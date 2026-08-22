"""What every route is given: a connection, a clock, and who is asking.

The authorisation check lives here rather than in each handler because invariant
6 is about the endpoint refusing, not about a button being hidden - and a check
each handler has to remember is a check some handler will not.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Any

from fastapi import Cookie, Depends, HTTPException, Request, status
from psycopg import Connection

from pdm.contracts import Role
from pdm.dispatch.service import DispatchRounds
from pdm.platform.auth.domain import Account, NotAuthenticated, NotAuthorised
from pdm.platform.auth.service import Authentication
from pdm.platform.clock import Clock
from pdm.platform.config import Config
from pdm.platform.jobs import JobQueue

SESSION_COOKIE = "pdm_session"


def connection(request: Request) -> Iterator[Connection[Any]]:
    """One connection and one transaction per request.

    Committed when the handler returns, rolled back if it fails. That is what
    makes an action and the access-log line recording it land together: a log
    written in its own transaction can record a read the database rolled back.

    **An `HTTPException` commits.** It is a decision the handler made - a 403, a
    404 - not a failure, and rolling back would take the access-log line with
    it. Refusals are the entries that matter most: "who looked at this manual"
    is the obvious question and "who tried to and could not" is the one asked
    after an incident, and it was being discarded by exactly the code meant to
    record it (ADR-019).
    """
    pool = request.app.state.pool
    with pool.connection() as conn:
        try:
            yield conn
        except HTTPException:
            conn.commit()
            raise


def authoring_jobs(request: Request) -> JobQueue:
    """The queue the API writes to and never reads from.

    `api` enqueues; `worker-authoring` claims. That is ADR-026's split seen from
    this side - the request that uploads a manual must not be the request that
    spends twenty minutes indexing it - and it is why this is a `JobQueue` for
    the authoring class rather than a worker of any kind.
    """
    queue: JobQueue = request.app.state.authoring_jobs
    return queue


def authentication(request: Request) -> Authentication:
    auth: Authentication = request.app.state.authentication
    return auth


def clock(request: Request) -> Clock:
    """The one time port (ADR-028), for a handler that has to stamp something.

    Most do not: the services the routers call carry their own clock, and a
    handler that read the time to pass it in would be a second source of it. This
    exists for the writes the API makes on its own account - an override is one -
    so that a compressed demo stamps simulated time on them like everything else.
    """
    the_clock: Clock = request.app.state.clock
    return the_clock


def plant(request: Request) -> Config:
    """The validated configuration, loaded once at boot (invariant 7).

    A handler that needs the layout - which model a machine is, which station it
    stands at - reads it from here rather than from the database, because
    `plant.yaml` is where the layout lives and a second copy is a second answer
    (ADR-027). Read-only: the config objects are frozen for the same reason
    `dispatch()` takes them as an argument.
    """
    config: Config = request.app.state.config
    return config


def dispatch_rounds(request: Request) -> DispatchRounds:
    """Layer 3, for the two read paths that report what it decided.

    Read-only from here. The API never writes a placement (ADR-026), and both
    screens that report the gate - the ticket queue and the line overview - call
    the same `decide()` the rounds themselves use, so a supervisor and the
    scheduler cannot be looking at two different shifts (ADR-050).
    """
    rounds: DispatchRounds = request.app.state.dispatch_rounds
    return rounds


def current_account(
    conn: Annotated[Connection[Any], Depends(connection)],
    auth: Annotated[Authentication, Depends(authentication)],
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> Account:
    try:
        return auth.account_for(conn, session)
    except NotAuthenticated as error:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error


CurrentAccount = Annotated[Account, Depends(current_account)]
Jobs = Annotated[JobQueue, Depends(authoring_jobs)]
Db = Annotated[Connection[Any], Depends(connection)]
Auth = Annotated[Authentication, Depends(authentication)]
Time = Annotated[Clock, Depends(clock)]
Plant = Annotated[Config, Depends(plant)]
Rounds = Annotated[DispatchRounds, Depends(dispatch_rounds)]


def requires(*roles: Role, action: str):  # type: ignore[no-untyped-def]
    """A dependency that admits only these roles, and logs either way.

    Returns the account so a handler can use it without asking twice.

    `action` is required rather than derived from the path, because the log is
    read by a person after an incident and "approve_playbook" answers their
    question where "POST /playbooks/SYM-014/approve" makes them work it out.
    """

    def dependency(account: CurrentAccount, conn: Db, auth: Auth) -> Account:
        try:
            auth.authorise(conn, account, *roles, action=action)
        except NotAuthorised as error:
            # 403 rather than 404: the caller is authenticated and the refusal
            # is the answer. Hiding the existence of the route from somebody who
            # already has an account protects nothing and makes a genuine
            # permissions problem look like a broken link.
            raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
        return account

    return dependency

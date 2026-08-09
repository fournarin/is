"""Signing in and out (ADR-036).

The only routes in the system that do not require a session, and the reason
there is no third: ADR-024 forbids a mode with authentication turned off, "not
even for a demo".
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field

from pdm.api.deps import SESSION_COOKIE, Auth, CurrentAccount, Db
from pdm.contracts import Role, UserId
from pdm.platform.auth.domain import SESSION_LIFETIME

router = APIRouter(tags=["sessions"])


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user: UserId = Field(min_length=1)
    password: str = Field(min_length=1)


class Whoami(BaseModel):
    """What the frontend needs to decide what to show.

    It decides what to *show*. Every refusal is still made by the endpoint -
    hiding a button the server would have refused anyway is a convenience, and
    treating it as the control is what invariant 6 exists to prevent.
    """

    model_config = ConfigDict(frozen=True)

    user: UserId
    display_name: str
    role: Role


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def log_in(credentials: Credentials, response: Response, conn: Db, auth: Auth) -> Whoami:
    result = auth.log_in(conn, credentials.user, credentials.password)
    if result is None:
        # One message for every kind of failure - unknown user, wrong password,
        # withdrawn access. Distinguishing them turns the login form into a way
        # of listing who works here, and helps the person who mistyped not at
        # all.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "those details do not match an account")

    account, token = result
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="strict",
        # Not `secure`: the plant network serves this over plain HTTP on one
        # node, and a cookie marked secure would simply never be sent. It goes
        # on the day there is TLS, and that is a deployment decision rather than
        # a code one.
    )
    return Whoami(user=account.user, display_name=account.display_name, role=account.role)


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def log_out(
    response: Response,
    conn: Db,
    auth: Auth,
    account: CurrentAccount,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    """Ends this session server-side, not only in the browser.

    Clearing the cookie alone would leave a row somebody holding the token could
    still use, which is the whole reason sessions are rows (ADR-036).

    `account` is required so that ending a session needs a valid one - otherwise
    an unauthenticated caller could delete any token they could guess.
    """
    del account
    if session:
        auth.log_out(conn, session)
    response.delete_cookie(SESSION_COOKIE, httponly=True, samesite="strict")


@router.get("/sessions/current")
def whoami(account: CurrentAccount) -> Whoami:
    return Whoami(user=account.user, display_name=account.display_name, role=account.role)

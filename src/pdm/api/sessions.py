"""Signing in and out (ADR-036).

The only routes in the system that do not require a session, and the reason
there is no third: ADR-024 forbids a mode with authentication turned off, "not
even for a demo".
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from pdm.api.deps import SESSION_COOKIE, Auth, CurrentAccount, Db, Time
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


class _Failures:
    """Failed sign-ins per user name, in this process (ADR-101).

    Five failures within five minutes refuse that name for the rest of the
    window. In memory on purpose: one API process, and a restart forgetting
    the count costs an attacker a restart rather than costing the plant a table.
    """

    LIMIT = 5
    WINDOW = timedelta(minutes=5)

    def __init__(self) -> None:
        self._seen: dict[str, list[datetime]] = {}

    def _recent(self, user: str, now: datetime) -> list[datetime]:
        kept = [at for at in self._seen.get(user, []) if now - at < self.WINDOW]
        self._seen[user] = kept
        return kept

    def refused(self, user: str, now: datetime) -> bool:
        return len(self._recent(user, now)) >= self.LIMIT

    def failed(self, user: str, now: datetime) -> None:
        self._recent(user, now).append(now)


def _failures(request: Request) -> _Failures:
    """One count per app, so each API process (and each test) keeps its own."""
    found = getattr(request.app.state, "sign_in_failures", None)
    if found is None:
        found = request.app.state.sign_in_failures = _Failures()
    return found


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def log_in(
    credentials: Credentials,
    request: Request,
    response: Response,
    conn: Db,
    auth: Auth,
    clock: Time,
) -> Whoami:
    now = clock.now()
    failures = _failures(request)
    if failures.refused(credentials.user, now):
        # Before the password is checked: each check costs 32 MiB of scrypt and
        # holds a database connection, so refusing late would still let a burst
        # of guesses take the screens down (ADR-101).
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "ใส่รหัสผ่านผิดหลายครั้งเกินไป รอ 5 นาทีแล้วลองใหม่ หรือติดต่อหัวหน้า",
        )
    result = auth.log_in(conn, credentials.user, credentials.password)
    if result is None:
        failures.failed(credentials.user, now)
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
        # On once the install serves over TLS (ADR-101). Over plain HTTP a
        # secure cookie would never be sent, so it is the install's to switch.
        secure=os.environ.get("PDM_COOKIE_SECURE") == "1",
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

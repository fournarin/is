"""Signing in, checking a session, and writing the access log (ADR-036).

The only module `api/` calls for identity. It opens no connection - the caller
supplies one - so that an action and the log line recording it commit together.

`IdentityProvider` is the seam ADR-036 put in the way of an unanswered question:
nobody has asked the plant whether it runs Active Directory, and the answer
changes the login screen and the account lifecycle while changing nothing an
endpoint needs to know. Local accounts are the only implementation today.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from psycopg import Connection

from pdm.contracts import Role, UserId
from pdm.platform.auth import repo
from pdm.platform.auth.domain import (
    SESSION_LIFETIME,
    Account,
    NotAuthenticated,
    NotAuthorised,
    hash_password,
    new_session_token,
    verify_password,
)
from pdm.platform.clock import Clock


@runtime_checkable
class IdentityProvider(Protocol):
    """Turns a name and a secret into an account, or does not.

    Returns None for every kind of failure - unknown user, wrong password,
    withdrawn access - and says nothing about which. A login form that
    distinguishes them tells an attacker which names exist, and the person who
    genuinely mistyped is no better served by the distinction.
    """

    def authenticate(
        self, conn: Connection[Any], user: UserId, password: str
    ) -> Account | None: ...


class LocalAccounts:
    """Accounts held in this system, with scrypt-hashed passwords."""

    def authenticate(self, conn: Connection[Any], user: UserId, password: str) -> Account | None:
        stored = repo.stored_password(conn, user)
        account = repo.account(conn, user)

        if stored is None or account is None:
            # Still hash something. Returning immediately makes an unknown user
            # measurably faster than a wrong password, which turns the login
            # form into a way of listing who works here.
            hash_password(password)
            return None

        if not verify_password(password, stored):
            return None
        if not account.active:
            return None

        if not stored.is_current:
            # The one moment the plaintext is available, so the one moment the
            # parameters can be raised without asking anybody to do anything.
            repo.set_password(conn, user, hash_password(password))

        return account


class Authentication:
    """Sessions, and the log of what was reached with them."""

    def __init__(self, identity: IdentityProvider, clock: Clock) -> None:
        self.identity = identity
        self.clock = clock

    def log_in(
        self, conn: Connection[Any], user: UserId, password: str
    ) -> tuple[Account, str] | None:
        """Returns the account and its session token, or None.

        The failed attempt is logged too. "Who tried to sign in as the engineer
        at two in the morning" is a question the log should be able to answer,
        and one holding only successes cannot.
        """
        now = self.clock.now()
        account = self.identity.authenticate(conn, user, password)

        if account is None:
            repo.record_access(
                conn,
                now=now,
                user=user,
                role=None,
                action="log_in",
                subject=None,
                allowed=False,
            )
            return None

        token = new_session_token()
        repo.open_session(
            conn, token=token, user=account.user, now=now, expires_at=now + SESSION_LIFETIME
        )
        repo.record_access(
            conn,
            now=now,
            user=account.user,
            role=account.role,
            action="log_in",
            subject=None,
            allowed=True,
        )
        return account, token

    def log_out(self, conn: Connection[Any], token: str) -> None:
        repo.close_session(conn, token)

    def account_for(self, conn: Connection[Any], token: str | None) -> Account:
        """The account behind a session token.

        Raises rather than returning None: every caller is a route that cannot
        proceed without one, and an optional return is an optional check.

        The role is read from the account on every request, never carried in the
        session. Withdrawing it takes effect on the next request rather than at
        the next login (ADR-036).
        """
        if not token:
            raise NotAuthenticated("no session")

        session = repo.session(conn, token)
        if session is None:
            raise NotAuthenticated("unknown session")
        if not session.is_valid_at(self.clock.now()):
            # Removed rather than left to a sweeper: the request that found it
            # is the cheapest place to notice.
            repo.close_session(conn, token)
            raise NotAuthenticated("session expired")

        account = repo.account(conn, session.user)
        if account is None or not account.active:
            raise NotAuthenticated("account is not active")
        return account

    def authorise(
        self,
        conn: Connection[Any],
        account: Account,
        *roles: Role,
        action: str,
        subject: str | None = None,
    ) -> None:
        """Check a role and log the attempt, allowed or refused.

        Both halves in one call on purpose. Splitting them makes it possible to
        check without logging, and ADR-019 requires the log "without exception" -
        an exception being precisely what a second, forgettable call creates.
        """
        allowed = account.may(*roles)
        repo.record_access(
            conn,
            now=self.clock.now(),
            user=account.user,
            role=account.role,
            action=action,
            subject=subject,
            allowed=allowed,
        )
        if not allowed:
            raise NotAuthorised(
                f"{account.user} holds {account.role} and this needs "
                f"{' or '.join(role.value for role in roles)}"
            )

    def create_account(
        self,
        conn: Connection[Any],
        *,
        user: UserId,
        display_name: str,
        role: Role,
        password: str,
    ) -> Account:
        """Used by the seeding script and by an engineer adding somebody.

        ADR-024 forbids a mode with authentication turned off, so a demo needs
        real accounts with real roles - which means creating them has to be an
        ordinary operation rather than a fixture.
        """
        return repo.create_account(
            conn,
            user=user,
            display_name=display_name,
            role=role,
            password=hash_password(password),
            now=self.clock.now(),
        )

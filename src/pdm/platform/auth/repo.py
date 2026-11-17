"""SQL for accounts, sessions and the access log. No business logic here.

Every function takes a connection first (ADR-031), so that an action and the
log line recording it commit together. A log written in its own transaction is
a log that can record a read the database rolled back, or miss one it kept.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from pdm.contracts import Role, UserId
from pdm.platform.auth.domain import Account, PasswordHash, Session

_ACCOUNT_COLUMNS = "user_id AS user, display_name, role, active"
_PASSWORD_COLUMNS = "password_salt, password_key, scrypt_n, scrypt_r, scrypt_p"


def create_account(
    conn: Connection[Any],
    *,
    user: UserId,
    display_name: str,
    role: Role,
    password: PasswordHash,
    now: datetime,
) -> Account:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            INSERT INTO account (user_id, display_name, role, password_salt, password_key,
                                 scrypt_n, scrypt_r, scrypt_p, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_ACCOUNT_COLUMNS}
            """,
            (
                user,
                display_name,
                role.value,
                password.salt,
                password.key,
                password.n,
                password.r,
                password.p,
                now,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return Account.model_validate(row)


def account(conn: Connection[Any], user: UserId) -> Account | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_ACCOUNT_COLUMNS} FROM account WHERE user_id = %s", (user,))
        row = cur.fetchone()
    return None if row is None else Account.model_validate(row)


def stored_password(conn: Connection[Any], user: UserId) -> PasswordHash | None:
    """Read separately from the account.

    So that every other query in the system returns an `Account` with no hash
    on it. A password that is only loaded by the one function that checks it
    cannot be logged, serialised into a response, or put in an error message by
    somebody who did not know it was there.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_PASSWORD_COLUMNS} FROM account WHERE user_id = %s", (user,))
        row = cur.fetchone()
    if row is None:
        return None
    return PasswordHash(
        salt=bytes(row["password_salt"]),
        key=bytes(row["password_key"]),
        n=row["scrypt_n"],
        r=row["scrypt_r"],
        p=row["scrypt_p"],
    )


def set_password(conn: Connection[Any], user: UserId, password: PasswordHash) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE account
               SET password_salt = %s, password_key = %s,
                   scrypt_n = %s, scrypt_r = %s, scrypt_p = %s
             WHERE user_id = %s
            """,
            (password.salt, password.key, password.n, password.r, password.p, user),
        )


def set_role(conn: Connection[Any], user: UserId, role: Role) -> None:
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET role = %s WHERE user_id = %s", (role.value, user))


def deactivate(conn: Connection[Any], user: UserId) -> None:
    """Withdraw access without removing the person.

    The row stays because a closed work order names who did it and an approved
    playbook names who approved it. Sessions go, so the change takes effect now
    rather than at their next login (ADR-036).
    """
    with conn.cursor() as cur:
        cur.execute("UPDATE account SET active = false WHERE user_id = %s", (user,))
        cur.execute("DELETE FROM session WHERE user_id = %s", (user,))


def open_session(
    conn: Connection[Any], *, token: str, user: UserId, now: datetime, expires_at: datetime
) -> Session:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO session (token, user_id, created_at, expires_at)
            VALUES (%s, %s, %s, %s)
            RETURNING token, user_id AS user, created_at, expires_at
            """,
            (token, user, now, expires_at),
        )
        row = cur.fetchone()
    assert row is not None
    return Session.model_validate(row)


def session(conn: Connection[Any], token: str) -> Session | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT token, user_id AS user, created_at, expires_at FROM session WHERE token = %s",
            (token,),
        )
        row = cur.fetchone()
    return None if row is None else Session.model_validate(row)


def close_session(conn: Connection[Any], token: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM session WHERE token = %s", (token,))


def delete_expired_sessions(conn: Connection[Any], now: datetime) -> int:
    """Remove sessions that have run out.

    Not a blob and not evidence: a session is state, and an expired one is
    already unusable, so deleting it removes nothing anybody could need. The
    access log is where "who was signed in" is recorded, and that is never
    deleted.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM session WHERE expires_at <= %s", (now,))
        return cur.rowcount


def record_access(
    conn: Connection[Any],
    *,
    now: datetime,
    user: UserId | None,
    role: Role | None,
    action: str,
    subject: str | None,
    allowed: bool,
) -> None:
    """One line per attempt, allowed or not.

    Refusals are logged as well as reads. "Who looked at this manual" is the
    obvious question; "who tried to and could not" is the one that matters after
    an incident, and a log holding only successes cannot answer it.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO access_log (at, user_id, role, action, subject, allowed)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (now, user, role.value if role else None, action, subject, allowed),
        )


def failed_attempts(
    conn: Connection[Any], *, action: str, subject: str, since: datetime
) -> tuple[int, datetime | None]:
    """Refused attempts at one action on one subject since a moment, and the last
    one's time (ADR-138, C2). A recorded reset of that subject starts the count
    again: a lead locked out is cleared by another lead, and that is audited too."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(at) FROM access_log WHERE action = %s AND subject = %s AND allowed",
            (f"{action}_reset", subject),
        )
        reset = cur.fetchone()
        # A reset clears everything up to and including its own moment.
        after_reset = reset is not None and reset[0] is not None and reset[0] >= since
        cur.execute(
            "SELECT count(*), max(at) FROM access_log"
            " WHERE action = %s AND subject = %s AND NOT allowed"
            f" AND at {'>' if after_reset else '>='} %s",
            (action, subject, reset[0] if after_reset and reset else since),
        )
        row = cur.fetchone()
    return (int(row[0]), row[1]) if row else (0, None)

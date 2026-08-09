"""Who somebody is, what they may do, and how a password is stored (ADR-036).

Pure: no database, no clock read, no I/O (ADR-030 layering). Hashing lives here
rather than in `repo.py` because it is a calculation, and because the one thing
that must never happen - a password reaching the database in a readable form -
is easier to keep true when the only function that writes one is in a file that
cannot reach a connection.
"""

from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta
from hashlib import scrypt

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import Role, UserId

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# scrypt from the standard library rather than argon2 from PyPI. Memory-hard,
# no C extension to install on the plant's machine, and ADR-008's rule against
# undocumented dependencies pointed the same way (ADR-036).
#
# n=2^15 with r=8 costs about 32 MB and a few tens of milliseconds per hash,
# which is the right order for a login on a machine that is also running
# PostgreSQL, Qdrant and a model. The numbers are stored beside every hash, so
# raising them later does not invalidate an account: an old hash verifies
# against its own parameters and can be upgraded on the next successful login.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1

# 128 * n * r comes to exactly 32 MiB at those parameters, and OpenSSL's default
# ceiling is exactly 32 MiB - so the recommended settings are the ones that fail,
# with "memory limit exceeded" and nothing pointing at why. Set explicitly with
# room above, which also makes the limit a decision of ours rather than a
# default that could move under us.
SCRYPT_MAXMEM = 96 * 1024 * 1024
_SALT_BYTES = 16
_KEY_BYTES = 32

# Long enough that guessing is not a strategy, and opaque: the token says
# nothing about who holds it, so a leaked one reveals nothing until it is used
# and can be revoked by deleting a row (ADR-036).
_TOKEN_BYTES = 32

SESSION_LIFETIME = timedelta(hours=12)
"""One shift plus a margin. Long enough that a technician is not asked to log in
again halfway through a job on a phone with gloves on, short enough that a
device left in the cell does not stay signed in until somebody notices."""


class PasswordHash(BaseModel):
    """A stored password, with the parameters it was made with.

    Kept as a model rather than a formatted string so the parameters cannot be
    read out of the wrong field when they change.
    """

    model_config = _FROZEN

    salt: bytes
    key: bytes
    n: int = Field(gt=1)
    r: int = Field(gt=0)
    p: int = Field(gt=0)

    @property
    def is_current(self) -> bool:
        """Whether this hash uses today's parameters.

        A login that verifies against weaker ones is an opportunity to rehash
        while the plaintext is in hand, which is the only moment it can be done.
        """
        return (self.n, self.r, self.p) == (SCRYPT_N, SCRYPT_R, SCRYPT_P)


def hash_password(password: str) -> PasswordHash:
    if not password:
        raise ValueError("a password of no characters is not a password")
    salt = secrets.token_bytes(_SALT_BYTES)
    key = scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
        dklen=_KEY_BYTES,
    )
    return PasswordHash(salt=salt, key=key, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)


def verify_password(password: str, stored: PasswordHash) -> bool:
    """Constant-time comparison against the parameters this hash was made with.

    `compare_digest` rather than `==` because a comparison that returns early on
    the first differing byte tells an attacker how much of a guess was right.
    The cost is nothing and the reasoning is not obvious from the code, which is
    exactly the kind of line that gets "simplified" later.
    """
    candidate = scrypt(
        password.encode("utf-8"),
        salt=stored.salt,
        n=stored.n,
        r=stored.r,
        p=stored.p,
        maxmem=SCRYPT_MAXMEM,
        dklen=len(stored.key),
    )
    return hmac.compare_digest(candidate, stored.key)


def new_session_token() -> str:
    return secrets.token_urlsafe(_TOKEN_BYTES)


class Account(BaseModel):
    """A person who can sign in, and the role they hold **now**.

    The role is here rather than on the session so that withdrawing it takes
    effect on the next request instead of at the next login. A role removed this
    morning that keeps working until somebody logs out is the same failure as a
    token that cannot be revoked (ADR-036).

    Not to be confused with `Playbook.approver_role`, which records the role held
    at the moment of approval and must not move when this one does (ADR-024).
    """

    model_config = _FROZEN

    user: UserId
    display_name: str = Field(min_length=1)
    role: Role
    active: bool = True

    def may(self, *roles: Role) -> bool:
        """Whether this account holds one of the roles an action requires.

        No hierarchy. An engineer is not "a technician with more rights": the
        actions are listed against roles in ADR-024 and a supervisor releasing
        held work is not a step above closing a job, it is a different job.
        Ranking them would quietly grant the engineer every technician action
        and make the table in ADR-024 decorative.
        """
        return self.active and self.role in roles


class Session(BaseModel):
    """One signed-in period. Revocable by deleting the row (ADR-036)."""

    model_config = _FROZEN

    token: str = Field(min_length=1)
    user: UserId
    created_at: datetime
    expires_at: datetime

    def is_valid_at(self, moment: datetime) -> bool:
        return moment < self.expires_at


class NotAuthenticated(Exception):
    """No session, or one that has expired or been revoked."""


class NotAuthorised(Exception):
    """A real session, and the role it holds is not one the action allows."""

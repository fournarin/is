"""Accounts, sessions and the access log.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-09

Three tables that exist because ADR-024 forbids a mode with authentication
turned off and ADR-019 requires every document read to pass through RBAC and
into a log, without exception.

The password columns hold scrypt output and its parameters, never a password
(ADR-036). The parameters are per row so that raising them later does not lock
anybody out: an old hash verifies against its own numbers and is replaced on the
next successful login.

No column has `DEFAULT now()`, for the reason recorded in 0001: a database
default reads real time even when the rest of the system is on a simulated clock
(ADR-028). That matters more here than anywhere else - a session expiry the
database sets and the application compares against the Clock would disagree by
however far a test or a compressed demo has moved.
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE account (
            user_id       text PRIMARY KEY CHECK (length(user_id) > 0),
            display_name  text NOT NULL CHECK (length(display_name) > 0),

            -- The four roles of ADR-024 and no others. A CHECK rather than an
            -- enum type: the ADR's own note says a fifth needs its own record
            -- before it appears in code, and this is where that shows up.
            role          text NOT NULL
                          CHECK (role IN ('technician', 'engineer',
                                          'supervisor', 'operator')),

            -- Left rather than deleted. A closed work order names the person who
            -- did it and an approved playbook names who approved it; removing
            -- the row would leave both pointing at nothing.
            active        boolean NOT NULL DEFAULT true,

            password_salt bytea NOT NULL,
            password_key  bytea NOT NULL,
            scrypt_n      integer NOT NULL CHECK (scrypt_n > 1),
            scrypt_r      integer NOT NULL CHECK (scrypt_r > 0),
            scrypt_p      integer NOT NULL CHECK (scrypt_p > 0),

            created_at    timestamptz NOT NULL
        )
    """)

    op.execute("""
        CREATE TABLE session (
            -- The token itself. Opaque and random, so the row is the only thing
            -- that knows whose it is, and revoking is a DELETE (ADR-036).
            token       text PRIMARY KEY CHECK (length(token) >= 32),
            user_id     text NOT NULL REFERENCES account (user_id),
            created_at  timestamptz NOT NULL,
            expires_at  timestamptz NOT NULL,

            CONSTRAINT session_expires_after_it_starts CHECK (expires_at > created_at)
        )
    """)

    # Signing out everywhere, and clearing a user's sessions when their access
    # is withdrawn.
    op.execute("CREATE INDEX session_by_user_idx ON session (user_id)")

    op.execute("""
        CREATE TABLE access_log (
            id           bigserial PRIMARY KEY,
            at           timestamptz NOT NULL,

            -- Not a foreign key. The log has to be able to record a request
            -- from an account that is later removed, and a constraint that
            -- could block a write to an audit table is a constraint that
            -- decides audit records are optional.
            user_id      text,
            role         text,

            action       text NOT NULL CHECK (length(action) > 0),
            -- What was reached: a document id, a playbook, a work order.
            subject      text,
            allowed      boolean NOT NULL
        )
    """)

    # Two questions this table exists to answer: what did this person see, and
    # who saw this document.
    op.execute("CREATE INDEX access_log_by_user_idx ON access_log (user_id, at DESC)")
    op.execute("CREATE INDEX access_log_by_subject_idx ON access_log (subject, at DESC)")


def downgrade() -> None:
    """Not supported (ADR-031). Dropping the access log would destroy the record
    of who read what, which is the reason ADR-019 serves documents through the
    API at all."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

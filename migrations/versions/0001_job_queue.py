"""Job queue table.

Revision ID: 0001
Create Date: 2026-08-08

Raw SQL rather than SQLAlchemy models, per ADR-031. Four of the five things this
schema most depends on - SKIP LOCKED claims, partial indexes, CHECK constraints
and (later) BRIN and tsvector - are things autogenerate cannot see, so a
generated migration would look complete while missing exactly the parts that
matter.

Note what is absent: no column has `DEFAULT now()`. Every timestamp is supplied
by the caller from the Clock port, because a database default reads real time
even when the rest of the system is on a simulated clock, and that single hole
would make SimulatedClock decorative (ADR-028).
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE job (
            id            bigserial PRIMARY KEY,

            -- Which worker may run this (ADR-026, invariant 12). A CHECK rather
            -- than an enum type: adding a value later is an ALTER on the
            -- constraint instead of a type migration, and there will only ever
            -- be a handful.
            job_class     text NOT NULL CHECK (job_class IN ('runtime', 'authoring')),
            kind          text NOT NULL,
            payload       jsonb NOT NULL DEFAULT '{}'::jsonb,

            status        text NOT NULL
                          CHECK (status IN ('queued', 'running', 'done', 'failed')),

            attempts      integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
            max_attempts  integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),

            -- Claimable from this moment. Carries both retry backoff and any
            -- deliberately delayed work.
            available_at  timestamptz NOT NULL,
            created_at    timestamptz NOT NULL,

            claimed_by    text,
            claimed_at    timestamptz,
            heartbeat_at  timestamptz,
            finished_at   timestamptz,
            last_error    text,

            -- A running job must say who is running it, so the reaper can tell a
            -- claim apart from a row that was left half written.
            CONSTRAINT running_jobs_have_a_worker
                CHECK (status <> 'running' OR claimed_by IS NOT NULL)
        )
    """)

    # The claim query's index. Partial, because the queued rows are a small and
    # shrinking fraction of the table: finished jobs are kept as evidence and
    # would otherwise make this index grow without bound.
    op.execute("""
        CREATE INDEX job_claimable_idx
            ON job (job_class, available_at, id)
            WHERE status = 'queued'
    """)

    # The reaper's index, also partial and for the same reason.
    op.execute("""
        CREATE INDEX job_running_idx
            ON job (job_class, heartbeat_at)
            WHERE status = 'running'
    """)


def downgrade() -> None:
    """Not supported. ADR-031 records that this project only moves forward, on
    the same reasoning ADR-018 used to drop playbook rollback: an approval step
    with a person in it makes going backwards the wrong answer anyway, and an
    untested downgrade path is worse than none."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

"""Isolation confirmed point by point, and the locks on the machine (ADR-135).

`step_confirmation` is the record REQ-H-04 asks for: who confirmed what, on which
step, at which point, when. Append-only, one row per (order, step, point, item),
because a confirmation is a statement a person made and a second tap is not a
second statement.

`lock_record` is the register: a personal lock is put on a point by its owner
and stays open until that owner takes it off. A lock number can be on one point
at a time, which the partial unique index makes the database's rule rather
than the screen's.
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE step_confirmation (
            work_order_ref text NOT NULL REFERENCES work_order (work_order_ref),
            step integer NOT NULL CHECK (step >= 1),
            point_id text NOT NULL DEFAULT '',
            item text NOT NULL
                CHECK (item IN ('off', 'locked', 'verified', 'released', 'wait_started')),
            confirmed_by text NOT NULL,
            confirmed_at timestamptz NOT NULL,
            PRIMARY KEY (work_order_ref, step, point_id, item)
        )
    """)
    op.execute("""
        CREATE TABLE lock_record (
            lock_id bigserial PRIMARY KEY,
            work_order_ref text NOT NULL REFERENCES work_order (work_order_ref),
            machine_id text NOT NULL,
            point_id text NOT NULL,
            lock_no text NOT NULL CHECK (length(trim(lock_no)) > 0),
            owner text NOT NULL,
            step integer NOT NULL CHECK (step >= 1),
            applied_at timestamptz NOT NULL,
            released_at timestamptz,
            CHECK (released_at IS NULL OR released_at >= applied_at)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX a_lock_is_on_one_point ON lock_record (lock_no)"
        " WHERE released_at IS NULL"
    )
    op.execute(
        "CREATE INDEX lock_record_open_by_machine ON lock_record (machine_id)"
        " WHERE released_at IS NULL"
    )


def downgrade() -> None:
    """Not supported (ADR-031): it would lose who locked what."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

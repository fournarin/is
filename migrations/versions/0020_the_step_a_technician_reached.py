"""Where a technician got to in a job's steps (ADR-134).

One row per order, overwritten as the person moves on: the job page has to say
"step 2 of 6" and its button has to resume there, and a phone that went to
sleep, or a second phone, has nothing else to resume from. Kept beside the order
rather than on it, because it is a bookmark and not part of what the order
instructed - `playbook_snapshot` is that, and is never rewritten.
"""

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work_step_reached (
            work_order_ref text PRIMARY KEY REFERENCES work_order (work_order_ref),
            step integer NOT NULL CHECK (step >= 1),
            recorded_by text NOT NULL,
            recorded_at timestamptz NOT NULL
        )
    """)


def downgrade() -> None:
    """Not supported (ADR-031)."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

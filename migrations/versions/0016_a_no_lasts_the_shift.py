"""A shift lead's no lasts the shift, and a job put down goes back to the queue (ADR-120).

Two things the owner's second trial found on the shift lead's board.

A rejected proposal returned its order to the queue, and the next round
proposed it again five minutes later: the lead said no and the same card came
back. The rejection now sets the order aside until the shift ends or the lead
brings it back, and `resumed_at` is the record of the second.

A handed-over order nobody held was placed by no round and listed on no
technician's screen, so it waited for ever. Such an order is queued work with a
note on it, and the rows already stranded are returned to the queue here.
"""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE dispatch_proposal
            ADD COLUMN resumed_at timestamptz,
            ADD COLUMN resumed_by text
    """)
    op.execute("""
        UPDATE work_order SET status = 'queued'
         WHERE status = 'handed_over' AND assignees = '[]'::jsonb
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE dispatch_proposal DROP COLUMN resumed_at, DROP COLUMN resumed_by")

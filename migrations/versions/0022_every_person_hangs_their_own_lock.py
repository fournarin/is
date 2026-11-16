"""Every person hangs their own lock, and a lock comes off with a reason (ADR-136).

A confirmation is keyed by who made it, so a second technician on the same job
can switch off nothing and still hang their own lock on the same point (group
lockout, 1910.147(f)(3)); the receiver of a handover locks for themselves. The
restore step's plant checks are a fifth item. A lock that comes off says why:
the restore step, or its owner taking it off after the job left their hands.
"""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE step_confirmation DROP CONSTRAINT step_confirmation_pkey")
    op.execute(
        "ALTER TABLE step_confirmation"
        " ADD PRIMARY KEY (work_order_ref, step, point_id, item, confirmed_by)"
    )
    op.execute("ALTER TABLE step_confirmation DROP CONSTRAINT step_confirmation_item_check")
    op.execute("""
        ALTER TABLE step_confirmation ADD CONSTRAINT step_confirmation_item_check
            CHECK (item IN ('off', 'locked', 'verified', 'checked', 'released', 'wait_started'))
    """)
    op.execute("ALTER TABLE lock_record ADD COLUMN release_reason text")
    op.execute("""
        ALTER TABLE lock_record ADD CONSTRAINT a_lock_off_says_why
            CHECK (released_at IS NULL OR release_reason IS NOT NULL)
    """)


def downgrade() -> None:
    """Not supported (ADR-031)."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

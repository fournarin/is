"""A lock taken off after its job closed records the restore checks (ADR-138, C3).

Once a "still locked" job has closed, its restore step is gone with it, so the
plant's checks before energy goes back - tools, guards, people, operator - are
confirmed on the release itself and kept beside it.
"""

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lock_record ADD COLUMN release_checks jsonb")


def downgrade() -> None:
    """Not supported (ADR-031)."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

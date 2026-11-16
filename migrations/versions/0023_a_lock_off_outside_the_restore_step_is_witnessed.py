"""A lock taken off outside the restore step names the shift lead who saw it (ADR-137).

After a handover or a "still locked" close the owner takes their own lock off
from their own list, not in a restore step, so nothing in the steps vouches for
it. The shift lead who watched it come off is recorded beside the reason.
"""

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE lock_record ADD COLUMN release_witness text")


def downgrade() -> None:
    """Not supported (ADR-031)."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

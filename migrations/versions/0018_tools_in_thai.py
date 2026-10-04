"""A playbook's tools in the approver's Thai, beside the manual's (ADR-130).

Position for position with `tools`; an empty string is a tool left as the manual
wrote it. Existing rows carry none, which reads as every tool untranslated.
"""

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE playbook ADD COLUMN tools_th text[] NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE playbook DROP COLUMN tools_th")

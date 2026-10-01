"""A reported fault remembers who reported it (ADR-122).

The reporter was written into the reason sentence and nowhere else, so nothing
could answer "what did I report and where is it now". In the owner's second
trial the answer was: nowhere anybody could see. Orders reported before this
carry no reporter; the sentence still names them.
"""

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_order ADD COLUMN reported_by text")
    op.execute(
        "CREATE INDEX work_order_reported_by_idx ON work_order (reported_by, created_at DESC) "
        "WHERE reported_by IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX work_order_reported_by_idx")
    op.execute("ALTER TABLE work_order DROP COLUMN reported_by")

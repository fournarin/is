"""One photo kept with a reported fault (ADR-142).

The bytes are a blob in the same content-addressed store as the manuals
(ADR-019), so nothing here deletes them; this row says which report they belong
to, who took them and when. One per report: the primary key is the work order.
"""

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE work_order_photo (
            work_order_ref text PRIMARY KEY REFERENCES work_order (work_order_ref),
            blob_id text NOT NULL,
            content_type text NOT NULL,
            size_bytes integer NOT NULL CHECK (size_bytes > 0),
            taken_by text NOT NULL,
            taken_at timestamptz NOT NULL
        )
        """
    )


def downgrade() -> None:
    """Not supported (ADR-031)."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

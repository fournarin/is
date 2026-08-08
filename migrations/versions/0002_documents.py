"""Document table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-08

The primary key is the sha256 of the file's contents (ADR-019), which makes
re-uploading the same manual a no-op at the database level rather than a
duplicate row somebody has to reconcile later.

No column has `DEFAULT now()`, for the reason recorded in 0001: a database
default reads real time even when the rest of the system runs on a simulated
clock (ADR-028).

There is no DELETE anywhere in this schema's intended use, and no ON DELETE
CASCADE waiting to be triggered by one. Withdrawing an edition sets a status
(ADR-018, ADR-019).
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document (
            -- sha256 of the contents, lowercase hex. Also the file's name on
            -- disk, so a row and its blob cannot drift apart.
            document_id   text PRIMARY KEY CHECK (document_id ~ '^[0-9a-f]{64}$'),

            -- As uploaded. Display only: operators reupload new editions under
            -- the old name, which is why identity is the hash instead.
            filename      text NOT NULL CHECK (length(filename) > 0),
            content_type  text NOT NULL CHECK (length(content_type) > 0),
            size_bytes    bigint NOT NULL CHECK (size_bytes >= 0),

            machine_model text NOT NULL CHECK (length(machine_model) > 0),
            title         text NOT NULL CHECK (length(title) > 0),
            edition       text,

            status        text NOT NULL CHECK (status IN ('active', 'withdrawn')),

            uploaded_by   text NOT NULL CHECK (length(uploaded_by) > 0),
            uploaded_at   timestamptz NOT NULL,
            withdrawn_at  timestamptz,

            -- The same rule the Document model enforces, kept here as well
            -- because the question "was this edition in force when that work
            -- order was issued" is answered by reading these two columns, and a
            -- row where they disagree cannot answer it (ADR-018).
            CONSTRAINT withdrawal_is_dated CHECK (
                (status = 'withdrawn' AND withdrawn_at IS NOT NULL)
                OR (status = 'active' AND withdrawn_at IS NULL)
            )
        )
    """)

    # The library listing: every edition for a model, newest first. Not partial
    # on status, because tracing a citation from a closed work order reaches for
    # withdrawn editions specifically.
    op.execute("""
        CREATE INDEX document_by_model_idx
            ON document (machine_model, uploaded_at DESC, document_id)
    """)


def downgrade() -> None:
    """Not supported (ADR-031), and here it would also be destructive: the table
    is the only record of which edition a citation refers to."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

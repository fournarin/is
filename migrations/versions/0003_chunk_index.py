"""Page records and the sparse index.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08

Two tables, because a page and a chunk answer different questions. `chunk` is
what search reads. `document_page` records **every** page including the ones
that produced no text, so "this manual is indexed" can be replaced by "83 of its
200 pages produced text and the rest are scans" - which is the only version of
that sentence somebody can act on (ADR-034).

Both are derived data. Re-ingesting replaces them and withdrawing a document
removes them, while the file itself is never touched (ADR-019). That is the one
place in this schema where rows are deleted on purpose, and it is safe precisely
because the documents, not the index, are the record.

The tsvector is a generated column rather than a trigger: it cannot drift from
the text it summarises, and there is no ordering problem between the two writes
because there is only one write.
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_page (
            document_id  text NOT NULL REFERENCES document (document_id),

            -- 1-based, matching the number printed on the page, which is what a
            -- playbook step cites and what a technician is told to open.
            page         integer NOT NULL CHECK (page > 0),

            outcome      text NOT NULL
                         CHECK (outcome IN ('text', 'no_text', 'too_little_text')),
            characters   integer NOT NULL CHECK (characters >= 0),

            PRIMARY KEY (document_id, page)
        )
    """)

    op.execute("""
        CREATE TABLE chunk (
            chunk_id     bigserial PRIMARY KEY,
            document_id  text NOT NULL,
            page         integer NOT NULL CHECK (page > 0),

            -- Position within the page. Makes re-ingest deterministic and lets a
            -- citation resolve to a place on the page rather than the whole of it.
            ordinal      integer NOT NULL CHECK (ordinal >= 0),

            text         text NOT NULL CHECK (length(text) > 0),

            -- Generated, not maintained by a trigger or the application: a
            -- tsvector written separately from its text is one failed update
            -- away from an index that answers questions about a version of the
            -- page nobody can see.
            --
            -- 'english' is deliberate and is a stated limit, not an oversight.
            -- The manuals are English and technicians ask in Thai; no text
            -- search configuration bridges that, and the cross-lingual half of
            -- retrieval is the embedding model's job (ADR-034 point 4).
            search       tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED,

            -- A chunk belongs to a page that was actually read. Without this a
            -- chunk could outlive the page record it was derived from and the
            -- coverage figures would stop adding up.
            FOREIGN KEY (document_id, page) REFERENCES document_page (document_id, page),
            UNIQUE (document_id, page, ordinal)
        )
    """)

    op.execute("CREATE INDEX chunk_search_idx ON chunk USING gin (search)")

    # Ingest and withdrawal both work a whole document at a time.
    op.execute("CREATE INDEX chunk_by_document_idx ON chunk (document_id)")


def downgrade() -> None:
    """Not supported (ADR-031). Rebuilding the index means re-ingesting, which
    is a different operation from unwinding a migration."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

"""What the review screen records, and the fourth thing a reviewer may do.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-22

Four columns on `playbook_proposal` and one more status. All of it exists so
that ADR-003 can be checked rather than asserted: the principle rests on an
engineer reading every draft, and until now nothing in the system could say
whether reading was happening or how long it took (ADR-064).

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028): the
clock is a port, and a demo running compressed time must not have the database
stamp real time behind its back.
"""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE playbook_proposal
            -- When the detail was last opened by somebody who may review it.
            -- The measurement ADR-064 asks for is taken from this and the
            -- decision time, both from the Clock, rather than from a timer in
            -- the browser: a number the screen sends is a number the screen can
            -- be wrong about, and this one goes in the report.
            ADD COLUMN opened_at timestamptz,

            -- Seconds from that open to the decision, written once when the
            -- decision is made. Stored rather than derived at read time because
            -- `opened_at` moves on every subsequent read, and the figure the
            -- report quotes has to be the one that was true when the engineer
            -- decided.
            ADD COLUMN review_seconds integer
                       CHECK (review_seconds IS NULL OR review_seconds >= 0),

            -- What the approver changed before approving: one object per step
            -- they rewrote, carrying the text before and after. The edit rate is
            -- counted from this, and the diff is what makes an approval that
            -- altered the manual's wording attributable to the person who
            -- altered it (ADR-064, ADR-003).
            ADD COLUMN edits jsonb NOT NULL DEFAULT '[]'::jsonb
    """)

    # An edit is something that happened on the way to an approval. A dismissed
    # or sent-back row carrying one would be a diff of text nobody applied.
    op.execute("""
        ALTER TABLE playbook_proposal
            ADD CONSTRAINT only_applied_proposals_carry_edits CHECK (
                jsonb_array_length(edits) = 0 OR status = 'applied'
            )
    """)

    # `sent_back` is the decision that was missing: the draft is wrong and the
    # drafter is asked again with the reviewer's note as the question (ADR-064).
    # Kept apart from `dismissed` because the two answer different questions -
    # "this symptom has no playbook because nobody thinks it needs one" against
    # "because the drafts so far have been wrong" (ADR-038 section 6).
    op.execute("""
        ALTER TABLE playbook_proposal
            DROP CONSTRAINT playbook_proposal_status_check,
            ADD CONSTRAINT playbook_proposal_status_check
                CHECK (status IN ('pending', 'applied', 'dismissed', 'sent_back'))
    """)


def downgrade() -> None:
    """Not supported (ADR-031). Dropping these would destroy the evidence that
    review is happening at all, which is what ADR-003 rests on."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

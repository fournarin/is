"""The shift lead confirms a proposal to somebody else (ADR-132).

A fifth ending for a proposal, `reassigned`: sent out now, to a person the
scheduler did not choose. It is a person's decision, so it names them, and it
keeps the crew the lead chose beside the one the round proposed, so the
confirmation record holds both sides of the disagreement.
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE dispatch_proposal ADD COLUMN confirmed_assignees jsonb")
    op.execute("""
        ALTER TABLE dispatch_proposal
        DROP CONSTRAINT dispatch_proposal_state_check,
        ADD CONSTRAINT dispatch_proposal_state_check
            CHECK (state IN ('pending', 'confirmed', 'rejected', 'expired', 'reassigned')),
        DROP CONSTRAINT a_persons_decision_names_them,
        ADD CONSTRAINT a_persons_decision_names_them CHECK (
            state NOT IN ('confirmed', 'rejected', 'reassigned')
            OR (decided_by IS NOT NULL AND decided_role IS NOT NULL)
        ),
        ADD CONSTRAINT a_reassignment_names_the_crew CHECK (
            state <> 'reassigned' OR confirmed_assignees IS NOT NULL
        )
    """)


def downgrade() -> None:
    """Not supported (ADR-031): it would lose who the lead gave work to."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

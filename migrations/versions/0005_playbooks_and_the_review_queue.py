"""The playbook table and the review queue.

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-13

Two tables, split by whether the content is served (ADR-038). `playbook` holds
one row per (symptom_code, machine_model) with no version chain (ADR-018);
`playbook_proposal` holds everything waiting for a person - drafts from the
authoring pipeline and objections from technicians, in one queue because one
engineer reviews both (design.md 4).

**`playbook` has no `draft` status, and that is the point.** Invariant 3 says a
draft is never served at runtime, not even when there is nothing else to give the
technician. Here that stops being a rule the serving code must remember: there is
no draft row for a query to reach.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE playbook (
            symptom_code         text NOT NULL CHECK (length(symptom_code) > 0),
            machine_model        text NOT NULL CHECK (length(machine_model) > 0),

            -- Steps with their per-step provenance, as PlaybookStep serialises
            -- (ADR-015). jsonb rather than a child table: nothing queries inside
            -- a step, the whole list is read and written together, and a child
            -- table would let a step exist without its playbook.
            steps                jsonb NOT NULL CHECK (jsonb_array_length(steps) > 0),
            tools                text[] NOT NULL DEFAULT '{}',
            parts                text[] NOT NULL DEFAULT '{}',

            estimated_minutes    integer NOT NULL CHECK (estimated_minutes > 0),
            required_skill       text NOT NULL CHECK (length(required_skill) > 0),
            -- A two-person job consumes twice the shift's capacity; omitting it
            -- makes load_ratio read low (ADR-025).
            required_technicians integer NOT NULL DEFAULT 1
                                 CHECK (required_technicians >= 1),

            source_doc           text NOT NULL REFERENCES document (document_id),
            page                 integer NOT NULL CHECK (page >= 1),

            -- Every document any step cites, maintained on write. The cascade in
            -- ADR-018 - replacing a manual moves every playbook derived from it
            -- to needs_review - is a safety mechanism, and reading it out of the
            -- steps json at cascade time would make it depend on the shape of a
            -- document that changes whenever a step gains a field.
            cited_documents      text[] NOT NULL CHECK (cardinality(cited_documents) > 0),

            revision             integer NOT NULL DEFAULT 1 CHECK (revision >= 1),

            -- Two statuses, not three. A draft is a proposal and lives in the
            -- other table (ADR-038), so invariant 3 is a state this table cannot
            -- hold rather than a rule a query has to remember.
            status               text NOT NULL
                                 CHECK (status IN ('approved', 'needs_review')),
            -- Why it is back in review: which manual was replaced, or what a
            -- technician reported. Shown beside the warning the screen carries
            -- while it is still served.
            review_reason        text,

            -- Not null even for needs_review: the row was approved once, and by
            -- whom is what makes it servable at all (ADR-003).
            approved_by          text NOT NULL REFERENCES account (user_id),
            approved_at          timestamptz NOT NULL,
            -- The role held at the moment of approval, not the approver's
            -- current role. Roles change; the evidence must not (ADR-024).
            approver_role        text NOT NULL CHECK (approver_role = 'engineer'),

            PRIMARY KEY (symptom_code, machine_model)
        )
    """)

    # The cascade's query: every playbook citing this document.
    op.execute(
        "CREATE INDEX playbook_by_cited_document_idx ON playbook USING gin (cited_documents)"
    )

    # The review screen's second list: what is currently flagged.
    op.execute("""
        CREATE INDEX playbook_needing_review_idx ON playbook (machine_model, symptom_code)
        WHERE status = 'needs_review'
    """)

    op.execute("""
        CREATE TABLE playbook_proposal (
            proposal_id     bigserial PRIMARY KEY,

            symptom_code    text NOT NULL CHECK (length(symptom_code) > 0),
            machine_model   text NOT NULL CHECK (length(machine_model) > 0),

            -- One queue, both sources (design.md 4). An engineer opens one box,
            -- and a system that needs two opened is a system where one is not.
            origin          text NOT NULL CHECK (origin IN ('drafted', 'technician')),

            -- What the drafter concluded, in its own words (ADR-037). A withheld
            -- draft is a row here with no steps: "the drafter produced nothing
            -- usable and here is what it tried" is information, and a silence is
            -- not.
            outcome         text NOT NULL
                            CHECK (outcome IN ('repair', 'diagnostic',
                                               'not_found', 'withheld',
                                               'objection')),
            steps           jsonb NOT NULL DEFAULT '[]'::jsonb,
            tools           text[] NOT NULL DEFAULT '{}',

            -- What the page stated, where it stated anything. Null is the honest
            -- answer and the reviewer supplies the value; a default here would
            -- be a figure with the authority of a manual and the provenance of
            -- nothing (ADR-037 section 8).
            proposed_skill    text,
            proposed_minutes  integer CHECK (proposed_minutes IS NULL
                                             OR proposed_minutes > 0),

            -- The steps the gate refused, with their reasons. Kept because in
            -- aggregate they are the only signal that a backend has started
            -- fabricating.
            rejected        jsonb NOT NULL DEFAULT '[]'::jsonb,
            reason          text NOT NULL CHECK (length(reason) > 0),

            created_at      timestamptz NOT NULL,
            -- Null when the authoring pipeline made it. A technician's objection
            -- names the person, because the review screen shows who reported it.
            created_by      text REFERENCES account (user_id),

            status          text NOT NULL
                            CHECK (status IN ('pending', 'applied', 'dismissed')),
            decided_by      text REFERENCES account (user_id),
            decided_at      timestamptz,
            decision_note   text,

            -- Nothing is deleted (ADR-038), so a decided row has to say who and
            -- when. Without this the queue could hold a dismissal nobody owns.
            CONSTRAINT proposal_decisions_are_attributed CHECK (
                (status = 'pending' AND decided_by IS NULL AND decided_at IS NULL)
                OR (status <> 'pending' AND decided_by IS NOT NULL
                    AND decided_at IS NOT NULL)
            ),

            -- A proposal with no steps cannot be applied to anything. The check
            -- is here rather than only in the service because "apply" is the one
            -- operation that puts text in front of a technician.
            CONSTRAINT applied_proposals_have_steps CHECK (
                status <> 'applied' OR jsonb_array_length(steps) > 0
            )
        )
    """)

    # The review queue itself: oldest first, so the objection from three weeks
    # ago is not permanently below this morning's re-draft.
    op.execute("""
        CREATE INDEX playbook_proposal_queue_idx
        ON playbook_proposal (created_at)
        WHERE status = 'pending'
    """)

    # "What is pending for this symptom" - asked before drafting again, so the
    # pipeline does not file the same proposal twice.
    op.execute("""
        CREATE INDEX playbook_proposal_by_pair_idx
        ON playbook_proposal (symptom_code, machine_model, status)
    """)


def downgrade() -> None:
    """Not supported (ADR-031). Dropping these would destroy the record of what
    was approved and by whom, which is what makes a served playbook servable."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

"""The state between a round deciding and a person agreeing, and its record.

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-23

ADR-071. The advisor asked for a person to press the button before a ticket
reaches a technician, and for that requirement to be removable later once there
is a record to judge it by. Two things follow here.

`work_order.status` gains `proposed`: decided, and not yet agreed to. It is a
status rather than a flag on another table because status is what every other
part of the system asks about - the open-queue index below, the capacity
calculation, the technician's transitions - and a job whose status says a
technician has it while another table says nobody approved it is a
disagreement that would be resolved differently in each of those places.

`dispatch_proposal` is what the decision leaves behind. One row per proposal,
carrying what the round decided and the round it was decided against, because a
round is never stored (ADR-050) and six weeks later there is nothing else to
read it back against - the same argument, and the same columns, as
`work_order_override` in 0009.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE work_order
        DROP CONSTRAINT work_order_status_check,
        ADD CONSTRAINT work_order_status_check
            CHECK (status IN ('queued', 'proposed', 'assigned', 'in_progress',
                              'handed_over', 'closed', 'cancelled'))
    """)

    # A proposal is open work: it consumes its assignees' capacity and it is part
    # of the queue a round is handed (ADR-071 section 3). Left out of this index,
    # `open_orders` would fall back to a sequential scan and - worse - the
    # partial index would no longer describe the query that reads it.
    op.execute("DROP INDEX work_order_open_idx")
    op.execute("""
        CREATE INDEX work_order_open_idx ON work_order (created_at, work_order_ref)
        WHERE status IN ('queued', 'proposed', 'assigned', 'in_progress', 'handed_over')
    """)

    op.execute("""
        CREATE TABLE dispatch_proposal (
            proposal_id     bigserial PRIMARY KEY,
            work_order_ref  text NOT NULL
                            REFERENCES work_order (work_order_ref) ON DELETE CASCADE,

            -- What the round decided. Copied rather than read back off the order,
            -- which a confirmation or a later round overwrites: the question this
            -- table answers is what the supervisor was shown, and an order's
            -- current assignees stop being that the moment anything changes them.
            proposed_at     timestamptz NOT NULL,
            assignees       jsonb NOT NULL,
            priority_score  double precision NOT NULL,
            priority_reason text NOT NULL,

            -- The round it was decided against (ADR-050, and 0009's columns for
            -- the same reason). Null where there was no capacity to compute a
            -- ratio from, which the band then names (ADR-045 section 3).
            band            text,
            load_ratio      double precision,
            shift_id        text,
            on_date         date,

            -- confirmed: a supervisor agreed, and the order is assigned.
            -- rejected:  a supervisor did not, and the order is queued again.
            -- expired:   nobody answered inside the window, same destination.
            state           text NOT NULL DEFAULT 'pending'
                            CHECK (state IN ('pending', 'confirmed', 'rejected', 'expired')),
            decided_at      timestamptz,
            decided_by      text,
            decided_role    text,
            -- Required on a rejection. An override with no reason is
            -- indistinguishable from a misclick when somebody reads it back
            -- (ADR-059), and a rejection is an override of the scheduler.
            reason          text,

            CONSTRAINT a_settled_proposal_says_when CHECK (
                state = 'pending' OR decided_at IS NOT NULL
            ),
            -- An expiry is the system noticing, so it names nobody. A
            -- confirmation and a rejection are somebody's decision, and a row
            -- that could not say whose would make the whole table unreadable as
            -- evidence about how well the scheduler and the shift lead agree.
            CONSTRAINT a_persons_decision_names_them CHECK (
                state NOT IN ('confirmed', 'rejected')
                OR (decided_by IS NOT NULL AND decided_role IS NOT NULL)
            ),
            CONSTRAINT a_rejection_carries_a_reason CHECK (
                state <> 'rejected' OR (reason IS NOT NULL AND length(reason) > 0)
            )
        )
    """)

    # One open question per order at a time. Without this a round that ran twice
    # over the same order - a retry, a worker that came back - would leave a
    # supervisor two identical proposals and no way to tell that confirming one
    # settled the other.
    op.execute(
        "CREATE UNIQUE INDEX dispatch_proposal_one_pending_idx "
        "ON dispatch_proposal (work_order_ref) WHERE state = 'pending'"
    )

    # What the supervisor's screen asks for, and what the expiry sweep asks for:
    # the open ones, oldest first. Partial for the reason 0011's is - settled
    # rows are all of them after a day and none of them are read by this query.
    op.execute(
        "CREATE INDEX dispatch_proposal_pending_idx "
        "ON dispatch_proposal (proposed_at) WHERE state = 'pending'"
    )


def downgrade() -> None:
    """Not supported (ADR-031). Dropping this table would lose the record of
    what a supervisor was asked and what they answered, which is the evidence
    ADR-071 exists to collect."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

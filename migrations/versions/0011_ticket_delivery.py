"""Where a ticket's journey out of the system is written down.

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-23

ADR-012 puts layer 4 behind an interface because nobody knows yet whether the
plant has a CMMS. ADR-068 decides what that interface has to record: at-least-
once delivery with the state kept here, rather than fire-and-forget. The moment
the destination is somebody else's system, "the ticket was dispatched" and "the
ticket arrived" stop being the same sentence, and only one of them can be
answered by the round that placed it.

One row per work order, by primary key. That is the whole "once per round"
guarantee: a round that runs twice, or a worker that dies between the placement
and the delivery, finds the row already there.

`destination` is recorded rather than used to select. An order delivered to one
destination is not undelivered by somebody changing the configured sink, and the
record is what says where it actually went.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ticket_delivery (
            work_order_ref   text PRIMARY KEY
                             REFERENCES work_order (work_order_ref) ON DELETE CASCADE,

            -- pending: the round placed it and nothing has been attempted yet.
            -- failed:  the destination refused it, and the next round tries again.
            -- delivered: it arrived, and nothing tries again.
            state            text NOT NULL
                             CHECK (state IN ('pending', 'delivered', 'failed')),

            -- Null until something has been attempted. Which destination a
            -- ticket went to is a fact about the delivery, not about the order.
            destination      text CHECK (destination IS NULL OR length(destination) > 0),

            -- The destination's own identifier for the ticket. The only thing
            -- that can reconcile two systems after the fact: our own record of
            -- having tried is exactly the answer nobody believes.
            external_ref     text,

            attempts         integer NOT NULL CHECK (attempts >= 0),
            queued_at        timestamptz NOT NULL,
            last_attempt_at  timestamptz,
            delivered_at     timestamptz,
            -- What the destination said. Stored because "why did this ticket
            -- never arrive" is asked days later, by somebody who cannot see the
            -- log line that would have answered it.
            last_error       text,

            -- Delivered means all three, or none of them. A row claiming to have
            -- arrived with no time and no identifier is worse than no row: it
            -- stops the retry while proving nothing.
            CONSTRAINT delivered_has_its_evidence CHECK (
                (state = 'delivered')
                = (delivered_at IS NOT NULL AND external_ref IS NOT NULL)
            ),
            -- A failure with no reason is indistinguishable from a bug six weeks
            -- later, the same argument 0009 made about an override with no reason.
            CONSTRAINT failure_says_why CHECK (
                state <> 'failed' OR last_error IS NOT NULL
            ),
            CONSTRAINT untried_means_pending CHECK (
                attempts > 0 OR (state = 'pending' AND last_attempt_at IS NULL)
            )
        )
    """)

    # The question every round asks: what still has to go out. Partial, because
    # delivered rows are all of them after a week and none of them are ever read
    # by this query.
    op.execute(
        "CREATE INDEX ticket_delivery_outstanding_idx "
        "ON ticket_delivery (queued_at) WHERE state <> 'delivered'"
    )


def downgrade() -> None:
    """Not supported (ADR-031). Dropping this table would lose which tickets
    reached their destination, which is the only reason it exists."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

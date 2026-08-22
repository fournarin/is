"""Where a person overruling the scheduler is written down.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-22

ADR-005 runs in both directions: the system explains itself to a person, and a
person explains themselves to the system when they overrule it. Two overrides
exist in the design - a technician disagreeing with where a job was ranked, and
a shift lead releasing a ticket the load gate is holding - and until this table
neither had anywhere to land.

Both are recorded from the first day they are possible. An override that was not
written down cannot be reconstructed afterwards: the round that produced it is
computed when asked (ADR-050) and is gone by the time anybody reads about it, so
the load band and ratio at that moment are stored here rather than looked up
later.

`reason` is NOT NULL and non-empty by CHECK. An override with no reason is
indistinguishable from a bug when somebody reads it six weeks later, and the
constraint belongs beside the data rather than only in the request model that
happens to be in front of it today.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE work_order_override (
            id              bigserial PRIMARY KEY,
            at              timestamptz NOT NULL,

            kind            text NOT NULL
                            CHECK (kind IN ('priority_disagreement', 'release_held')),

            -- The order the person was looking at. A foreign key here, unlike
            -- in access_log: this row is about one work order and a row naming
            -- an order that never existed is not a record of anything.
            work_order_ref  text NOT NULL REFERENCES work_order (work_order_ref),

            -- Not a foreign key, and for access_log's reason: the record has to
            -- survive the account being removed, and a constraint that can
            -- block a write to an audit table decides audit records are
            -- optional.
            user_id         text NOT NULL CHECK (length(user_id) > 0),
            role            text NOT NULL CHECK (length(role) > 0),

            reason          text NOT NULL CHECK (length(btrim(reason)) > 0),

            -- The round the decision was taken against. Null for a
            -- disagreement, which is about one ticket's rank rather than about
            -- the shift, and null for `load_ratio` where there was no capacity
            -- to compute one from (ADR-045 §3).
            band            text CHECK (band IN ('light', 'normal', 'heavy', 'no_capacity')),
            load_ratio      double precision,

            -- A release is a decision about the shift, so it says which shift.
            shift_id        text,
            on_date         date,

            -- A release with no band recorded would be a release nobody can
            -- read back in the context that produced it, which is the whole
            -- point of the row (ADR-011).
            CHECK (kind <> 'release_held' OR band IS NOT NULL)
        )
    """)

    # The two questions this table is read with: what has been overridden about
    # this order, and what did this person overrule.
    op.execute(
        "CREATE INDEX work_order_override_by_order_idx "
        "ON work_order_override (work_order_ref, at DESC)"
    )
    op.execute(
        "CREATE INDEX work_order_override_by_user_idx ON work_order_override (user_id, at DESC)"
    )

    # The question every round asks: which orders has somebody released. Partial,
    # because a round never asks about disagreements and they are the rows that
    # will accumulate.
    op.execute(
        "CREATE INDEX work_order_override_released_idx "
        "ON work_order_override (work_order_ref) WHERE kind = 'release_held'"
    )


def downgrade() -> None:
    """Not supported (ADR-031). Dropping this table would destroy the record of
    who overruled the scheduler and why, which is the only reason it exists."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

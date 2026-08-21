"""Who is on the line, and for how long today.

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-21

ADR-045 said these two had no tables and that they would arrive with the tick
that calls `dispatch()`. This is that tick's half of the bargain: the pure
function still takes its world as arguments, and something has to read the world
first.

The column lists follow `Technician` and `ShiftAssignment` in
`contracts/resources.py` (ADR-027). Two things are worth reading:

**`available_minutes` is not the shift's length.** People take leave, attend
training and arrive late. Capacity that assumed the length would be capacity the
load gate over-commits, on every shift where somebody left early - and it would
over-commit quietly, because the numbers would all still add up.

**`on_date` is the local date the shift *started*.** Monday night's shift runs
into Tuesday morning and its roster is filed under Monday (ADR-045 §7). The
primary key says so, and `shift_at` resolves the same way.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE technician (
            user_id     text PRIMARY KEY CHECK (length(user_id) > 0),

            -- Drawn from the single list in plant.yaml, which is also where
            -- Playbook.required_skill draws from. Two vocabularies would fail to
            -- match in silence: work would keep being assigned, just to the
            -- wrong people (ADR-027). Validated at the boundary rather than by a
            -- foreign key, because the list is configuration and this is not.
            skills      jsonb NOT NULL DEFAULT '[]'::jsonb,

            -- Somebody who has left. Kept rather than deleted: closed work
            -- orders name their assignees, and a row that vanished would leave
            -- those orders pointing at nobody (ADR-024's argument about roles,
            -- one table along).
            active      boolean NOT NULL DEFAULT true,

            created_at  timestamptz NOT NULL,

            CHECK (jsonb_typeof(skills) = 'array')
        )
    """)

    op.execute("""
        CREATE TABLE shift_assignment (
            shift_id          text NOT NULL CHECK (length(shift_id) > 0),
            -- The local date the shift started on, which is what a roster is
            -- written against: the night shift running into Tuesday morning is
            -- Monday night's, and its assignments are filed under Monday.
            on_date           date NOT NULL,
            technician        text NOT NULL REFERENCES technician (user_id),

            -- Person-minutes this person really has, which is both sides of
            -- load_ratio's unit (design.md 13.2). Zero is not allowed: somebody
            -- with no minutes is somebody who is not on this shift, and a row
            -- saying otherwise would put them in the roster and out of the
            -- capacity at the same time.
            available_minutes integer NOT NULL CHECK (available_minutes > 0),

            PRIMARY KEY (shift_id, on_date, technician)
        )
    """)

    # The dispatch round asks exactly one question of this table - who is on
    # this shift, on this date - once every round, for ever.
    op.execute("""
        CREATE INDEX shift_assignment_by_shift
            ON shift_assignment (on_date, shift_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE shift_assignment")
    op.execute("DROP TABLE technician")

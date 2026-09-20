"""The PM schedule: what is due, when it was last done, and one order at a time.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-20

ADR-083, and the slice the health screen has been apologising for since ADR-081:
`pm_overdue` has been reading zero off a table that did not exist.

Two things live here and one of them deliberately does not. **The definition -
which machine, which symptom, how often - is in `plant.yaml`**, because an
interval is a decision with a source (a manual page) and configuration is where
this project keeps decisions somebody can read. **The state is here**, because
"when was this last done" is something that happened, and the row that says so
has to survive a config edit.

`due_at` is not a column. It is `last_done_at + interval`, or the moment the
task was registered when nothing has ever been recorded, and #90 asked for
exactly that: the next occurrence falls out of the interval rather than out of a
second field somebody has to keep in step with the first.

**The partial unique index is the answer to "what if one is still open when the
next falls due".** It stacks nothing: while an order for a task is queued,
proposed, assigned, in progress or handed over, a second one cannot be written -
by the scan, by a script, or by two workers at the same moment. That is
ADR-023's argument arriving at the other origin, and it is a constraint rather
than a convention for the same reason invariant 8 is.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028): the
clock a row is written against is the system's, and a database default would
make a simulated run write real time.

There is no foreign key from `work_order.pm_task_ref` to this table. An order
outlives the schedule that produced it, exactly as it outlives the layout it was
created under (ADR-048), and a closed order pointing at a task somebody has
since removed from `plant.yaml` is a record of what happened rather than a
broken reference.
"""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE pm_task (
            pm_task_ref    text PRIMARY KEY,
            machine_id     text NOT NULL,

            -- PM- prefixed, so layer 2 serves it through the ordinary lookup and
            -- never learns the word "PM" (ADR-027, design.md 13.3).
            symptom_code   text NOT NULL
                           CHECK (symptom_code LIKE 'PM-%'),

            -- The interval as seconds. Config states it in hours, because the
            -- manuals do; one unit reaches the database, because two would be a
            -- conversion somebody has to remember.
            interval_seconds bigint NOT NULL CHECK (interval_seconds > 0),

            -- NULL means nobody has ever recorded this being done. It is not the
            -- same as "done long ago", and the ticket and the health reading
            -- both say which (ADR-083 section 4).
            last_done_at   timestamptz,

            -- When the task entered the system. With no last_done_at, this is
            -- what the task is due from, so a plant that installs today starts
            -- with its whole schedule due rather than with a date nobody knows.
            registered_at  timestamptz NOT NULL
        )
    """)

    # One live order per task. The scan also checks before issuing, and would be
    # correct on its own with one worker; this is what makes it true with two,
    # with a script, and with whatever writes orders in a year's time.
    op.execute("""
        CREATE UNIQUE INDEX one_live_order_per_pm_task
        ON work_order (pm_task_ref)
        WHERE pm_task_ref IS NOT NULL
          AND status IN ('queued', 'proposed', 'assigned', 'in_progress', 'handed_over')
    """)


def downgrade() -> None:
    """Not supported (ADR-031). Dropping this table would lose every record of
    when a PM task was last done, and the orders that carry those completions
    are closed rows that cannot be replayed."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

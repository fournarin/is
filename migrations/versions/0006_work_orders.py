"""Work orders, and the trigger that makes invariant 2 true.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-13

One table, three origins (ADR-010), and the scheduling facts copied onto the row
because `dispatch()` may not read a table to find them (ADR-041, invariant 10).

**The trigger is the point of this migration.** `playbook_snapshot` is the only
evidence of what the system instructed on a job closed a year ago (ADR-018), and
invariant 2 asks for a database constraint rather than a convention. Frozen
pydantic models stop the application editing it and stop nothing else: a
migration, a repair script, or a future `repo.py` writing `UPDATE work_order SET
...` all reach the row.

No column has `DEFAULT now()`, for the reason recorded in 0001 (ADR-028).
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The ticket number a technician reads out over the radio. A sequence rather
    # than a value built from the machine and the time: two orders for one
    # machine within a minute is unlikely and not impossible, and slice 3.0's
    # lesson was that "unlikely" written into a primary key is a collision
    # waiting for the day the plant is busy. Not `DEFAULT now()` in any form, so
    # the rule about clocks (ADR-028) is untouched.
    op.execute("CREATE SEQUENCE work_order_number")

    op.execute("""
        CREATE TABLE work_order (
            work_order_ref    text PRIMARY KEY
                              DEFAULT 'WO-' || lpad(nextval('work_order_number')::text, 6, '0')
                              CHECK (length(work_order_ref) > 0),

            -- Where the work came from. `condition` needs a Finding, `scheduled`
            -- a PM task, `manual` neither - checked below rather than left to
            -- the application, because an order with no source is one nobody can
            -- trace after an incident (ADR-010).
            origin            text NOT NULL
                              CHECK (origin IN ('condition', 'scheduled', 'manual')),
            finding_ref       text,
            pm_task_ref       text,

            machine_id        text NOT NULL CHECK (length(machine_id) > 0),
            severity          text NOT NULL
                              CHECK (severity IN ('low', 'medium', 'high', 'critical')),

            -- Copied from the Finding at creation, never read back from it: the
            -- scheduler needs them and must not import layer 1 (ADR-030).
            finding_kind      text CHECK (finding_kind IN ('detected', 'predicted')),
            eta               timestamptz,
            eta_confidence    interval,

            playbook_ref      text,
            -- Frozen at issue. The trigger below is what makes "frozen" a
            -- property of the database rather than a habit of the code.
            playbook_snapshot jsonb NOT NULL DEFAULT '[]'::jsonb,
            snapshot_approved_by text,
            snapshot_approved_at timestamptz,
            -- Set when the playbook was awaiting review at the moment this order
            -- was issued. ADR-018 serves such a playbook anyway; that is only
            -- defensible while the person holding the ticket can tell (ADR-041).
            playbook_warning  text,

            -- What the load gate computes with (ADR-041, design.md 13.2).
            estimated_minutes integer NOT NULL CHECK (estimated_minutes > 0),
            -- Null means "any technician": there is no honest default, and a
            -- guess sends the wrong person to an electrical fault.
            required_skill    text,
            required_technicians integer NOT NULL DEFAULT 1
                              CHECK (required_technicians >= 1),
            -- True when the duration came from policy.yaml rather than a manual.
            estimate_is_fallback boolean NOT NULL DEFAULT false,

            -- Why the job exists, written once. Never empty: a ticket that
            -- cannot explain itself gets overruled and then ignored (ADR-005).
            reason            text NOT NULL CHECK (length(reason) > 0),
            -- Why it is ranked where it is. Layer 3 writes this on the tick that
            -- ranked it, so it starts empty.
            priority_score    double precision NOT NULL DEFAULT 0,
            priority_reason   text NOT NULL DEFAULT '',

            status            text NOT NULL
                              CHECK (status IN ('queued', 'assigned', 'in_progress',
                                                'handed_over', 'closed', 'cancelled')),
            assignees         jsonb NOT NULL DEFAULT '[]'::jsonb,
            work_segments     jsonb NOT NULL DEFAULT '[]'::jsonb,
            handover_note     text,

            blocked_minutes   integer NOT NULL DEFAULT 0 CHECK (blocked_minutes >= 0),
            blocked_reason    text[] NOT NULL DEFAULT '{}',
            outcome           text CHECK (outcome IN ('fixed', 'temporary_fix',
                                                      'not_fixed', 'no_problem_found')),
            technician_feedback text,

            created_at        timestamptz NOT NULL,
            closed_at         timestamptz,

            -- `actual_minutes` is deliberately absent: it is the sum of the work
            -- segments and a stored copy could disagree with them, which is the
            -- disagreement ADR-025 exists to prevent (a job crossing midnight
            -- recording eighteen hours).

            CONSTRAINT an_order_names_its_source CHECK (
                (origin = 'condition' AND finding_ref IS NOT NULL)
                OR (origin = 'scheduled' AND pm_task_ref IS NOT NULL)
                OR origin = 'manual'
            ),
            -- An order with a playbook takes its estimate from it; the fallback
            -- flag describes an order that has none. Both at once says two
            -- things and one of them is wrong (ADR-041).
            CONSTRAINT a_fallback_estimate_has_no_playbook CHECK (
                NOT estimate_is_fallback OR playbook_ref IS NULL
            ),
            CONSTRAINT a_handover_carries_a_note CHECK (
                status <> 'handed_over' OR (handover_note IS NOT NULL
                                            AND length(handover_note) > 0)
            ),
            CONSTRAINT a_closed_order_says_how_it_ended CHECK (
                status <> 'closed' OR outcome IS NOT NULL
            )
        )
    """)

    # The dispatch tick reads the whole open queue every five minutes and orders
    # it by age (design.md 6.2). Leading on created_at rather than on severity:
    # nothing filters by severity - the ranking does that in memory - and an
    # index that leads with a column no query restricts cannot serve the sort.
    # Partial, because closed orders are kept for ever as evidence.
    op.execute("""
        CREATE INDEX work_order_open_idx ON work_order (created_at, work_order_ref)
        WHERE status IN ('queued', 'assigned', 'in_progress', 'handed_over')
    """)

    # "Seen N times" on the technician's screen reads back through this, and so
    # does anybody asking what a Finding produced (ADR-023).
    op.execute("CREATE INDEX work_order_by_finding_idx ON work_order (finding_ref)")
    op.execute("CREATE INDEX work_order_by_machine_idx ON work_order (machine_id, created_at DESC)")

    # ── invariant 2 ────────────────────────────────────────────────────────
    # The snapshot may be written once and never changed. Not "should not":
    # the alternative to a trigger is trusting every future writer, and the
    # thing being trusted is the only evidence of what a technician was told.
    op.execute("""
        CREATE FUNCTION refuse_to_change_a_playbook_snapshot() RETURNS trigger AS $$
        BEGIN
            IF NEW.playbook_snapshot IS DISTINCT FROM OLD.playbook_snapshot
               OR NEW.snapshot_approved_by IS DISTINCT FROM OLD.snapshot_approved_by
               OR NEW.snapshot_approved_at IS DISTINCT FROM OLD.snapshot_approved_at
            THEN
                RAISE EXCEPTION
                    'playbook_snapshot is frozen when the order is issued and is the only '
                    'evidence of what the system instructed (invariant 2, ADR-018)'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER work_order_snapshot_is_frozen
        BEFORE UPDATE ON work_order
        FOR EACH ROW EXECUTE FUNCTION refuse_to_change_a_playbook_snapshot()
    """)


def downgrade() -> None:
    """Not supported (ADR-031). Dropping this table would destroy the record of
    what every closed job instructed, which is the thing ADR-018 moved here to
    keep."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

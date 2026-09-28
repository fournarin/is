"""An empty snapshot may be filled once, before anybody works the order (ADR-102).

An order issued before any playbook existed carries no steps. When an engineer
approves one for its symptom, the order still in the queue or on the board
should carry it: the technician was otherwise told "no approved steps" about a
symptom that has them. Invariant 2 exists so that a job proves what it
instructed, and an order nobody has started has instructed nothing yet.

So the trigger allows exactly one change: from no steps to steps, while the
order has no work segment and the new snapshot names its approver. Every other
change is refused as before, and a snapshot with steps is still never rewritten.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION refuse_to_change_a_playbook_snapshot() RETURNS trigger AS $$
        BEGIN
            IF NEW.playbook_snapshot IS DISTINCT FROM OLD.playbook_snapshot
               OR NEW.snapshot_approved_by IS DISTINCT FROM OLD.snapshot_approved_by
               OR NEW.snapshot_approved_at IS DISTINCT FROM OLD.snapshot_approved_at
            THEN
                IF OLD.playbook_snapshot = '[]'::jsonb
                   AND OLD.work_segments = '[]'::jsonb
                   AND NEW.playbook_snapshot <> '[]'::jsonb
                   AND NEW.snapshot_approved_by IS NOT NULL
                   AND NEW.snapshot_approved_at IS NOT NULL
                THEN
                    RETURN NEW;
                END IF;
                RAISE EXCEPTION
                    'playbook_snapshot is frozen once it holds steps or work has started, '
                    'and is the only evidence of what the system instructed '
                    '(invariant 2, ADR-018, ADR-102)'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION refuse_to_change_a_playbook_snapshot() RETURNS trigger AS $$
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

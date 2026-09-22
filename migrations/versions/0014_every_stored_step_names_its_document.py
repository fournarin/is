"""Prove that no stored step cites a page of no document, before the contract requires it.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-20

ADR-084 section 2. This migration creates nothing and changes nothing. It is a
proof obligation, run once, at the moment the rule it proves becomes enforced.

`PlaybookStep.source_doc` now refuses the empty string (invariant 4). Steps are
read back through `PlaybookStep.model_validate` in two places -
`work/repo.py::_to_order` for a `playbook_snapshot` and `playbooks/repo.py` for
a served playbook - so a stricter contract meeting a row written under the older
one would stop that work order loading at all. The order would not be wrong; it
would be unreadable, which is worse, because invariant 2 makes a snapshot
unchangeable and there is no repair short of deleting the record of what a
technician was instructed to do.

**So the row is checked rather than rewritten.** If every stored step names a
document, the upgrade is a no-op and the contract is safe to tighten. If one
does not, the upgrade stops and names the rows, and a person decides what a work
order whose snapshot lost its provenance should become. That decision is not one
a migration may take at three in the morning on somebody's plant database.

On a database seeded by this repository both queries return nothing: the drafter
is the only writer of steps, and it carries `source_doc` from the page it
quoted. That is the expected result, and it is not the same as not checking.
"""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


# Kept as module constants so the test can run the same query against rows it
# writes on purpose. A check nobody has ever seen fail is a check nobody knows
# the shape of (#108).
UNATTRIBUTED_SNAPSHOT_STEPS = """
    SELECT work_order_ref
      FROM work_order
     WHERE EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(playbook_snapshot) AS step
                WHERE coalesce(btrim(step ->> 'source_doc'), '') = ''
           )
"""

UNATTRIBUTED_PLAYBOOK_STEPS = """
    SELECT symptom_code || ' / ' || machine_model
      FROM playbook
     WHERE EXISTS (
               SELECT 1
                 FROM jsonb_array_elements(steps) AS step
                WHERE coalesce(btrim(step ->> 'source_doc'), '') = ''
           )
"""


def _refuse_if_any(query: str, what: str) -> None:
    op.execute(f"""
        DO $$
        DECLARE offenders text;
        BEGIN
            SELECT string_agg(ref, ', ')
              INTO offenders
              FROM ({query}) AS unattributed(ref);

            IF offenders IS NOT NULL THEN
                RAISE EXCEPTION
                    '{what} cite a page of no document, and PlaybookStep now refuses that '
                    '(invariant 4, ADR-084): %. Decide what each one should be before '
                    'upgrading; a snapshot may not be rewritten (invariant 2).', offenders;
            END IF;
        END $$;
    """)


def upgrade() -> None:
    _refuse_if_any(UNATTRIBUTED_SNAPSHOT_STEPS, "steps of these work orders'' snapshots")
    _refuse_if_any(UNATTRIBUTED_PLAYBOOK_STEPS, "steps of these playbooks")


def downgrade() -> None:
    """Not supported (ADR-031). There is nothing to undo: this migration read
    two tables and wrote nothing."""
    raise NotImplementedError("downgrade is not supported (ADR-031)")

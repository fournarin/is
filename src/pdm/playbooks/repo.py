"""SQL for the playbook table and the review queue. No business logic here.

Every function takes a connection first (ADR-031), so that applying a proposal
and the row it changes commit together - a queue that could record an approval
without the playbook it approved would be a queue that lies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pdm.contracts import (
    DocumentId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.playbooks.domain import (
    Proposal,
    ProposalOrigin,
    ProposalStatus,
    cited_documents,
)

_PLAYBOOK_COLUMNS = """
    symptom_code, machine_model, steps, tools, parts, estimated_minutes,
    required_skill, required_technicians, source_doc, page, revision, status,
    review_reason, approved_by, approved_at, approver_role
"""

_PROPOSAL_COLUMNS = """
    proposal_id, symptom_code, machine_model, origin, outcome, steps, tools,
    proposed_skill, proposed_minutes, rejected, reason, created_at, created_by,
    status, decided_by, decided_at, decision_note
"""


class NothingToApply(Exception):
    """The proposal has no steps, or has already been decided."""


def _to_playbook(row: dict[str, Any]) -> tuple[Playbook, str | None]:
    review_reason = row.pop("review_reason")
    row["steps"] = tuple(PlaybookStep.model_validate(step) for step in row["steps"])
    row["tools"] = tuple(row["tools"])
    row["parts"] = tuple(row["parts"])
    return (Playbook.model_validate(row), review_reason)


def _to_proposal(row: dict[str, Any]) -> Proposal:
    row["steps"] = tuple(PlaybookStep.model_validate(step) for step in row["steps"])
    row["tools"] = tuple(row["tools"])
    row["rejected"] = tuple(row["rejected"])
    return Proposal.model_validate(row)


def get(
    conn: Connection[Any], symptom_code: SymptomCode, machine_model: MachineModel
) -> tuple[Playbook, str | None] | None:
    """The served row for this pair, with the reason it is flagged if it is.

    There is no `status` filter and none is needed: this table holds no drafts
    (ADR-038), so the query cannot reach unapproved text however it is written.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PLAYBOOK_COLUMNS} FROM playbook "
            "WHERE symptom_code = %s AND machine_model = %s",
            (symptom_code, machine_model),
        )
        row = cur.fetchone()
    return _to_playbook(row) if row else None


def needing_review(conn: Connection[Any]) -> list[tuple[Playbook, str | None]]:
    """Everything served with a warning, for the second list on the screen."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PLAYBOOK_COLUMNS} FROM playbook "
            "WHERE status = 'needs_review' ORDER BY machine_model, symptom_code"
        )
        rows = cur.fetchall()
    return [_to_playbook(row) for row in rows]


def save_approved(
    conn: Connection[Any],
    playbook: Playbook,
    *,
    approved_by: UserId,
    approved_at: datetime,
    approver_role: Role,
) -> Playbook:
    """Write an approved playbook, overwriting whatever the pair held.

    Overwrite with `revision + 1` is the whole of ADR-018: no chain, no
    supersedes, and history kept on the work order instead. The revision is read
    from the row rather than from the argument, so two approvals racing produce
    two revisions rather than the same number twice.

    Refuses anything that is not approved. `PlaybookDraft.into_playbook` builds a
    `draft` object for the review screen to render, and this table has nowhere
    for it to go (ADR-038).
    """
    if playbook.status is not PlaybookStatus.APPROVED:
        raise ValueError(
            f"the playbook table holds no {playbook.status.value} rows: a draft is a proposal "
            "and lives in the queue (ADR-038, invariant 3)"
        )

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO playbook (
                symptom_code, machine_model, steps, tools, parts,
                estimated_minutes, required_skill, required_technicians,
                source_doc, page, cited_documents, revision, status,
                review_reason, approved_by, approved_at, approver_role
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'approved',
                    NULL, %s, %s, %s)
            ON CONFLICT (symptom_code, machine_model) DO UPDATE SET
                steps                = EXCLUDED.steps,
                tools                = EXCLUDED.tools,
                parts                = EXCLUDED.parts,
                estimated_minutes    = EXCLUDED.estimated_minutes,
                required_skill       = EXCLUDED.required_skill,
                required_technicians = EXCLUDED.required_technicians,
                source_doc           = EXCLUDED.source_doc,
                page                 = EXCLUDED.page,
                cited_documents      = EXCLUDED.cited_documents,
                revision             = playbook.revision + 1,
                status               = 'approved',
                review_reason        = NULL,
                approved_by          = EXCLUDED.approved_by,
                approved_at          = EXCLUDED.approved_at,
                approver_role        = EXCLUDED.approver_role
            RETURNING """
            + _PLAYBOOK_COLUMNS,
            (
                playbook.symptom_code,
                playbook.machine_model,
                Jsonb([step.model_dump(mode="json") for step in playbook.steps]),
                list(playbook.tools),
                list(playbook.parts),
                playbook.estimated_minutes,
                playbook.required_skill,
                playbook.required_technicians,
                playbook.source_doc,
                playbook.page,
                list(cited_documents(playbook.steps, playbook.source_doc)),
                approved_by,
                approved_at,
                approver_role.value,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return _to_playbook(row)[0]


def flag_for_review(conn: Connection[Any], document_id: DocumentId, *, reason: str) -> list[str]:
    """Move every playbook citing this manual into `needs_review`.

    Still served, with a warning, because a technician with an out-of-date
    procedure is better off than one with none while an engineer looks at it
    (ADR-018, design.md 5).

    Returns the symptom codes touched, which is what an operator replacing an
    edition needs to be told before they press the button.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE playbook
               SET status = 'needs_review', review_reason = %s
             WHERE %s = ANY (cited_documents)
               AND status <> 'needs_review'
            RETURNING symptom_code
            """,
            (reason, document_id),
        )
        return [str(row[0]) for row in cur.fetchall()]


def add_proposal(
    conn: Connection[Any],
    *,
    symptom_code: SymptomCode,
    machine_model: MachineModel,
    origin: ProposalOrigin,
    outcome: str,
    steps: tuple[PlaybookStep, ...],
    tools: tuple[str, ...],
    proposed_skill: SkillId | None,
    proposed_minutes: int | None,
    rejected: tuple[dict[str, object], ...],
    reason: str,
    created_at: datetime,
    created_by: UserId | None,
) -> Proposal:
    """File something for review. Several may be pending for one pair (ADR-038)."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO playbook_proposal (
                symptom_code, machine_model, origin, outcome, steps, tools,
                proposed_skill, proposed_minutes, rejected, reason, created_at,
                created_by, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING """
            + _PROPOSAL_COLUMNS,
            (
                symptom_code,
                machine_model,
                origin.value,
                outcome,
                Jsonb([step.model_dump(mode="json") for step in steps]),
                list(tools),
                proposed_skill,
                proposed_minutes,
                Jsonb(list(rejected)),
                reason,
                created_at,
                created_by,
            ),
        )
        row = cur.fetchone()
    assert row is not None
    return _to_proposal(row)


def queue(conn: Connection[Any], *, limit: int = 50) -> list[Proposal]:
    """The review queue, oldest first.

    Oldest first so that an objection from three weeks ago is not permanently
    below this morning's re-draft - which is how a queue becomes a list nobody
    reaches the bottom of (ADR-013's warning, one layer down).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PROPOSAL_COLUMNS} FROM playbook_proposal "
            "WHERE status = 'pending' ORDER BY created_at, proposal_id LIMIT %s",
            (limit,),
        )
        rows = cur.fetchall()
    return [_to_proposal(row) for row in rows]


def proposal(conn: Connection[Any], proposal_id: int) -> Proposal | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PROPOSAL_COLUMNS} FROM playbook_proposal WHERE proposal_id = %s",
            (proposal_id,),
        )
        row = cur.fetchone()
    return _to_proposal(row) if row else None


def decide(
    conn: Connection[Any],
    proposal_id: int,
    *,
    status: ProposalStatus,
    decided_by: UserId,
    decided_at: datetime,
    note: str | None,
) -> Proposal:
    """Record that a person looked at this and what they concluded.

    The `WHERE status = 'pending'` is what makes deciding twice impossible: the
    second call finds no row and raises, rather than overwriting the first
    person's decision with the second's.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE playbook_proposal
               SET status = %s, decided_by = %s, decided_at = %s, decision_note = %s
             WHERE proposal_id = %s AND status = 'pending'
            RETURNING """
            + _PROPOSAL_COLUMNS,
            (status.value, decided_by, decided_at, note, proposal_id),
        )
        row = cur.fetchone()
    if row is None:
        raise NothingToApply(f"proposal {proposal_id} is not pending")
    return _to_proposal(row)

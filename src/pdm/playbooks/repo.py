"""SQL for the playbook table and the review queue. No business logic here.

Every function takes a connection first (ADR-031), so that applying a proposal
and the row it changes commit together - a queue that could record an approval
without the playbook it approved would be a queue that lies.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, NamedTuple

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
    PendingForPair,
    Proposal,
    ProposalOrigin,
    ProposalStatus,
    StepEdit,
    cited_documents,
    energy_problems,
)

_PLAYBOOK_COLUMNS = """
    symptom_code, machine_model, steps, tools, tools_th, parts, estimated_minutes,
    required_skill, required_technicians, source_doc, page, revision, status,
    review_reason, approved_by, approved_at, approver_role
"""

_PROPOSAL_COLUMNS = """
    proposal_id, symptom_code, machine_model, origin, outcome, steps, tools,
    proposed_skill, proposed_minutes, rejected, reason, created_at, created_by,
    status, decided_by, decided_at, decision_note, opened_at, review_seconds,
    edits
"""


class NothingToApply(Exception):
    """The proposal has no steps, or has already been decided."""


def _to_playbook(row: dict[str, Any]) -> tuple[Playbook, str | None]:
    review_reason = row.pop("review_reason")
    row["steps"] = tuple(PlaybookStep.model_validate(step) for step in row["steps"])
    row["tools"] = tuple(row["tools"])
    row["tools_th"] = tuple(row["tools_th"])
    row["parts"] = tuple(row["parts"])
    return (Playbook.model_validate(row), review_reason)


def _to_proposal(row: dict[str, Any]) -> Proposal:
    row["steps"] = tuple(PlaybookStep.model_validate(step) for step in row["steps"])
    row["tools"] = tuple(row["tools"])
    row["rejected"] = tuple(row["rejected"])
    row["edits"] = tuple(StepEdit.model_validate(edit) for edit in row["edits"])
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


def last_approver(conn: Connection[Any], machine_model: MachineModel) -> UserId | None:
    """The engineer to ask about a job with no steps (ADR-134).

    Whoever last approved a playbook for this model, since they have read its
    manual; for a model nobody has written for yet, whoever approves playbooks
    here at all.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT approved_by FROM playbook WHERE approved_by IS NOT NULL "
            "ORDER BY machine_model = %s DESC, approved_at DESC LIMIT 1",
            (machine_model,),
        )
        row = cur.fetchone()
    return UserId(row[0]) if row else None


def needing_review(conn: Connection[Any]) -> list[tuple[Playbook, str | None]]:
    """Everything served with a warning, for the second list on the screen."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PLAYBOOK_COLUMNS} FROM playbook "
            "WHERE status = 'needs_review' ORDER BY machine_model, symptom_code"
        )
        rows = cur.fetchall()
    return [_to_playbook(row) for row in rows]


def served_pairs(conn: Connection[Any]) -> set[tuple[SymptomCode, MachineModel]]:
    """Every pair runtime has something to give a technician for.

    Both statuses this table can hold, because both are served: a `needs_review`
    row still reaches a technician, with a warning (ADR-018), so it is a
    different question - "these are being served while their manual has changed"
    - and not an unanswered symptom.

    A pair whose only playbook is a draft has no row here at all, because drafts
    live in the other table (ADR-038). That is what makes the gap list correct
    without a `status` filter: from a technician's side, a draft is nothing.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT symptom_code, machine_model FROM playbook")
        return {(SymptomCode(row[0]), MachineModel(row[1])) for row in cur.fetchall()}


class PricedPair(NamedTuple):
    """One served playbook, reduced to what Loop 1 needs to say anything.

    The steps are left in the table on purpose. Loop 1 proposes a duration and
    reads nothing else, and a reader that returned whole playbooks would hand the
    caller the text as well - which is how a screen about minutes grows a panel
    of procedures nobody opened it to review (ADR-087 section 1).
    """

    symptom_code: SymptomCode
    machine_model: MachineModel
    estimated_minutes: int
    status: PlaybookStatus


def priced_pairs(conn: Connection[Any]) -> list[PricedPair]:
    """Every pair with a price, in the order the loop screen reads them.

    Both statuses, for `served_pairs`' reason: a `needs_review` playbook is still
    served to a technician (ADR-018), so the estimate it prices work with is
    still the one `load_ratio` is computed from, and a proposal about it is no
    less relevant for the manual having changed.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT symptom_code, machine_model, estimated_minutes, status "
            "FROM playbook ORDER BY machine_model, symptom_code"
        )
        return [
            PricedPair(
                symptom_code=SymptomCode(row[0]),
                machine_model=MachineModel(row[1]),
                estimated_minutes=int(row[2]),
                status=PlaybookStatus(row[3]),
            )
            for row in cur.fetchall()
        ]


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
    # Every approved playbook passes here - approval, seeds, anything set through
    # the contract - so the energy marks are checked here and not only at the
    # review screen (REQ-H-05, ADR-137 B5).
    problems = energy_problems(playbook.steps)
    if problems:
        raise ValueError("; ".join(problems))

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO playbook (
                symptom_code, machine_model, steps, tools, tools_th, parts,
                estimated_minutes, required_skill, required_technicians,
                source_doc, page, cited_documents, revision, status,
                review_reason, approved_by, approved_at, approver_role
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 'approved',
                    NULL, %s, %s, %s)
            ON CONFLICT (symptom_code, machine_model) DO UPDATE SET
                steps                = EXCLUDED.steps,
                tools                = EXCLUDED.tools,
                tools_th             = EXCLUDED.tools_th,
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
                list(playbook.tools_th),
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
             -- Containment rather than `= ANY`, which cannot use the GIN index
             -- migration 0005 created for exactly this query. On two playbooks
             -- the difference is nothing; on a plant's worth of them the cascade
             -- is a sequential scan inside the transaction an operator is
             -- waiting on.
             WHERE cited_documents @> ARRAY[%s]::text[]
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


def pending_by_pair(conn: Connection[Any]) -> list[PendingForPair]:
    """What the review queue holds, counted per pair rather than listed.

    The queue itself is `queue()`, bounded and ordered for a person to work
    through. This is the same rows asked a different question - how much is
    waiting, and since when - so the overview can report the size of the queue
    without loading it (ADR-050: computed when asked, from the rows that are
    already there).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT symptom_code, machine_model,
                   count(*) AS waiting, min(created_at) AS oldest,
                   count(*) FILTER (WHERE outcome = 'not_found') AS not_found
              FROM playbook_proposal
             WHERE status = 'pending'
             GROUP BY symptom_code, machine_model
            """
        )
        rows = cur.fetchall()
    return [PendingForPair.model_validate(row) for row in rows]


def awaiting_review(
    conn: Connection[Any], *, symptom_code: SymptomCode, machine_model: MachineModel
) -> int | None:
    """The proposal already waiting for a decision on this pair, if there is one.

    `pending_by_pair` answers this for every pair at once, which is what the
    overview needs and what the drafting endpoint would be loading the whole
    queue to read one row of. Oldest first, so the answer is the one that has
    been waiting longest rather than whichever the planner returned.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT proposal_id FROM playbook_proposal "
            "WHERE status = 'pending' AND symptom_code = %s AND machine_model = %s "
            "ORDER BY created_at, proposal_id LIMIT 1",
            (str(symptom_code), str(machine_model)),
        )
        row = cur.fetchone()
    return int(row[0]) if row is not None else None


def ever_proposed(
    conn: Connection[Any], *, symptom_code: SymptomCode, machine_model: MachineModel
) -> bool:
    """Whether anything has ever been filed for this pair, in any state (ADR-121).

    The test for asking by itself: once a draft has been filed - approved,
    dismissed, sent back or "not found" - the next one is a person's decision,
    not the loop's, or every new Finding of an unanswered symptom would ask again.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM playbook_proposal "
            "WHERE symptom_code = %s AND machine_model = %s LIMIT 1",
            (str(symptom_code), str(machine_model)),
        )
        return cur.fetchone() is not None


def proposal(conn: Connection[Any], proposal_id: int) -> Proposal | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_PROPOSAL_COLUMNS} FROM playbook_proposal WHERE proposal_id = %s",
            (proposal_id,),
        )
        row = cur.fetchone()
    return _to_proposal(row) if row else None


def opened(conn: Connection[Any], proposal_id: int, *, at: datetime) -> None:
    """Somebody who may review this has just looked at it.

    Written on every read of the detail rather than only the first, so what the
    decision is measured against is the sitting it was made in. A proposal
    opened on Monday and decided on Thursday would otherwise report three days
    of review, which is a number that would make the median meaningless and the
    mean absurd (ADR-064).

    Only `pending` rows move: reading a decided proposal is reading history, and
    it must not restate when the decision that is already recorded was taken.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE playbook_proposal SET opened_at = %s "
            "WHERE proposal_id = %s AND status = 'pending'",
            (at, proposal_id),
        )


def decide(
    conn: Connection[Any],
    proposal_id: int,
    *,
    status: ProposalStatus,
    decided_by: UserId,
    decided_at: datetime,
    note: str | None,
    edits: tuple[StepEdit, ...] = (),
) -> Proposal:
    """Record that a person looked at this and what they concluded.

    The `WHERE status = 'pending'` is what makes deciding twice impossible: the
    second call finds no row and raises, rather than overwriting the first
    person's decision with the second's.

    `review_seconds` is computed in the same statement, from the row's own
    `opened_at` and the decision time the caller passes - both from the Clock
    (ADR-028). Reading the open time out and subtracting in Python would be the
    same arithmetic across two statements, with room between them for the read
    that moves `opened_at` on. Null when the proposal was decided without the
    detail ever being opened, which is a real thing to be able to say: it is an
    approval made without the evidence panel in front of anybody (ADR-064).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE playbook_proposal
               SET status = %s, decided_by = %s, decided_at = %s, decision_note = %s,
                   edits = %s,
                   review_seconds = CASE
                       WHEN opened_at IS NULL THEN NULL
                       -- greatest(0, ...) rather than a bare subtraction: a
                       -- SimulatedClock can be wound back between the open and
                       -- the decision, and the column refuses a negative.
                       ELSE greatest(0, extract(epoch FROM (%s - opened_at))::integer)
                   END
             WHERE proposal_id = %s AND status = 'pending'
            RETURNING """
            + _PROPOSAL_COLUMNS,
            (
                status.value,
                decided_by,
                decided_at,
                note,
                Jsonb([edit.model_dump(mode="json") for edit in edits]),
                decided_at,
                proposal_id,
            ),
        )
        row = cur.fetchone()
    if row is None:
        raise NothingToApply(f"proposal {proposal_id} is not pending")
    return _to_proposal(row)

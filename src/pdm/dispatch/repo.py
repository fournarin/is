"""SQL for the world a round reads and the decision it writes.

`domain.py` is a pure function and must stay one (invariant 10, ADR-045 §6), so
everything that touches a connection is here. Every function takes the
connection first (ADR-031), which is what lets a whole round - the reading, the
writing and the appointment for the next one - commit or roll back together
(ADR-017).

**A round writes only to orders it is placing.** Work somebody has accepted is
read, because it consumes their capacity, and is never written back
(ADR-045 §4). The UPDATE below says so in its WHERE clause rather than trusting
the caller to have filtered: a round that re-assigned an order under a
technician already walking to a machine is the failure design.md 6.2 exists to
prevent, and it would look like a successful round.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pdm.contracts import (
    Assignee,
    Role,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderStatus,
)
from pdm.dispatch.domain import Placement
from pdm.dispatch.overrides import Override, OverrideKind
from pdm.dispatch.proposals import Proposal, ProposalState


def technicians(conn: Connection[Any]) -> list[Technician]:
    """Everybody the plant employs, active or not.

    The inactive are returned rather than filtered here because `dispatch()`
    filters them itself, and a repository that pre-filtered would be deciding
    part of the answer - the same argument that keeps `open_orders` from sorting
    by severity.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT user_id, skills, active FROM technician ORDER BY user_id")
        rows = cur.fetchall()
    return [
        Technician(
            user=UserId(str(row["user_id"])),
            skills=frozenset(SkillId(skill) for skill in row["skills"]),
            active=bool(row["active"]),
        )
        for row in rows
    ]


def roster(conn: Connection[Any], *, shift_id: ShiftId, on_date: date) -> list[ShiftAssignment]:
    """Who is on this shift on this day, and for how many minutes each.

    `on_date` is the local date the shift started on: Monday night's shift runs
    into Tuesday and is filed under Monday (ADR-045 §7). Passing Tuesday would
    return an empty roster, which the round reports as no capacity rather than
    as an empty queue - loud, but wrong, so the caller resolves the date with
    `shift_at` rather than from a wall clock.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT shift_id, on_date, technician, available_minutes
              FROM shift_assignment
             WHERE on_date = %s AND shift_id = %s
             ORDER BY technician
            """,
            (on_date, shift_id),
        )
        rows = cur.fetchall()
    return [ShiftAssignment.model_validate(dict(row)) for row in rows]


def place(conn: Connection[Any], placement: Placement, *, status: WorkOrderStatus) -> bool:
    """Write one placement onto its order, if it is still queued.

    The `status = 'queued'` in the WHERE clause is the idempotence: a round that
    dies after `dispatch()` and before its commit leaves nothing behind, and a
    round replayed against a queue somebody has since accepted from writes
    nothing over the top of them. False means the order moved while the round
    was deciding, which is a fact for the caller to report rather than an error -
    the next round will rank it again from what is true then.

    `priority_score` and `priority_reason` are written beside the assignment
    because they are the answer to "why is this job here, now" and ADR-005 wants
    it on the screen where the job is, not recomputed by whoever asks.

    The status to write is the caller's, and it is the only difference between
    the two confirmation modes (ADR-071 section 2): `assigned` hands the job
    straight to a technician, `proposed` holds the same decision still until a
    supervisor agrees to it. Everything else about the round - what it decided,
    how it scored it, who it crewed it with - is identical in both, which is
    what stops the mode the plant eventually runs in from being the one least
    tested.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE work_order
               SET status = %s,
                   assignees = %s,
                   priority_score = %s,
                   priority_reason = %s
             WHERE work_order_ref = %s AND status = 'queued'
            """,
            (
                status.value,
                Jsonb([_assignee(one) for one in placement.assignees]),
                placement.priority_score,
                placement.priority_reason,
                placement.ref,
            ),
        )
        return cur.rowcount == 1


def record_override(conn: Connection[Any], override: Override) -> None:
    """Write down that a person overruled layer 3, and against what (ADR-059).

    In the request's transaction, like every other write here, so an override
    that was recorded is an override that happened: a release committed without
    its record would change the next round with nothing to explain why, which is
    the state ADR-005 exists to prevent.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_order_override
                   (at, kind, work_order_ref, user_id, role, reason,
                    band, load_ratio, shift_id, on_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                override.at,
                override.kind.value,
                override.work_order_ref,
                str(override.user),
                override.role.value,
                override.reason,
                override.band.value if override.band is not None else None,
                override.load_ratio,
                str(override.shift_id) if override.shift_id is not None else None,
                override.on_date,
            ),
        )


def released(conn: Connection[Any]) -> set[str]:
    """The orders a shift lead has taken out of the gate's hands.

    A release has no expiry, and that is the decision rather than an omission
    (ADR-059): "do this job" stays true until the job is done, and any lifetime
    put on it would be a constant with nothing behind it. It stops mattering on
    its own, because a round only ranks orders that are still queued and a
    released order that gets placed is not one of those any more.

    A set rather than a list: the caller asks it one question, per order, and the
    only thing an ordering here could do is reach an output somewhere else.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT work_order_ref FROM work_order_override WHERE kind = %s",
            (OverrideKind.RELEASE_HELD.value,),
        )
        return {str(row[0]) for row in cur.fetchall()}


def propose(conn: Connection[Any], proposal: Proposal) -> None:
    """Ask a supervisor about one placement (ADR-071).

    In the round's transaction, beside the `place` that put the order into
    `proposed`. The two commit together or not at all: an order held in a state
    only a confirmation can leave, with nothing asking anybody to confirm it,
    would be work that has quietly stopped existing.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO dispatch_proposal
                   (work_order_ref, proposed_at, assignees, priority_score,
                    priority_reason, band, load_ratio, shift_id, on_date, state)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            """,
            (
                proposal.work_order_ref,
                proposal.proposed_at,
                Jsonb([_assignee(one) for one in proposal.assignees]),
                proposal.priority_score,
                proposal.priority_reason,
                proposal.band.value if proposal.band is not None else None,
                proposal.load_ratio,
                str(proposal.shift_id) if proposal.shift_id is not None else None,
                proposal.on_date,
            ),
        )


def pending_proposals(conn: Connection[Any]) -> list[Proposal]:
    """Everything waiting for an answer, oldest first.

    Oldest first because that is the order a supervisor should work through and
    the order the sweep will take them in: the one nearest expiry is the one
    nearest being decided by nobody.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PROPOSAL_COLUMNS} FROM dispatch_proposal
             WHERE state = 'pending' ORDER BY priority_score DESC, proposed_at, proposal_id
            """
        )
        return [_to_proposal(dict(row)) for row in cur.fetchall()]


def proposal_record(
    conn: Connection[Any], *, since: datetime | None = None, until: datetime | None = None
) -> list[Proposal]:
    """Every proposal in a window, oldest first, whatever became of it (ADR-075).

    Pending rows are returned with the settled ones because a reading that
    dropped them could not say how much of the record is still open, and a report
    written on a quiet afternoon would look like a shift lead who had answered
    everything.

    The window is the caller's, and it has no default. How much history is enough
    to argue from is exactly the judgement ADR-071 §8 refuses to let this project
    make on a plant's behalf, and a default here would make it silently.

    Bounded on `proposed_at` rather than `decided_at`: the question is what a
    shift lead was asked during a stretch of time, and a proposal answered after
    the window closed still belongs to the shift that was asked about it.
    """
    where = " AND ".join(
        clause
        for clause, wanted in (("proposed_at >= %s", since), ("proposed_at < %s", until))
        if wanted is not None
    )
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PROPOSAL_COLUMNS} FROM dispatch_proposal
            {f"WHERE {where}" if where else ""}
             ORDER BY proposed_at, proposal_id
            """,
            tuple(one for one in (since, until) if one is not None),
        )
        return [_to_proposal(dict(row)) for row in cur.fetchall()]


def pending_proposal(conn: Connection[Any], work_order_ref: str) -> Proposal | None:
    """The open question about one order, or None.

    None covers both "there never was one" and "somebody has already answered
    it", which the caller reports differently: the second is two supervisors on
    the same screen, and it deserves a sentence rather than a 404.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_PROPOSAL_COLUMNS} FROM dispatch_proposal
             WHERE work_order_ref = %s AND state = 'pending'
            """,
            (work_order_ref,),
        )
        row = cur.fetchone()
    return _to_proposal(dict(row)) if row is not None else None


def settle_proposal(
    conn: Connection[Any],
    work_order_ref: str,
    *,
    state: ProposalState,
    at: datetime,
    by: UserId | None = None,
    role: Role | None = None,
    reason: str | None = None,
) -> bool:
    """Write down how a proposal ended. False if somebody got there first.

    The `state = 'pending'` in the WHERE clause is what makes two supervisors
    pressing at once safe: the second UPDATE matches nothing, and the caller
    reports that rather than overwriting the first answer with the second.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dispatch_proposal
               SET state = %s, decided_at = %s, decided_by = %s,
                   decided_role = %s, reason = %s
             WHERE work_order_ref = %s AND state = 'pending'
            """,
            (
                state.value,
                at,
                str(by) if by is not None else None,
                role.value if role is not None else None,
                reason,
                work_order_ref,
            ),
        )
        return cur.rowcount == 1


def expire_proposals(
    conn: Connection[Any], *, proposed_before: datetime, at: datetime
) -> list[str]:
    """Sweep the proposals nobody answered, and return the orders they held.

    Called at the start of a round, in the round's transaction, before it decides
    (ADR-071 §6) - so the queue the round is handed already contains what the
    sweep let go, and a supervisor who went home does not leave a shift committed
    to work nobody agreed to.

    The orders are returned to the queue by the caller rather than here, because
    the two writes are different sentences: this one says the question went
    unanswered, and that one says the work is available again.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dispatch_proposal
               SET state = %s, decided_at = %s
             WHERE state = 'pending' AND proposed_at < %s
         RETURNING work_order_ref
            """,
            (ProposalState.EXPIRED.value, at, proposed_before),
        )
        return [str(row[0]) for row in cur.fetchall()]


def withdraw_pending(conn: Connection[Any], work_order_refs: list[str], *, at: datetime) -> int:
    """Close the question on orders that were withdrawn while it was open.

    A prediction overtaken by its detection has its ticket cancelled (ADR-023
    §7). A pending proposal left behind would still sit on the shift lead's
    board, for work that no longer exists. Recorded as `expired`: nobody
    answered it, and the Finding the order points at says why it went.
    """
    if not work_order_refs:
        return 0
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE dispatch_proposal
               SET state = %s, decided_at = %s
             WHERE state = 'pending' AND work_order_ref = ANY(%s)
            """,
            (ProposalState.EXPIRED.value, at, work_order_refs),
        )
        return cur.rowcount


def return_to_queue(conn: Connection[Any], work_order_ref: str) -> bool:
    """Undo a placement nobody agreed to, and take the crew off it with it.

    The assignees go because they are the present tense of who holds the job
    (ADR-056), and an order sitting in the queue with somebody's name on it would
    be counted against their capacity by the next round and offered to them by
    `accept`. The score and its sentence are left: the next round overwrites both,
    and clearing them would make an order that has been proposed once read as one
    that has never been ranked.

    `status = 'proposed'` in the WHERE clause for the same reason `place` names
    `queued`: whatever else has happened to this order since, this write is only
    ever allowed to undo a proposal.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE work_order
               SET status = %s, assignees = '[]'::jsonb
             WHERE work_order_ref = %s AND status = %s
            """,
            (WorkOrderStatus.QUEUED.value, work_order_ref, WorkOrderStatus.PROPOSED.value),
        )
        return cur.rowcount == 1


def confirm_placement(conn: Connection[Any], work_order_ref: str) -> bool:
    """A proposal becomes a technician's job. False if it is no longer proposed."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE work_order SET status = %s WHERE work_order_ref = %s AND status = %s",
            (
                WorkOrderStatus.ASSIGNED.value,
                work_order_ref,
                WorkOrderStatus.PROPOSED.value,
            ),
        )
        return cur.rowcount == 1


_PROPOSAL_COLUMNS = """
    work_order_ref, proposed_at, assignees, priority_score, priority_reason,
    band, load_ratio, shift_id, on_date, state, decided_at, decided_by,
    decided_role, reason
"""


def _to_proposal(row: dict[str, Any]) -> Proposal:
    row["assignees"] = tuple(Assignee.model_validate(one) for one in row["assignees"])
    return Proposal.model_validate(row)


def _assignee(one: Assignee) -> dict[str, str]:
    return {"user": str(one.user), "role": one.role.value}


class SkillNotInTheVocabulary(ValueError):
    """A technician holding a label `plant.yaml` does not declare (invariant 13)."""


def add_technician(
    conn: Connection[Any],
    technician: Technician,
    *,
    known_skills: Collection[SkillId],
    now: Any,
) -> None:
    """Upsert one technician. The roster is maintained elsewhere; this exists so
    that something can put people in the table before an API does.

    `known_skills` is the vocabulary from `plant.yaml` and has no default on
    purpose (invariant 13, ADR-084 §3). Until ADR-084 this function wrote
    whatever it was given, and a label outside the vocabulary fails in the
    quietest way this system has: `can_perform` never matches, so the person is
    simply never assigned anything, and no round, screen or log says why. A
    default of `()` would have made the check skippable by forgetting, which is
    how it came to be missing in the first place.
    """
    unknown = sorted(str(skill) for skill in technician.skills if skill not in known_skills)
    if unknown:
        raise SkillNotInTheVocabulary(
            f"{technician.user} holds {', '.join(unknown)}, which plant.yaml does not declare "
            f"({', '.join(sorted(str(skill) for skill in known_skills)) or 'no skills at all'}). "
            "A skill no playbook can ask for is a technician dispatch will never match to any "
            "work, and nothing would say so (invariant 13, ADR-027)"
        )
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO technician (user_id, skills, active, created_at)
                 VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
                    SET skills = EXCLUDED.skills, active = EXCLUDED.active
            """,
            (
                str(technician.user),
                Jsonb(sorted(str(skill) for skill in technician.skills)),
                technician.active,
                now,
            ),
        )


def assign_to_shift(conn: Connection[Any], assignment: ShiftAssignment) -> None:
    """Upsert one roster line, for the same reason as `add_technician`."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO shift_assignment (shift_id, on_date, technician, available_minutes)
                 VALUES (%s, %s, %s, %s)
            ON CONFLICT (shift_id, on_date, technician) DO UPDATE
                    SET available_minutes = EXCLUDED.available_minutes
            """,
            (
                str(assignment.shift_id),
                assignment.on_date,
                str(assignment.technician),
                assignment.available_minutes,
            ),
        )

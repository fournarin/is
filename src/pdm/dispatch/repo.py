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

from datetime import date
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pdm.contracts import (
    Assignee,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderStatus,
)
from pdm.dispatch.domain import Placement


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


def place(conn: Connection[Any], placement: Placement) -> bool:
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
                WorkOrderStatus.ASSIGNED.value,
                Jsonb([_assignee(one) for one in placement.assignees]),
                placement.priority_score,
                placement.priority_reason,
                placement.ref,
            ),
        )
        return cur.rowcount == 1


def _assignee(one: Assignee) -> dict[str, str]:
    return {"user": str(one.user), "role": one.role.value}


def add_technician(conn: Connection[Any], technician: Technician, *, now: Any) -> None:
    """Upsert one technician. The roster is maintained elsewhere; this exists so
    that something can put people in the table before an API does."""
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

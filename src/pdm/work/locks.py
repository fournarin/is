"""Isolation confirmed point by point, and the register of locks (ADR-135).

The rules are pure functions over the steps an order was issued with and what
has been confirmed, so they can be asserted without a database; the register is
plain SQL beside them.

What a step needs before the job moves past it comes only from what the
approving engineer marked (`PlaybookStep.kind`), never from the words of the
step (REQ-H-02):

  isolation  every point switched off, then a personal lock and tag on it
  verify     every point checked at zero energy
  restore    every point's lock taken off by its owner
  hazard     with `wait_minutes`, that long since the step was reached
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from pdm.contracts import LockState, MachineId, PlaybookStep, StepKind, UserId

_FROZEN = ConfigDict(frozen=True)

# What each kind of step asks for, per point, in order.
ITEMS: dict[StepKind, tuple[str, ...]] = {
    StepKind.ISOLATION: ("off", "locked"),
    StepKind.VERIFY: ("verified",),
    StepKind.RESTORE: ("released",),
}
WAIT_STARTED = "wait_started"


class Confirmation(BaseModel):
    model_config = _FROZEN

    step: int
    point_id: str
    item: str
    confirmed_by: UserId
    confirmed_at: datetime


class Lock(BaseModel):
    model_config = _FROZEN

    lock_id: int
    work_order_ref: str
    machine_id: MachineId
    point_id: str
    lock_no: str
    owner: UserId
    step: int
    applied_at: datetime


# ─────────────────────────────────────────────────────────────
# The rules
# ─────────────────────────────────────────────────────────────


def wait_ends(step: PlaybookStep, number: int, done: Iterable[Confirmation]) -> datetime | None:
    """When a waiting hazard step may be left, or None if its clock has not started."""
    if step.wait_minutes is None:
        return None
    for one in done:
        if one.step == number and one.item == WAIT_STARTED:
            return one.confirmed_at + timedelta(minutes=step.wait_minutes)
    return None


def still_needed(
    step: PlaybookStep, number: int, done: Sequence[Confirmation], *, now: datetime
) -> list[tuple[str, str]]:
    """The (point, item) pairs this step still needs, in the order they are confirmed."""
    have = {(one.point_id, one.item) for one in done if one.step == number}
    needed = [
        (point.point_id, item)
        for point in step.isolation_points
        for item in ITEMS.get(step.kind, ())
        if (point.point_id, item) not in have
    ]
    if step.wait_minutes is not None:
        ends = wait_ends(step, number, done)
        if ends is None or now < ends:
            needed.append(("", WAIT_STARTED))
    return needed


def first_unfinished(
    steps: Sequence[PlaybookStep], done: Sequence[Confirmation], *, before: int, now: datetime
) -> tuple[int, list[tuple[str, str]]] | None:
    """The first step before `before` (1-based) that still needs something, if any."""
    for number, step in enumerate(steps[: max(0, before - 1)], start=1):
        missing = still_needed(step, number, done, now=now)
        if missing:
            return number, missing
    return None


def missing_verify(steps: Sequence[PlaybookStep]) -> bool:
    """An isolation step with no verify step after it (REQ-H-05).

    OSHA 1910.147 puts "verify zero energy" between isolating and working. An
    approved playbook that skips it is shown with a stop bar rather than worked
    as if it were complete.
    """
    for index, step in enumerate(steps):
        if step.kind is StepKind.ISOLATION and not any(
            later.kind is StepKind.VERIFY for later in steps[index + 1 :]
        ):
            return True
    return False


def lock_state_refused(
    answer: LockState | None, *, mine: Sequence[Lock], on_this_job: Sequence[Lock]
) -> str | None:
    """Why the register contradicts this answer about locks, or None if it does not.

    The register is the record and the answer has to agree with it: "my locks
    are off" while one of yours is still on the breaker is the sentence that
    gets somebody hurt (REQ-H-06). No answer at all is accepted only from a job
    with none of your locks on it, so a caller that predates the question still
    works where the question cannot matter.
    """
    if answer is LockState.RELEASED and mine:
        return f"กุญแจ {_named(mine)} ของคุณยังล็อกอยู่ ปลดในขั้นคืนพลังงานก่อน หรือเลือก “ยังล็อกอยู่”"
    if answer is LockState.NOT_ISOLATED and on_this_job:
        return f"ทะเบียนมีกุญแจ {_named(on_this_job)} ในงานนี้ จึงเลือก “งานนี้ไม่ได้ตัดพลังงาน” ไม่ได้"
    if answer is LockState.STILL_LOCKED and not on_this_job:
        return "ทะเบียนไม่มีกุญแจที่ยังล็อกอยู่ในงานนี้"
    if answer is None and mine:
        return f"กุญแจ {_named(mine)} ของคุณยังล็อกอยู่ ตอบสถานะกุญแจก่อน"
    return None


def lock_line(answer: LockState | None, reason: str | None, locks: Sequence[Lock]) -> str | None:
    """The line put at the top of the note, so the answer travels with it (REQ-H-06)."""
    if answer is None:
        return None
    if answer is LockState.RELEASED:
        return "สถานะกุญแจ: ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต"
    if answer is LockState.NOT_ISOLATED:
        return "สถานะกุญแจ: งานนี้ไม่ได้ตัดพลังงาน"
    why = f" · เหตุ: {reason.strip()}" if reason and reason.strip() else ""
    return f"สถานะกุญแจ: ยังล็อกอยู่ {_named(locks)}{why}"


def _named(locks: Sequence[Lock]) -> str:
    return ", ".join(f"{one.lock_no} ที่ {one.point_id}" for one in locks)


# ─────────────────────────────────────────────────────────────
# The register
# ─────────────────────────────────────────────────────────────


def confirmations(conn: Connection[Any], work_order_ref: str) -> list[Confirmation]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT step, point_id, item, confirmed_by, confirmed_at FROM step_confirmation
             WHERE work_order_ref = %s
             ORDER BY confirmed_at, step, point_id,
                      array_position(
                          ARRAY['wait_started', 'off', 'locked', 'verified', 'released'], item
                      )
            """,
            (work_order_ref,),
        )
        return [Confirmation.model_validate(row) for row in cur.fetchall()]


def confirm(
    conn: Connection[Any],
    work_order_ref: str,
    *,
    step: int,
    point_id: str,
    item: str,
    user: UserId,
    now: datetime,
) -> None:
    """Record one confirmation. A second tap of the same one is not a second statement."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO step_confirmation
                   (work_order_ref, step, point_id, item, confirmed_by, confirmed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (work_order_ref, step, point_id, item, user, now),
        )


_LOCK_COLUMNS = "lock_id, work_order_ref, machine_id, point_id, lock_no, owner, step, applied_at"


def open_locks(
    conn: Connection[Any], *, machine_id: MachineId | None = None, work_order_ref: str | None = None
) -> list[Lock]:
    """Locks still on, on one machine or on one job's points."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_LOCK_COLUMNS} FROM lock_record
             WHERE released_at IS NULL
               AND (%(machine)s::text IS NULL OR machine_id = %(machine)s)
               AND (%(ref)s::text IS NULL OR work_order_ref = %(ref)s)
             ORDER BY applied_at, lock_id
            """,
            {"machine": machine_id, "ref": work_order_ref},
        )
        return [Lock.model_validate(row) for row in cur.fetchall()]


def apply_lock(
    conn: Connection[Any],
    *,
    work_order_ref: str,
    machine_id: MachineId,
    point_id: str,
    lock_no: str,
    owner: UserId,
    step: int,
    now: datetime,
) -> bool:
    """Put a lock on a point. False when that lock number is already on another point."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO lock_record
                   (work_order_ref, machine_id, point_id, lock_no, owner, step, applied_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (lock_no) WHERE released_at IS NULL DO NOTHING
            RETURNING {_LOCK_COLUMNS}
            """,
            (work_order_ref, machine_id, point_id, lock_no.strip(), owner, step, now),
        )
        return cur.fetchone() is not None


def release_lock(
    conn: Connection[Any], *, work_order_ref: str, point_id: str, owner: UserId, now: datetime
) -> bool:
    """Take the owner's lock off a point. Only the owner's: nobody removes another's lock."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE lock_record SET released_at = %s
             WHERE work_order_ref = %s AND point_id = %s AND owner = %s AND released_at IS NULL
            """,
            (now, work_order_ref, point_id, owner),
        )
        return cur.rowcount > 0


def lock_numbers_of(conn: Connection[Any], user: UserId, *, limit: int = 4) -> list[str]:
    """The lock numbers this person has used, most recent first, for one-tap choices."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT lock_no FROM lock_record WHERE owner = %s
             GROUP BY lock_no ORDER BY max(applied_at) DESC, lock_no LIMIT %s
            """,
            (user, limit),
        )
        return [str(row[0]) for row in cur.fetchall()]

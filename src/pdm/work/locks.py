"""Isolation confirmed point by point, and the register of locks (ADR-135, ADR-136).

The rules are pure functions over the steps an order was issued with, what has
been confirmed, and which locks are on now, so they can be asserted without a
database; the register is plain SQL beside them.

What a step needs before somebody works past it comes only from what the
approving engineer marked (`PlaybookStep.kind`), never from the words of the
step (REQ-H-02), and for the person asking (ADR-136, group lockout):

  isolation  every point switched off (by anybody), then **your own** lock on
             it - on now, not once: a lock taken off early opens the step again
  verify     every point checked at zero energy, by you
  restore    the plant's restore checks (policy.yaml), then every lock on its
             points off - each by its owner
  hazard     with `wait_minutes`, that long since the step was reached

An isolation step stops asking for your lock once the job is past a restore
step for that point, because that is where the lock is meant to come off.
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

# The items a confirmation can be, by the kind of step that takes it.
ITEMS: dict[StepKind, tuple[str, ...]] = {
    StepKind.ISOLATION: ("off", "locked"),
    StepKind.VERIFY: ("verified",),
    StepKind.RESTORE: ("checked", "released"),
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
    step: PlaybookStep,
    number: int,
    done: Sequence[Confirmation],
    *,
    now: datetime,
    user: UserId,
    locks_on: Sequence[Lock],
    checks: Sequence[str] = (),
    restored: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    """The (point, item) pairs this step still needs from `user`, in order.

    `locks_on` are the locks on this job now; `restored` the points whose restore
    step the job is already past, where a lock is no longer asked for.
    """
    here = [one for one in done if one.step == number]
    by_anybody = {(one.point_id, one.item) for one in here}
    by_you = {(one.point_id, one.item) for one in here if one.confirmed_by == user}
    yours_on = {one.point_id for one in locks_on if one.owner == user}
    any_on = {one.point_id for one in locks_on}
    needed: list[tuple[str, str]] = []
    points = [point.point_id for point in step.isolation_points]
    if step.kind is StepKind.ISOLATION:
        for point in points:
            if (point, "off") not in by_anybody:
                needed.append((point, "off"))
            if point not in yours_on and point not in restored:
                needed.append((point, "locked"))
    elif step.kind is StepKind.VERIFY:
        needed += [(point, "verified") for point in points if (point, "verified") not in by_you]
    elif step.kind is StepKind.RESTORE:
        needed += [(check, "checked") for check in checks if (check, "checked") not in by_anybody]
        needed += [(point, "released") for point in points if point in any_on]
    if step.wait_minutes is not None:
        ends = wait_ends(step, number, done)
        if ends is None or now < ends:
            needed.append(("", WAIT_STARTED))
    return needed


def restored_points(steps: Sequence[PlaybookStep], *, before: int) -> frozenset[str]:
    """Points whose restore step comes before `before` (1-based): their locks may be off."""
    return frozenset(
        point.point_id
        for step in steps[: max(0, before - 1)]
        if step.kind is StepKind.RESTORE
        for point in step.isolation_points
    )


def first_unfinished(
    steps: Sequence[PlaybookStep],
    done: Sequence[Confirmation],
    *,
    before: int,
    now: datetime,
    user: UserId,
    locks_on: Sequence[Lock],
    checks: Sequence[str] = (),
) -> tuple[int, list[tuple[str, str]]] | None:
    """The first step before `before` (1-based) that still needs something from `user`."""
    restored = restored_points(steps, before=before)
    for number, step in enumerate(steps[: max(0, before - 1)], start=1):
        missing = still_needed(
            step,
            number,
            done,
            now=now,
            user=user,
            locks_on=locks_on,
            checks=checks,
            restored=restored,
        )
        if missing:
            return number, missing
    return None


def lock_state_refused(
    answer: LockState | None,
    *,
    on_job: Sequence[Lock],
    on_machine: Sequence[Lock],
    you_locked_here: bool,
    anybody_locked_here: bool,
) -> str | None:
    """Why the register contradicts this answer about locks, or None if it does not.

    The register is the record and the answer has to agree with it (REQ-H-06):

    - no answer, while **anybody's** lock is on the job - whoever took over may
      not close past somebody else's lock without saying so (red line 3);
    - "my locks are off, the machine goes back to production", while any lock is
      on the machine - another person's, or another job's on the same machine -
      or from somebody who never locked here;
    - "not isolated", for a job where anybody locked anything;
    - "still locked", with nothing on.
    """
    if answer is None and on_job:
        return f"ในทะเบียนยังมีกุญแจ {_named(on_job)} ในงานนี้ ตอบสถานะกุญแจก่อน"
    if answer is LockState.RELEASED:
        if on_machine:
            return (
                f"ในทะเบียนยังมีกุญแจ {_named(on_machine)} ที่เครื่องนี้ เครื่องยังคืนสู่การผลิตไม่ได้ เลือก “ยังล็อกอยู่”"
            )
        if not you_locked_here:
            return "คุณไม่ได้ใส่กุญแจในงานนี้ เลือก “ปลดกุญแจแล้ว” ไม่ได้"
    if answer is LockState.NOT_ISOLATED and (on_job or anybody_locked_here):
        return "ทะเบียนบันทึกว่ามีการใส่กุญแจในงานนี้ จึงเลือก “งานนี้ไม่ได้ตัดพลังงาน” ไม่ได้"
    if answer is LockState.STILL_LOCKED and not on_job:
        return "ทะเบียนไม่มีกุญแจที่ยังล็อกอยู่ในงานนี้"
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
    conn: Connection[Any],
    *,
    work_order_ref: str,
    point_id: str,
    owner: UserId,
    now: datetime,
    reason: str = "restore step",
) -> bool:
    """Take the owner's lock off a point. Only the owner's: nobody removes another's lock."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE lock_record SET released_at = %s, release_reason = %s
             WHERE work_order_ref = %s AND point_id = %s AND owner = %s AND released_at IS NULL
            """,
            (now, reason, work_order_ref, point_id, owner),
        )
        return cur.rowcount > 0


def release_own(
    conn: Connection[Any], lock_id: int, *, owner: UserId, now: datetime, reason: str
) -> Lock | None:
    """The owner takes their own lock off, from wherever they are (ADR-136, B3).

    After a handover or a "still locked" close the owner no longer holds the job,
    and the lock is still theirs: this is how the register records it coming off.
    None when it is not this person's lock, or is already off.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            UPDATE lock_record SET released_at = %s, release_reason = %s
             WHERE lock_id = %s AND owner = %s AND released_at IS NULL
            RETURNING {_LOCK_COLUMNS}
            """,
            (now, reason, lock_id, owner),
        )
        row = cur.fetchone()
    return Lock.model_validate(row) if row else None


def locks_of(conn: Connection[Any], owner: UserId) -> list[Lock]:
    """This person's locks still on, anywhere."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_LOCK_COLUMNS} FROM lock_record"
            " WHERE owner = %s AND released_at IS NULL ORDER BY applied_at, lock_id",
            (owner,),
        )
        return [Lock.model_validate(row) for row in cur.fetchall()]


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

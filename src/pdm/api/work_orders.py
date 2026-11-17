"""Reporting a fault, and the four buttons a technician has: accept, start, hand
over, close.

Until this router existed a work order could be created, priced, ranked and
released, and then nothing: `actual_minutes` was zero on every order in the
system, `handed_over` was a status with no evidence behind it, and the feedback
loop ADR-006 describes had no input at all.

**Technicians only** (ADR-024's table: *accept and close work - technician*).
Checked here, at the endpoint, rather than by hiding buttons - an engineer who
found the URL is refused and recorded, which is invariant 6 and the same rule the
approval endpoint enforces from the other side.

Nothing here decides anything about the *queue*. Which job comes first is layer
3's answer and this router does not touch it; what it writes is what a person did
with the job they were given.

**Reporting is the one route here that any role may call** (ADR-077). The four
buttons are a technician's alone; telling the system about a fault is not, and
the person standing next to the machine when it starts making a noise is as
likely to be an operator. What the reporting route refuses is a severity a
report may not carry, a machine this plant does not have, and a second ticket
for work already open.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.api.deps import Db, Plant, Time, authentication, requires
from pdm.contracts import (
    BlockedReason,
    LockState,
    MachineId,
    Role,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.platform.auth import repo as auth_repo
from pdm.platform.auth.domain import Account
from pdm.platform.auth.service import Authentication
from pdm.work import AlreadyOpen, NoSuchOrder, TransitionRefused, WorkOrders, locks
from pdm.work import repo as work_repo

router = APIRouter(tags=["work orders"])

# ADR-024. An engineer approves the playbook and does not take the job; a
# supervisor releases what the gate is holding and does not take it either.
_MAY_WORK = (Role.TECHNICIAN,)

# ADR-077 section 1. Every role, because a fault is seen by whoever is standing
# there, and because nothing is dispatched on a report alone: a round proposes it
# and a shift lead confirms it (ADR-071). Authentication is still required - the
# reason names the reporter, and a report nobody can be asked about is one
# nobody can settle.
_MAY_REPORT = (Role.TECHNICIAN, Role.ENGINEER, Role.SUPERVISOR, Role.OPERATOR)


def _orders(request: Request) -> WorkOrders:
    return request.app.state.work_orders  # type: ignore[no-any-return]


Orders = Annotated[WorkOrders, Depends(_orders)]


class Handover(BaseModel):
    """ADR-025's note, required by the schema so the request never reaches the
    code that would have to decide what an empty one means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str = Field(min_length=1)
    # What is still locked goes over with the job (REQ-H-06, ADR-135).
    lock_state: LockState | None = None
    lock_reason: str | None = None

    @field_validator("note")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", and a note of spaces leaves the next shift
        exactly where no note would: starting again from step one."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("โน้ตส่งต่องานต้องมีข้อความ ไม่ใช่ช่องว่าง")
        return stripped


class Closing(BaseModel):
    """How the job ended, and what of the elapsed time was not repair.

    **No field asks for a duration.** It is the sum of the segments that "start"
    and "hand over" opened and closed (ADR-025): asking a technician for a number
    at the end of a shift buys a guess, and the guesses destroy the loop ADR-006
    is built on.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Mandatory. `no_problem_found` is one of the four and the reason the field
    # is not optional: it is the only false-alarm signal the system will ever
    # receive, and Loop 2 does not exist without it (ADR-022).
    outcome: WorkOutcome
    blocked_minutes: int = Field(default=0, ge=0)
    blocked_reason: tuple[BlockedReason, ...] = ()
    technician_feedback: str | None = None
    # Checked against the lock register before the job closes (REQ-H-06, ADR-135).
    lock_state: LockState | None = None
    lock_reason: str | None = None


class Report(BaseModel):
    """A fault somebody saw, in the words they saw it in.

    Three of the four fields are refused here rather than in the service, for the
    reason `Handover` refuses an empty note: a request that cannot become a
    sensible order should not reach the code that would have to decide what it
    meant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine_id: MachineId
    severity: Severity
    description: str = Field(min_length=1)
    # Optional, and never inferred from the description. A person may not know
    # which code it is, and a system that requires a diagnosis before it accepts
    # a problem gets one invented for it. No code means no playbook, a duration
    # from `fallback_minutes`, and `required_skill` left empty rather than
    # guessed (ADR-009, ADR-041, ADR-077 section 4).
    symptom_code: SymptomCode | None = None
    # The tickets the reporter was shown and is saying this is not. Named rather
    # than a plain "yes I am sure", so that a ticket raised between the refusal
    # and the retry refuses the retry too (ADR-077 section 3).
    distinct_from: tuple[str, ...] = ()

    @field_validator("description")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", and a description of spaces leaves a
        technician arriving at a machine knowing only that somebody thought
        something was wrong with it (ADR-077 section 5)."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("บอกสิ่งที่เห็นหรือได้ยินด้วย ใบแจ้งที่ไม่มีคำอธิบายช่างทำต่อไม่ได้")
        return stripped

    @field_validator("severity")
    @classmethod
    def _not_critical(cls, value: Severity) -> Severity:
        """ADR-077 section 2. `high` already passes the load gate on the busiest
        shift there is, so the ceiling costs a reporter no urgency; what it stops
        is one person's account outranking a measured threshold crossing in the
        queue. A fault that cannot wait for the next round is a phone call, and
        the ticket records it afterwards."""
        if value is Severity.CRITICAL:
            raise ValueError(
                "เลือกความเร่งด่วนได้แค่ ต่ำ ปานกลาง หรือ สูง ระดับวิกฤตใช้กับสิ่งที่เครื่องวัดได้เท่านั้น "
                "ถ้ารอรอบถัดไปไม่ได้ ให้โทรหาหัวหน้ากะก่อนแล้วค่อยแจ้งในระบบ"
            )
        return value


class ReportedOrder(BaseModel):
    """The ticket a report became, and what it did or did not come with.

    `estimate_is_fallback` and `playbook_ref` are returned because a reporter who
    gave no symptom code has produced an order that nothing priced and nothing
    can instruct, and the screen says so rather than showing a duration that
    looks measured (ADR-041).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    machine_id: str
    severity: Severity
    status: WorkOrderStatus
    reason: str
    estimated_minutes: int
    estimate_is_fallback: bool
    required_skill: str | None = None
    playbook_ref: str | None = None
    playbook_warning: str | None = None


class WorkOrderState(BaseModel):
    """What the screen shows after a button was pressed.

    `actual_minutes` and `repair_minutes` are returned because they are derived -
    the sum of the segments, and that sum with waiting removed - and a screen
    that computed them itself would be a second answer to a question the contract
    already answers (ADR-025).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    status: WorkOrderStatus
    assignees: tuple[str, ...] = ()
    segments: int = 0
    actual_minutes: int = 0
    blocked_minutes: int = 0
    repair_minutes: int = 0
    handover_note: str | None = None
    outcome: WorkOutcome | None = None


def _state(ref: str, order: WorkOrder) -> WorkOrderState:
    return WorkOrderState(
        ref=ref,
        status=order.status,
        assignees=tuple(str(one.user) for one in order.assignees),
        segments=len(order.work_segments),
        actual_minutes=order.actual_minutes,
        blocked_minutes=order.blocked_minutes,
        repair_minutes=order.repair_minutes,
        handover_note=order.handover_note,
        outcome=order.outcome,
    )


def _translate(error: Exception) -> HTTPException:
    """One mapping for all four handlers, so they cannot drift apart.

    404 for a reference that is not there; 409 for a state the button does not
    fit - somebody else has it, you never accepted it, it closed an hour ago;
    422 for a request that is answerable and wrong, which is where the blocked
    minutes land.
    """
    if isinstance(error, NoSuchOrder):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    if isinstance(error, TransitionRefused):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    if isinstance(error, AlreadyOpen):
        # The one refusal in this router whose detail is not a sentence. The
        # screen has to offer "this is something else" and that button carries
        # the references, so they are returned as data rather than left for a
        # regular expression over a message (ADR-077 section 3).
        return HTTPException(
            status.HTTP_409_CONFLICT,
            {
                "message": str(error),
                "open_orders": list(error.open_refs),
                "open_reasons": list(error.reasons),
                "open_titles": list(error.titles),
            },
        )
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


@router.post("/work-orders", response_model=ReportedOrder, status_code=status.HTTP_201_CREATED)
def report(
    reported: Report,
    conn: Db,
    orders: Orders,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_REPORT, action="report_fault"))],
) -> ReportedOrder:
    """The third origin: a person saw something (ADR-010, ADR-077).

    The machine is resolved against `plant.yaml` rather than trusted, because the
    model decides which playbook the order binds and which fallback prices it: a
    machine id nobody recognises would produce a ticket for a machine that does
    not exist, priced from a table it does not appear in.

    Everything else about the order is written by the work module. This handler
    does not phrase the reason, does not choose a priority and does not touch the
    queue - a report is proposed by a round and confirmed by a shift lead like
    any other work (ADR-005, ADR-071).
    """
    try:
        machine_model = plant.model_of(reported.machine_id)
    except KeyError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"ไม่พบเครื่อง {reported.machine_id} ในโรงงานนี้ ตรวจเลขที่ตัวเครื่องอีกครั้ง "
            f"หรือแจ้งหัวหน้ากะให้เพิ่มเครื่องนี้เข้าระบบ",
        ) from error

    try:
        issued = orders.from_report(
            conn,
            machine_id=reported.machine_id,
            machine_model=machine_model,
            severity=reported.severity,
            reported_by=account.user,
            # The name the board prints, rather than the sign-in (ADR-093).
            reporter_name=account.display_name,
            description=reported.description,
            symptom_code=reported.symptom_code,
            distinct_from=reported.distinct_from,
        )
    except (AlreadyOpen, TransitionRefused, ValueError) as error:
        raise _translate(error) from error

    order = issued.order
    return ReportedOrder(
        ref=issued.ref,
        machine_id=str(order.machine_id),
        severity=order.severity,
        status=order.status,
        reason=order.reason,
        estimated_minutes=order.estimated_minutes,
        estimate_is_fallback=order.estimate_is_fallback,
        required_skill=str(order.required_skill) if order.required_skill else None,
        playbook_ref=str(order.playbook_ref) if order.playbook_ref else None,
        playbook_warning=order.playbook_warning,
    )


@router.post("/work-orders/{work_order_ref}/accept", response_model=WorkOrderState)
def accept(
    work_order_ref: str,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="accept_work_order"))],
) -> WorkOrderState:
    """Take the job. The first person on it is the primary (ADR-056)."""
    try:
        order = orders.accept(conn, work_order_ref, user=account.user)
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return _state(work_order_ref, order)


@router.post("/work-orders/{work_order_ref}/start", response_model=WorkOrderState)
def start(
    work_order_ref: str,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="start_work_order"))],
) -> WorkOrderState:
    """Open a segment. The clock the segment is stamped with is the system's
    decision time, never `now()` (ADR-028), so a compressed demo does not stamp
    real time on simulated work."""
    try:
        order = orders.start(conn, work_order_ref, user=account.user)
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return _state(work_order_ref, order)


class Progress(BaseModel):
    """The step a technician has moved on to, 1-based as the screen counts."""

    model_config = ConfigDict(extra="forbid")

    step: int = Field(ge=1)


class StepReached(BaseModel):
    ref: str
    step: int


@router.post("/work-orders/{work_order_ref}/progress", response_model=StepReached)
def progress(
    work_order_ref: str,
    reached: Progress,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="record_step_reached"))],
) -> StepReached:
    """Where the job's steps have got to, so the job page can resume there
    (ADR-134). A bookmark: the order's status and segments do not move."""
    try:
        step = orders.reach_step(conn, work_order_ref, user=account.user, step=reached.step)
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return StepReached(ref=work_order_ref, step=step)


class Confirming(BaseModel):
    """One point of an isolation, verify or restore step (ADR-135, REQ-H-04)."""

    model_config = ConfigDict(extra="forbid")

    item: str = Field(pattern="^(off|locked|verified|checked|released|wait_started)$")
    point_id: str = ""
    lock_no: str | None = None


class Confirmed(BaseModel):
    step: int
    point_id: str
    item: str
    confirmed_at: str


@router.post("/work-orders/{work_order_ref}/steps/{step}/confirm", response_model=list[Confirmed])
def confirm_point(
    work_order_ref: str,
    step: int,
    confirming: Confirming,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="confirm_isolation_point"))],
) -> list[Confirmed]:
    """Switched off, locked, verified at zero, or released - one point at a
    time, in order, recorded with who and when. Locks go into the register."""
    try:
        done = orders.confirm(
            conn,
            work_order_ref,
            user=account.user,
            step=step,
            point_id=confirming.point_id,
            item=confirming.item,
            lock_no=confirming.lock_no,
        )
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return [
        Confirmed(
            step=one.step,
            point_id=one.point_id,
            item=one.item,
            confirmed_at=one.confirmed_at.isoformat(),
        )
        for one in done
    ]


class LockView(BaseModel):
    lock_id: int
    # Whether the job is still open: a closed one asks for the restore checks on the release.
    job_open: bool = True
    checks_needed: tuple[CheckView, ...] = ()
    work_order_ref: str
    machine_id: str
    point_id: str
    lock_no: str
    step: int
    applied_at: str


class Removal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1)
    # The shift lead who watched the lock come off, signing with their own password
    # on this phone (ADR-137): outside the restore step nothing else vouches for it.
    witness: str = Field(min_length=1)
    witness_password: str = Field(min_length=1)
    # The plant's restore checks, confirmed on the release when the job has closed (C3).
    checks: tuple[str, ...] = ()


class CheckView(BaseModel):
    key: str
    label: str


def _lock(one: locks.Lock) -> LockView:
    return LockView(
        lock_id=one.lock_id,
        work_order_ref=one.work_order_ref,
        machine_id=str(one.machine_id),
        point_id=one.point_id,
        lock_no=one.lock_no,
        step=one.step,
        applied_at=one.applied_at.isoformat(),
    )


@router.get("/locks/mine", response_model=list[LockView])
def my_locks(
    conn: Db,
    config: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="read_own_locks"))],
) -> list[LockView]:
    """Every lock still on in this person's name, on any job (ADR-136), with the
    plant's restore checks for those whose job has closed (ADR-138, C3)."""
    checks = tuple(
        CheckView(key=one.key, label=one.label) for one in config.policy.safety.restore_checks
    )
    views = []
    for one in locks.locks_of(conn, account.user):
        order = work_repo.get(conn, one.work_order_ref)
        is_open = order is not None and order.status not in (
            WorkOrderStatus.CLOSED,
            WorkOrderStatus.CANCELLED,
        )
        views.append(
            _lock(one).model_copy(
                update={"job_open": is_open, "checks_needed": () if is_open else checks}
            )
        )
    return views


# C2: a witness's password is tried at most this often before the account is
# held, and every try is written to the access log - a phone passed round a
# shift is not a place to guess a lead's password.
WITNESS_TRIES = 5
WITNESS_WINDOW = timedelta(minutes=15)


@router.post("/locks/{lock_id}/release", response_model=LockView)
def release_my_lock(
    lock_id: int,
    removal: Removal,
    conn: Db,
    orders: Orders,
    clock: Time,
    config: Plant,
    auth: Annotated[Authentication, Depends(authentication)],
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="release_own_lock"))],
) -> LockView:
    """The owner records taking their own lock off, with why and in front of a
    shift lead - after a handover or a "still locked" close, when the job is no
    longer theirs (ADR-136 B3, ADR-137, ADR-138). Nobody else's: a lock is
    removed by the person whose lock it is."""
    now = clock.now()
    witness_id = UserId(removal.witness)
    failed, last = auth_repo.failed_attempts(
        conn, action="witness_lock_release", subject=str(witness_id), since=now - WITNESS_WINDOW
    )
    if failed >= WITNESS_TRIES and last is not None:
        # Who is held, since when and until when - and that another lead can clear it.
        free_at = (last + WITNESS_WINDOW).astimezone(config.timezone)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"รหัสพยานของ {witness_id} ผิด {failed} ครั้ง ล่าสุด "
            f"{last.astimezone(config.timezone):%H:%M} น. · ใช้ได้อีกครั้ง {free_at:%H:%M} น. "
            "หรือให้หัวหน้ากะคนอื่นล้างการล็อก",
        )
    witness = auth.identity.authenticate(conn, witness_id, removal.witness_password)
    ok = witness is not None and witness.role is Role.SUPERVISOR
    auth_repo.record_access(
        conn,
        now=now,
        user=account.user,
        role=account.role,
        action="witness_lock_release",
        subject=str(witness_id),
        allowed=ok,
    )
    if witness is None or not ok:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "ต้องมีหัวหน้ากะยืนยันด้วยรหัสของตัวเองตอนปลดกุญแจนอกขั้นคืนพลังงาน"
        )
    try:
        return _lock(
            orders.release_own_lock(
                conn,
                lock_id,
                user=account.user,
                reason=removal.reason,
                witness=witness.user,
                checks=removal.checks,
            )
        )
    except (TransitionRefused, ValueError) as error:
        raise _translate(error) from error


@router.post("/witness-lockouts/{user}/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_witness_lockout(
    user: str,
    conn: Db,
    clock: Time,
    account: Annotated[Account, Depends(requires(Role.SUPERVISOR, action="reset_witness_lockout"))],
) -> None:
    """Another shift lead clears a lead held after five wrong witness passwords
    (ADR-138, set 2 refresh review item 8). Nobody clears their own; the reset is
    in the access log, and the count starts again from it."""
    if UserId(user) == account.user:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "ล้างการล็อกของตัวเองไม่ได้ ให้หัวหน้ากะคนอื่นทำ")
    auth_repo.record_access(
        conn,
        now=clock.now(),
        user=account.user,
        role=account.role,
        action="witness_lock_release_reset",
        subject=user,
        allowed=True,
    )


@router.post("/work-orders/{work_order_ref}/handover", response_model=WorkOrderState)
def hand_over(
    work_order_ref: str,
    handover: Handover,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="hand_over_work_order"))],
) -> WorkOrderState:
    """Put it down for the next shift, with the note that saves them the first
    hour (ADR-025)."""
    try:
        order = orders.hand_over(
            conn,
            work_order_ref,
            user=account.user,
            note=handover.note,
            lock_state=handover.lock_state,
            lock_reason=handover.lock_reason,
        )
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return _state(work_order_ref, order)


@router.post("/work-orders/{work_order_ref}/close", response_model=WorkOrderState)
def close(
    work_order_ref: str,
    closing: Closing,
    conn: Db,
    orders: Orders,
    account: Annotated[Account, Depends(requires(*_MAY_WORK, action="close_work_order"))],
) -> WorkOrderState:
    """End it, with how it ended and what held it up."""
    try:
        order = orders.close(
            conn,
            work_order_ref,
            user=account.user,
            outcome=closing.outcome,
            blocked_minutes=closing.blocked_minutes,
            blocked_reason=closing.blocked_reason,
            technician_feedback=closing.technician_feedback,
            lock_state=closing.lock_state,
            lock_reason=closing.lock_reason,
        )
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return _state(work_order_ref, order)

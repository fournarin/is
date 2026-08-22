"""The four buttons a technician has: accept, start, hand over, close.

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
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.api.deps import Db, requires
from pdm.contracts import BlockedReason, Role, WorkOrder, WorkOrderStatus, WorkOutcome
from pdm.platform.auth.domain import Account
from pdm.work import NoSuchOrder, TransitionRefused, WorkOrders

router = APIRouter(tags=["work orders"])

# ADR-024. An engineer approves the playbook and does not take the job; a
# supervisor releases what the gate is holding and does not take it either.
_MAY_WORK = (Role.TECHNICIAN,)


def _orders(request: Request) -> WorkOrders:
    return request.app.state.work_orders  # type: ignore[no-any-return]


Orders = Annotated[WorkOrders, Depends(_orders)]


class Handover(BaseModel):
    """ADR-025's note, required by the schema so the request never reaches the
    code that would have to decide what an empty one means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str = Field(min_length=1)

    @field_validator("note")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", and a note of spaces leaves the next shift
        exactly where no note would: starting again from step one."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("a handover note cannot be only whitespace (ADR-025)")
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
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error))


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
        order = orders.hand_over(conn, work_order_ref, user=account.user, note=handover.note)
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
        )
    except (NoSuchOrder, TransitionRefused, ValueError) as error:
        raise _translate(error) from error
    return _state(work_order_ref, order)

"""What layer 3 decided, and why - the two read paths ADR-005 asks for.

Two questions, asked by two people, and ADR-041 keeps them apart on the record
so they can be answered separately here:

  a technician looks at one ticket and asks **why this job, and why now**;
  a shift lead looks at the queue and asks **what is being held back, and why**.

The second one is the sentence ADR-011 kept the gate separate in order to be
able to write. Without a reader it was a string nobody had ever seen, and a
supervisor whose work does not appear has no way to tell a system that is
holding it from a system that lost it - which is how a scheduler gets overruled
and then abandoned (principle 3).

**Nothing here writes.** The report is computed when asked (ADR-050), from the
same `dispatch()` the rounds use, so a supervisor and the scheduler cannot
disagree about what is being held.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from pdm.api.deps import Db, requires
from pdm.contracts import Role, Severity, WorkOrderStatus
from pdm.dispatch.service import DispatchRounds
from pdm.platform.auth.domain import Account
from pdm.work import repo as work

router = APIRouter(tags=["dispatch"])

# Everybody who can be shown a ticket may read why it is ranked where it is.
# Restricting the gate's report to supervisors would leave a technician with a
# ranking and no way to check it, which is the state ADR-005 exists to prevent.
_MAY_READ = (Role.TECHNICIAN, Role.ENGINEER, Role.SUPERVISOR, Role.OPERATOR)


class Ranked(BaseModel):
    """One released ticket, and the numbers behind where it sits."""

    ref: str
    priority_score: float
    priority_reason: str
    assignees: tuple[str, ...] = ()
    # The unnormalised quantities the sentence quotes. Returned so a screen can
    # show the figures rather than re-deriving them, and deliberately not the
    # normalised terms, which mean nothing outside their own round (ADR-045 §1).
    downtime_units: float = 0.0
    waited_minutes: float = 0.0


class Withheld(BaseModel):
    ref: str
    why: str


class RoundView(BaseModel):
    """What the gate is doing right now.

    `at` is when it was computed, not when a round last ran, and the two differ
    by up to one cadence. Named rather than hidden: a supervisor reading a
    report has to know whether it describes the queue in front of them or the
    queue five minutes ago (ADR-050).
    """

    at: datetime
    shift_id: str | None = None
    on_date: date | None = None
    band: str
    load_ratio: float | None = None
    capacity_minutes: int
    committed_minutes: int
    summary: str
    placed: list[Ranked] = []
    unassigned: list[Withheld] = []
    held: list[Withheld] = []


class TicketView(BaseModel):
    """One ticket as the person who has to do it sees it.

    Both reasons, because they answer different questions and one field would
    answer whichever was asked last (ADR-005, ADR-041): `reason` is why the job
    exists - "over threshold for twenty minutes", or a crossing expected in
    about six hours, give or take two - and `priority_reason` is why it is
    ranked where it is.
    """

    ref: str
    machine_id: str
    severity: Severity
    status: WorkOrderStatus
    reason: str
    priority_reason: str
    priority_score: float
    estimated_minutes: int
    estimate_is_fallback: bool
    required_skill: str | None = None
    required_technicians: int
    assignees: tuple[str, ...] = ()
    playbook_warning: str | None = None


def _rounds(request: Request) -> DispatchRounds:
    return request.app.state.dispatch_rounds  # type: ignore[no-any-return]


@router.get("/dispatch/round", response_model=RoundView)
def current_round(
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_dispatch_round"))],
    rounds: Annotated[DispatchRounds, Depends(_rounds)],
) -> RoundView:
    """The gate's own sentence, and everything behind it (ADR-011).

    Computed now rather than read from a log of past rounds, which is ADR-050:
    "four tickets are being held" is a question about the queue in front of
    somebody, and the answer that was true five minutes ago is the wrong one.
    """
    decided = rounds.decide(conn)
    return RoundView(
        at=decided.at,
        shift_id=decided.shift_id,
        on_date=decided.on_date,
        band=decided.band.value,
        load_ratio=decided.load_ratio,
        capacity_minutes=decided.capacity_minutes,
        committed_minutes=decided.committed_minutes,
        summary=decided.summary,
        placed=[
            Ranked(
                ref=one.ref,
                priority_score=one.priority_score,
                priority_reason=one.priority_reason,
                assignees=tuple(str(who.user) for who in one.assignees),
                downtime_units=one.facts.downtime_units,
                waited_minutes=one.facts.waited_minutes,
            )
            for one in decided.placed
        ],
        unassigned=[Withheld(ref=one.ref, why=one.why) for one in decided.unassigned],
        held=[Withheld(ref=one.ref, why=one.why) for one in decided.held],
    )


@router.get("/work-orders/{work_order_ref}", response_model=TicketView)
def ticket(
    work_order_ref: str,
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_work_order"))],
) -> TicketView:
    """One ticket, with both of its reasons.

    `priority_reason` is whatever the round that released it wrote, not a fresh
    calculation: it is the explanation the person was given, and re-deriving it
    on every read would show them a sentence about a queue that has since
    changed. A ticket nobody has released yet carries an empty one, which is the
    truth - no round has ranked it.
    """
    order = work.get(conn, work_order_ref)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no work order {work_order_ref}")
    return TicketView(
        ref=work_order_ref,
        machine_id=str(order.machine_id),
        severity=order.severity,
        status=order.status,
        reason=order.reason,
        priority_reason=order.priority_reason,
        priority_score=order.priority_score,
        estimated_minutes=order.estimated_minutes,
        estimate_is_fallback=order.estimate_is_fallback,
        required_skill=str(order.required_skill) if order.required_skill else None,
        required_technicians=order.required_technicians,
        assignees=tuple(str(who.user) for who in order.assignees),
        playbook_warning=order.playbook_warning,
    )

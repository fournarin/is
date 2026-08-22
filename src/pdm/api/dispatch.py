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

**The two read paths write nothing.** The report is computed when asked
(ADR-050), from the same `dispatch()` the rounds use, so a supervisor and the
scheduler cannot disagree about what is being held.

The two writes here are the same argument running the other way (ADR-059): a
person overruling the scheduler explains themselves to it. A technician records
that the queue put the wrong job first - and the queue does not move, because a
ranking that could be argued down is not a ranking - and a shift lead releases
one held ticket, with the reason and the shift it was released against. Neither
places anybody on anything; that is still the round's job, in worker-runtime.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.api.deps import Db, Rounds, Time, requires
from pdm.contracts import (
    FindingKind,
    Role,
    Severity,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.dispatch import Band
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.overrides import Override, OverrideKind
from pdm.platform.auth.domain import Account

# Reading a Finding here is not the thing `.importlinter` forbids. That rule
# names `pdm.dispatch` - layer 3's own code, which must schedule from the order
# alone (invariant 10, ADR-030) - and this module is `pdm.api.dispatch`, the
# composition layer that already reaches into work/, dispatch/ and playbooks/ to
# assemble a screen.
from pdm.triggers import repo as findings
from pdm.work import repo as work

router = APIRouter(tags=["dispatch"])

# Everybody who can be shown a ticket may read why it is ranked where it is.
# Restricting the gate's report to supervisors would leave a technician with a
# ranking and no way to check it, which is the state ADR-005 exists to prevent.
_MAY_READ = (Role.TECHNICIAN, Role.ENGINEER, Role.SUPERVISOR, Role.OPERATOR)

# Whoever may be shown a ranking may object to it. Narrowing this to the person
# holding the ticket would record only the objections that are convenient, and
# the record is the entire value of the button (ADR-059).
_MAY_OBJECT = _MAY_READ

# ADR-024's table and ADR-011's sentence: the gate reports to the shift lead, and
# taking work out of its hands is the shift lead's decision to defend.
_MAY_RELEASE = (Role.SUPERVISOR,)


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
    # Every timestamp in this system is UTC (config/plant.yaml), and every
    # timestamp a person reads is plant-local. The zone is a fact about the
    # plant rather than about the device holding the screen - a supervisor
    # reading this from a laptop set to UTC still has to see the shift's own
    # clock - so it comes from the configuration, here, rather than from the
    # browser.
    timezone: str
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


class Step(BaseModel):
    """One instruction as it was issued, with the page it came from.

    Taken from `playbook_snapshot` and never from the playbook table. The order
    has to be able to prove what it instructed, and the served row is
    overwritten on re-approval (ADR-018) - so a screen reading the current
    playbook would show a technician steps nobody gave them.
    """

    text: str
    source_doc: str
    page: int


class Recurrence(BaseModel):
    """How often the rule behind this ticket has fired, read now.

    Through `finding_ref`, deliberately: `machine_id`, `severity`, `eta` and the
    rest are snapshots frozen onto the order at creation (ADR-041), and "seen 34
    times since 08:12" is the one figure on the screen that has to be current.
    ADR-023 raises `occurrence_count` on the existing record rather than opening
    a second one, which is what makes the count mean anything.
    """

    occurrence_count: int
    detected_at: datetime
    last_seen_at: datetime | None = None
    status: str


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
    origin: WorkOrderOrigin
    reason: str
    priority_reason: str
    priority_score: float
    estimated_minutes: int
    estimate_is_fallback: bool
    required_skill: str | None = None
    required_technicians: int
    assignees: tuple[str, ...] = ()
    playbook_warning: str | None = None

    # A predicted job must not be able to reach a screen looking like a detected
    # one. `eta_confidence` is serialised as whole minutes and is **never**
    # optional when `finding_kind` is predicted - the contract validates that on
    # the Finding (ADR-020) and the test at this seam validates it again, because
    # this is the layer where dropping it would be invisible.
    finding_kind: FindingKind | None = None
    eta: datetime | None = None
    eta_confidence_minutes: int | None = None

    steps: tuple[Step, ...] = ()
    recurrence: Recurrence | None = None


class Objection(BaseModel):
    """The typed reason, required by the schema so the request never reaches the
    code that would have to decide what an empty one means."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", and a reason of spaces leaves whoever reads
        this back exactly where no reason would."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("an override needs a reason (ADR-005)")
        return stripped


class OverrideRecorded(BaseModel):
    """What was written down, returned so the screen shows the record rather
    than a hopeful message about one.

    A release carries the round it was taken against and a disagreement does not,
    because a disagreement is about one ticket's rank and not about the shift.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    kind: OverrideKind
    at: datetime
    reason: str
    by: str
    band: str | None = None
    load_ratio: float | None = None
    shift_id: str | None = None


def _recorded(override: Override) -> OverrideRecorded:
    return OverrideRecorded(
        ref=override.work_order_ref,
        kind=override.kind,
        at=override.at,
        reason=override.reason,
        by=str(override.user),
        band=override.band.value if override.band is not None else None,
        load_ratio=override.load_ratio,
        shift_id=str(override.shift_id) if override.shift_id is not None else None,
    )


@router.get("/dispatch/round", response_model=RoundView)
def current_round(
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_dispatch_round"))],
    rounds: Rounds,
) -> RoundView:
    """The gate's own sentence, and everything behind it (ADR-011).

    Computed now rather than read from a log of past rounds, which is ADR-050:
    "four tickets are being held" is a question about the queue in front of
    somebody, and the answer that was true five minutes ago is the wrong one.
    """
    decided = rounds.decide(conn)
    return RoundView(
        at=decided.at,
        timezone=rounds.config.plant.timezone,
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


def _recurrence(conn: Connection[Any], order: WorkOrder) -> Recurrence | None:
    """How often the rule behind this order has fired, or None.

    None for scheduled and manual work, which has no Finding at all (ADR-010) -
    and None rather than a count of one, because "seen once" and "there is
    nothing to count" are different sentences and a screen must not print the
    first when it means the second.
    """
    if order.finding_ref is None:
        return None
    finding = findings.get(conn, order.finding_ref)
    if finding is None:
        return None
    return Recurrence(
        occurrence_count=finding.occurrence_count,
        detected_at=finding.detected_at,
        last_seen_at=finding.last_seen_at,
        status=finding.status.value,
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
        origin=order.origin,
        reason=order.reason,
        priority_reason=order.priority_reason,
        priority_score=order.priority_score,
        estimated_minutes=order.estimated_minutes,
        estimate_is_fallback=order.estimate_is_fallback,
        required_skill=str(order.required_skill) if order.required_skill else None,
        required_technicians=order.required_technicians,
        assignees=tuple(str(who.user) for who in order.assignees),
        playbook_warning=order.playbook_warning,
        finding_kind=order.finding_kind,
        eta=order.eta,
        eta_confidence_minutes=(
            None
            if order.eta_confidence is None
            else round(order.eta_confidence.total_seconds() / 60)
        ),
        steps=tuple(
            Step(text=step.text, source_doc=str(step.source_doc), page=step.page)
            for step in order.playbook_snapshot
        ),
        recurrence=_recurrence(conn, order),
    )


@router.post(
    "/work-orders/{work_order_ref}/disagreement",
    response_model=OverrideRecorded,
    status_code=status.HTTP_201_CREATED,
)
def disagree(
    work_order_ref: str,
    objection: Objection,
    conn: Db,
    clock: Time,
    account: Annotated[Account, Depends(requires(*_MAY_OBJECT, action="record_disagreement"))],
) -> OverrideRecorded:
    """ "I disagree" - recorded, and changing nothing else (ADR-005, ADR-059).

    The queue does not move. Re-ranking on an objection would make it negotiable,
    and a queue that can be argued down is how the load gate stops mattering: the
    easy job gets talked to the top on the shift where that is worst. What the
    button is worth is the record - a hundred of these against the same term is
    an argument about the score that can be had with evidence rather than with
    recollection, and it is worth nothing at all if it is not written down while
    somebody is standing at the machine.
    """
    if work.get(conn, work_order_ref) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no work order {work_order_ref}")

    override = Override(
        kind=OverrideKind.PRIORITY_DISAGREEMENT,
        work_order_ref=work_order_ref,
        user=account.user,
        role=account.role,
        at=clock.now(),
        reason=objection.reason,
    )
    dispatch_repo.record_override(conn, override)
    return _recorded(override)


@router.post(
    "/dispatch/held/{work_order_ref}/release",
    response_model=OverrideRecorded,
    status_code=status.HTTP_201_CREATED,
)
def release_held(
    work_order_ref: str,
    objection: Objection,
    conn: Db,
    clock: Time,
    rounds: Rounds,
    account: Annotated[Account, Depends(requires(*_MAY_RELEASE, action="release_held_work_order"))],
) -> OverrideRecorded:
    """One held ticket, into the next round, on the shift lead's authority.

    The round is computed here rather than remembered, for ADR-050's reason and
    for one more: the band and ratio written onto the record have to be the ones
    in force at the moment of the decision, and a round that ran five minutes ago
    describes a different shift. They are copied onto the record because the
    round itself is never stored - six weeks later there is nothing else to read
    the decision back against.

    What this does **not** do is place anybody on anything. The next round ranks
    and crews the released order like any other, which is why releasing work into
    a shift that has nobody on it is refused below rather than accepted with
    nothing to show for it.
    """
    if work.get(conn, work_order_ref) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no work order {work_order_ref}")

    if work_order_ref in dispatch_repo.released(conn):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"{work_order_ref} has already been released; it is waiting for a round, not "
            "for the gate",
        )

    decided = rounds.decide(conn)
    if decided.band is Band.NO_CAPACITY:
        # Everything is held here, and the gate is not what is holding it: there
        # is no shift, or nobody on it (ADR-045 §3). Releasing would record a
        # decision that could not have an effect, and the honest answer is the
        # sentence the round already wrote.
        raise HTTPException(status.HTTP_409_CONFLICT, decided.summary)

    if work_order_ref not in {one.ref for one in decided.held}:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"the gate is not holding {work_order_ref}",
        )

    override = Override(
        kind=OverrideKind.RELEASE_HELD,
        work_order_ref=work_order_ref,
        user=account.user,
        role=account.role,
        at=clock.now(),
        reason=objection.reason,
        band=decided.band,
        load_ratio=decided.load_ratio,
        shift_id=decided.shift_id,
        on_date=decided.on_date,
    )
    dispatch_repo.record_override(conn, override)
    return _recorded(override)

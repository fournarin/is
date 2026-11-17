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

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.api.deps import Confirming, Db, Plant, Rounds, Time, requires
from pdm.contracts import (
    Assignee,
    AssigneeRole,
    FindingKind,
    IsolationPoint,
    MachineId,
    MachineModel,
    Role,
    Severity,
    StepKind,
    SymptomCode,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.dispatch import Band, downtime_or_unknown
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.agreement import AgreementReport, agreement
from pdm.dispatch.overrides import Override, OverrideKind
from pdm.dispatch.proposals import Proposal, ProposalState, Reassignment, crew_with, why_not
from pdm.dispatch.service import AlreadyAnswered, NoProposal, NotSetAside
from pdm.platform.auth import repo as auth_repo
from pdm.platform.auth.domain import Account
from pdm.platform.config import Config
from pdm.playbooks import repo as playbooks_repo
from pdm.playbooks.domain import uncovered

# Layer 4, for one line in `confirm_proposal`. `.importlinter` bans `pdm.dispatch`
# and `pdm.work` from importing this package at all and names only the workers
# and this layer as allowed to (ADR-068) - which is what makes it possible for
# the transaction that gives a technician a job to be the one that queues the
# ticket, without layer 3 learning that a destination exists (ADR-071 §5).
from pdm.sinks import repo as deliveries

# Reading a Finding here is not the thing `.importlinter` forbids. That rule
# names `pdm.dispatch` - layer 3's own code, which must schedule from the order
# alone (invariant 10, ADR-030) - and this module is `pdm.api.dispatch`, the
# composition layer that already reaches into work/, dispatch/ and playbooks/ to
# assemble a screen.
from pdm.triggers import repo as findings
from pdm.work import locks
from pdm.work import repo as work
from pdm.work.domain import reported_words, title, when_expected

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

# The press the advisor asked for on 2026-08-23 (ADR-071). Same role as the
# release above and for the same reason: ADR-024 makes the shift lead the person
# who answers for what the shift is sent to do.
_MAY_CONFIRM = (Role.SUPERVISOR,)

# The confirmation record is about the shift lead rather than for them (ADR-075
# section 6), so it is not on the technician's side of the house: a report of how
# often somebody's decisions were overruled by nobody in particular is read by
# the people who would act on it - the shift lead themselves, and the engineer
# who would take it to the maintenance department with the switch in hand.
_MAY_READ_THE_RECORD = (Role.SUPERVISOR, Role.ENGINEER)


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
    # What the shift lead set aside this shift, each with their reason (ADR-120).
    set_aside: list[Withheld] = []


class Step(BaseModel):
    """One instruction as it was issued, with the page it came from.

    Taken from `playbook_snapshot` and never from the playbook table. The order
    has to be able to prove what it instructed, and the served row is
    overwritten on re-approval (ADR-018) - so a screen reading the current
    playbook would show a technician steps nobody gave them.
    """

    text: str
    # The approver's Thai, when there is one (ADR-095). `text` is the manual's.
    text_th: str | None = None
    source_doc: str
    page: int
    # Which manual the page is in, so a technician holding the printed copy
    # knows which book to open (ADR-102).
    manual: str | None = None
    # As the approving engineer marked it (ADR-135); a step nobody marked is normal.
    kind: StepKind = StepKind.NORMAL
    hazards: tuple[str, ...] = ()
    isolation_points: tuple[IsolationPoint, ...] = ()
    wait_minutes: int | None = None


class PointConfirmed(BaseModel):
    step: int
    point_id: str
    item: str
    by: str
    at: datetime


class RestoreCheckView(BaseModel):
    key: str
    label: str


class LockOn(BaseModel):
    """A personal lock still on a point of this machine (ADR-135)."""

    point_id: str
    lock_no: str
    owner: str
    owner_name: str
    work_order_ref: str
    step: int
    applied_at: datetime


class Reading(BaseModel):
    """The measurement behind a condition ticket, as its Finding recorded it
    (ADR-134): the value, the line it is measured against, and for a forecast
    the slope. Each is None where the Finding did not carry it, and a screen
    leaves that box out rather than inventing a figure."""

    metric_name: str
    metric_title: str | None = None
    unit: str | None = None
    value: float | None = None
    measured_at: datetime | None = None
    threshold: float | None = None
    comparison: str | None = None
    slope_per_hour: float | None = None


class PastJob(BaseModel):
    """One closed job on the same machine: what the last person found (ADR-134)."""

    ref: str
    title: str
    closed_at: datetime
    outcome: WorkOutcome
    minutes: int
    by: tuple[str, ...] = ()
    page: int | None = None
    note: str | None = None


class Approval(BaseModel):
    """Who approved the steps this order carries, and when (principle 2).

    `revision` is the served playbook's only while it is still the one the
    snapshot was taken from; after a re-approval the order's steps are an
    older revision whose number is not kept, and None says so rather than
    printing the new number over the old steps.
    """

    approved_by: str
    approved_at: datetime
    revision: int | None = None
    manual: str | None = None


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


class WhereToLook(BaseModel):
    """Where a technician holding a ticket with no approved steps should look (ADR-118).

    Principle 5 in the ticket's own words: "not found - see manual page X or
    ask an engineer". Only facts the system already holds: the manuals in
    service for this machine model, and the pages a draft waiting for an
    engineer cites. A draft page is marked as one, because it has not been
    approved; it is a page to read, never a step to follow.
    """

    document_id: str
    manual: str
    page: int | None = None
    from_unapproved_draft: bool = False


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
    # Machine and symptom, the name a person gives the job (fourth trial).
    title: str = ""
    severity: Severity
    status: WorkOrderStatus
    origin: WorkOrderOrigin
    reason: str
    # The other work open on this machine as the ticket is read (finding 5).
    also_open: tuple[str, ...] = ()
    priority_reason: str
    priority_score: float
    estimated_minutes: int
    estimate_is_fallback: bool
    required_skill: str | None = None
    # The skill and the station as the plant names them, for the screen to
    # print as they are (ADR-093). Labels, not sentences.
    required_skill_name: str | None = None
    station: str | None = None
    tools: tuple[str, ...] = ()
    # The approver's Thai for each tool, position for position; "" where the
    # manual's words stand (ADR-130).
    tools_th: tuple[str, ...] = ()
    required_technicians: int
    assignees: tuple[str, ...] = ()
    playbook_warning: str | None = None
    # What the last person to put this job down wrote about how far it got
    # (ADR-025). The next person, and the lead offering it to them, read it.
    handover_note: str | None = None

    # A predicted job must not be able to reach a screen looking like a detected
    # one. `eta_confidence` is serialised as whole minutes and is **never**
    # optional when `finding_kind` is predicted - the contract validates that on
    # the Finding (ADR-020) and the test at this seam validates it again, because
    # this is the layer where dropping it would be invisible.
    finding_kind: FindingKind | None = None
    eta: datetime | None = None
    eta_confidence_minutes: int | None = None
    # The live forecast as a sentence, interval included (ADR-123). Rendered
    # here so no screen prints a time without its give-or-take.
    eta_text: str | None = None

    steps: tuple[Step, ...] = ()
    # Filled only when `steps` is empty (ADR-118).
    where_to_look: tuple[WhereToLook, ...] = ()
    # A scheduled job with no steps and no page on record says where in the
    # manual to look instead of a bare title (fourth trial, finding 11).
    where_to_look_note: str | None = None
    recurrence: Recurrence | None = None

    # What the technician's job page shows besides the steps (ADR-134).
    station_name: str | None = None
    machine_model: str | None = None
    started_at: datetime | None = None
    step_reached: int | None = None
    reading: Reading | None = None
    history: tuple[PastJob, ...] = ()
    approval: Approval | None = None
    # Whom to ask when there are no approved steps: the engineer who last
    # approved a playbook for this machine model.
    engineer: str | None = None

    # Isolation, point by point (ADR-135).
    confirmations: tuple[PointConfirmed, ...] = ()
    locks: tuple[LockOn, ...] = ()
    # Lock numbers the reader has used before, for one-tap choices.
    your_lock_numbers: tuple[str, ...] = ()
    # Isolated points no verify step covers (REQ-H-05): shown as a stop bar.
    missing_verify: bool = False
    unverified_points: tuple[str, ...] = ()
    # EHS's checks before a restore step's locks come off (policy.yaml, ADR-136).
    restore_checks: tuple[RestoreCheckView, ...] = ()


class Mine(BaseModel):
    """One job that is this person's now, as their screen lists it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    status: WorkOrderStatus
    priority_score: float
    priority_reason: str


class Candidate(BaseModel):
    """One person the shift lead could give a proposed job to instead."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    user: str
    name: str


class ProposalView(BaseModel):
    """One decision waiting for a supervisor (ADR-071).

    Carries the round it was decided against rather than the round in front of
    the reader. The two differ by up to one cadence and sometimes by more, and a
    supervisor answering "should this go out" is answering about the shift the
    scheduler saw - which is the whole reason those four columns are copied onto
    the record (ADR-050, ADR-059).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    proposed_at: datetime
    assignees: tuple[str, ...]
    # The same people by name, for the board (ADR-093).
    assignee_names: tuple[str, ...] = ()
    priority_score: float
    priority_reason: str
    band: str | None = None
    load_ratio: float | None = None
    shift_id: str | None = None
    # When it goes back into the queue if nobody answers (ADR-071 §6). Computed
    # here rather than shown as a duration, because "expires at 14:32" is a
    # decision a person can make and "expires in a while" is not.
    expires_at: datetime
    # Who else on this shift could take it, for the lead's "ให้คนอื่น" (ADR-132):
    # active, rostered now, holding the skill the job asks for, and not already
    # the proposed primary. Empty when nobody else could.
    others: tuple[Candidate, ...] = ()
    # What the line loses if this waits, in cars, by the same arithmetic the
    # score used (ADR-021); None where the layout cannot place the machine. The
    # board's one number per row (ADR-141).
    downtime_units: float | None = None
    # Why the proposed person, in one line: the skill, the time, what they hold
    # now. Facts the round checked, not a ranking of people (ADR-141).
    assigned_because: str | None = None


class ProposalAnswered(BaseModel):
    """What was recorded, returned so the screen shows the record rather than a
    hopeful message about one - the same argument as `OverrideRecorded`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    state: ProposalState
    at: datetime
    by: str
    reason: str | None = None
    # Who the job went to, by name, when the lead chose somebody else (ADR-132).
    given_to: tuple[str, ...] = ()


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
        set_aside=[Withheld(ref=one.ref, why=one.why) for one in decided.set_aside],
    )


class Reported(BaseModel):
    """One fault this person reported, and where it is now (ADR-122)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    machine_id: str
    reported_at: datetime
    # The same moment on the plant's clock, as people say it (ADR-093).
    reported_when: str
    reason: str
    # What the reporter wrote, so two reports on one machine can be told apart
    # in their list (fourth trial, finding 19).
    what: str = ""
    status: WorkOrderStatus
    # Where it is, in a sentence the reporter reads. Written here rather than by
    # the screen: every sentence a person reads comes from the backend (ADR-063).
    where: str
    finished: bool


_OUTCOME_TH = {
    WorkOutcome.FIXED: "ช่างซ่อมเสร็จแล้ว",
    WorkOutcome.TEMPORARY_FIX: "ช่างแก้ชั่วคราวแล้ว ยังต้องซ่อมจริงอีกครั้ง",
    WorkOutcome.NOT_FIXED: "ช่างยังซ่อมไม่ได้",
    WorkOutcome.NO_PROBLEM_FOUND: "ช่างตรวจแล้วไม่พบปัญหา",
}


def _where(order: WorkOrder, names: tuple[str, ...]) -> str:
    who = ", ".join(names)
    if order.status is WorkOrderStatus.QUEUED:
        return "รอหัวหน้ากะจัดช่าง"
    if order.status is WorkOrderStatus.PROPOSED:
        return f"ระบบเลือก {who} ไว้ รอหัวหน้ากะยืนยัน"
    if order.status is WorkOrderStatus.ASSIGNED:
        return f"ส่งให้ {who} แล้ว รอเริ่มงาน"
    if order.status is WorkOrderStatus.IN_PROGRESS:
        return f"{who} กำลังซ่อม"
    if order.status is WorkOrderStatus.HANDED_OVER:
        return "ช่างส่งต่อไว้ รอคนรับงานต่อ"
    if order.status is WorkOrderStatus.CANCELLED:
        return "ยกเลิกแล้ว"
    return _OUTCOME_TH.get(order.outcome, "ปิดงานแล้ว") if order.outcome else "ปิดงานแล้ว"


@router.get("/work-orders/reported", response_model=list[Reported])
def reported_by_me(
    conn: Db,
    plant: Plant,
    account: Annotated[
        Account,
        Depends(requires(*_MAY_READ, action="read_my_reports")),
    ],
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[Reported]:
    """What the caller reported, newest first, and where each one is (ADR-122).

    Registered before `/work-orders/{work_order_ref}` for the reason `mine` is.
    In the owner's second trial a report, once sent, could not be found again
    by the person who sent it.
    """
    return [
        Reported(
            ref=ref,
            machine_id=str(order.machine_id),
            reported_at=created_at,
            reported_when=plant.wording().day_and_clock(created_at),
            reason=order.reason,
            what=reported_words(order),
            status=order.status,
            where=_where(order, _names(conn, (one.user for one in order.assignees))),
            finished=order.status in (WorkOrderStatus.CLOSED, WorkOrderStatus.CANCELLED),
        )
        for ref, created_at, _closed, order in work.reported_by(conn, account.user, limit=limit)
    ]


@router.get("/work-orders/mine", response_model=list[Mine])
def my_work(
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_my_work"))],
) -> list[Mine]:
    """This caller's own live work, ranked as layer 3 ranked it (ADR-071 §7).

    **Registered before `/work-orders/{work_order_ref}`**, and it has to stay
    there: Starlette matches in definition order, and behind the parameterised
    route this would be a 404 for a work order called "mine".

    Always the caller's own work and never a parameter, so there is nothing here
    to leak and no reason to narrow it to technicians - an engineer who opens it
    gets an empty list, which is the true answer.

    It reads the orders. The screen used to filter `GET /dispatch/round`, which
    computes what a round *would* decide, and `dispatch()` only ever places work
    that is still `queued` - so a job disappeared from the technician's screen at
    the moment a round wrote it. Nothing is `proposed` here either: work nobody
    has confirmed is not this person's.
    """
    return [
        Mine(
            ref=ref,
            status=order.status,
            priority_score=order.priority_score,
            priority_reason=order.priority_reason,
        )
        for ref, order in work.assigned_to(conn, account.user)
    ]


class Active(BaseModel):
    """A job somebody is on, for the shift lead's board (ADR-093)."""

    ref: str
    machine_id: str
    status: WorkOrderStatus
    assignees: tuple[str, ...] = ()
    assignee_names: tuple[str, ...] = ()
    reason: str
    eta_text: str | None = None


_ON_SOMEBODY = frozenset(
    {WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.HANDED_OVER}
)


class Finished(BaseModel):
    """A job closed this shift, for the board's last column (ADR-126)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    machine_id: str
    reason: str
    closed_when: str
    outcome: str
    by_names: tuple[str, ...] = ()
    note: str | None = None


@router.get("/work-orders/finished", response_model=list[Finished])
def finished_this_shift(
    conn: Db,
    rounds: Rounds,
    account: Annotated[
        Account, Depends(requires(*_MAY_READ_THE_RECORD, action="read_finished_work"))
    ],
) -> list[Finished]:
    """What was closed since the current shift began, newest first.

    Registered before `/work-orders/{work_order_ref}` for the reason `mine` is.
    In the third trial a closed job simply vanished from the board: the shift
    lead could not see that it was done, how, or what the technician wrote.
    """
    since = rounds.shift_started_at()
    if since is None:
        return []
    wording = rounds.config.wording()
    return [
        Finished(
            ref=ref,
            machine_id=str(order.machine_id),
            reason=order.reason,
            closed_when=wording.clock(closed_at),
            outcome=_where(order, ()),
            by_names=_names(conn, dict.fromkeys(segment.user for segment in order.work_segments)),
            note=order.technician_feedback,
        )
        for ref, closed_at, order in work.closed_since(conn, since)
    ]


@router.get("/work-orders/active", response_model=list[Active])
def active_work(
    conn: Db,
    rounds: Rounds,
    account: Annotated[
        Account, Depends(requires(*_MAY_READ_THE_RECORD, action="read_active_work"))
    ],
) -> list[Active]:
    """Work released to a person and not yet closed, oldest first.

    The third column of the board: what the floor is doing now. Registered
    before `/work-orders/{work_order_ref}` for the same reason `/mine` is.
    """
    return [
        Active(
            ref=ref,
            machine_id=str(order.machine_id),
            status=order.status,
            assignees=tuple(str(who.user) for who in order.assignees),
            assignee_names=_names(conn, (who.user for who in order.assignees)),
            reason=order.reason,
            eta_text=when_expected(order, rounds.config.wording(), now=rounds.clock.now()),
        )
        for ref, order, _ in work.open_orders(conn)
        if order.status in _ON_SOMEBODY
    ]


def _expires_at(proposal: Proposal, config: Config) -> datetime:
    return proposal.proposed_at + timedelta(minutes=config.policy.dispatch.proposal_expires_minutes)


def _names(conn: Connection[Any], users: Iterable[UserId]) -> tuple[str, ...]:
    """Display names for user ids; an id with no account shows as itself."""
    names = []
    for user in users:
        found = auth_repo.account(conn, user)
        names.append(found.display_name if found is not None else str(user))
    return tuple(names)


def _others(
    proposal: Proposal,
    conn: Connection[Any],
    *,
    technicians: dict[UserId, Technician],
    rostered: set[UserId],
) -> tuple[Candidate, ...]:
    """The shift's technicians who could take this job instead (ADR-132)."""
    order = work.get(conn, proposal.work_order_ref)
    skill = order.required_skill if order is not None else None
    primary = next(
        (one.user for one in proposal.assignees if one.role is AssigneeRole.PRIMARY), None
    )
    users = sorted(
        user
        for user in rostered
        if user != primary
        and why_not(
            name=str(user),
            technician=technicians.get(user),
            rostered=True,
            required_skill=skill,
        )
        is None
    )
    return tuple(
        Candidate(user=str(user), name=name)
        for user, name in zip(users, _names(conn, users), strict=True)
    )


def _assigned_because(proposal: Proposal, config: Config, conn: Connection[Any]) -> str | None:
    """ "มีทักษะช่างไฟฟ้า · มีเวลาว่างพอในกะนี้ · ตอนนี้ถืออยู่ 1 งาน" (ADR-141).

    Each part is a check the round made before it placed the job on this person:
    the skill the order asks for, and minutes left in the shift (ADR-102: with
    none, the job is unassigned rather than proposed). What they hold now is
    read from the orders, so the lead sees the load the proposal adds to.
    """
    order = work.get(conn, proposal.work_order_ref)
    primary = next(
        (one.user for one in proposal.assignees if one.role is AssigneeRole.PRIMARY), None
    )
    if order is None or primary is None:
        return None
    skill = (
        f"มีทักษะ{config.wording().skill(order.required_skill)}"
        if order.required_skill
        else "งานนี้ไม่ต้องใช้ทักษะเฉพาะ"
    )
    holding = len(work.assigned_to(conn, primary))
    now = f"ตอนนี้ถืออยู่ {holding} งาน" if holding else "ตอนนี้ไม่มีงานค้าง"
    return f"{skill} · มีเวลาว่างพอในกะนี้ · {now}"


def _proposed(
    proposal: Proposal,
    config: Config,
    conn: Connection[Any],
    others: tuple[Candidate, ...] = (),
) -> ProposalView:
    order = work.get(conn, proposal.work_order_ref)
    lost = downtime_or_unknown(order, config) if order is not None else None
    return ProposalView(
        ref=proposal.work_order_ref,
        proposed_at=proposal.proposed_at,
        assignees=tuple(str(one.user) for one in proposal.assignees),
        assignee_names=_names(conn, (one.user for one in proposal.assignees)),
        priority_score=proposal.priority_score,
        priority_reason=proposal.priority_reason,
        band=proposal.band.value if proposal.band is not None else None,
        load_ratio=proposal.load_ratio,
        shift_id=str(proposal.shift_id) if proposal.shift_id is not None else None,
        expires_at=_expires_at(proposal, config),
        others=others,
        downtime_units=round(lost, 1) if lost is not None else None,
        assigned_because=_assigned_because(proposal, config, conn),
    )


@router.get("/dispatch/proposals", response_model=list[ProposalView])
def proposals(
    conn: Db,
    config: Plant,
    rounds: Rounds,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_proposals"))],
) -> list[ProposalView]:
    """What the scheduler is waiting to be told about, oldest first.

    Read by everybody who may be shown a ranking, for ADR-005's reason: a
    technician who can see that their next job is waiting on an approval knows
    something different from one whose screen is simply empty.

    Read from the table rather than recomputed. A proposal is a decision that was
    taken and written down, and the round that took it is gone (ADR-050); asking
    `decide()` again would answer a different question - what a round would do
    now, with those orders already out of the queue.
    """
    technicians = {one.user: one for one in dispatch_repo.technicians(conn)}
    rostered = rounds.rostered_now(conn)
    return [
        _proposed(
            one,
            config,
            conn,
            _others(one, conn, technicians=technicians, rostered=rostered),
        )
        for one in dispatch_repo.pending_proposals(conn)
    ]


@router.get("/dispatch/confirmations", response_model=AgreementReport)
def confirmation_record(
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ_THE_RECORD, action="read_agreement"))],
    since: datetime | None = None,
    until: datetime | None = None,
) -> AgreementReport:
    """How far the shift lead and the scheduler agreed, and how much nobody answered.

    The report the advisor's "ต้องดู performance ไปก่อน" asks for (ADR-071 §8),
    to the shape ADR-075 fixed. It computes when asked and writes nothing, like
    the gate's report beside it, and it returns the domain reading rather than a
    view of one: the figures *are* the answer here, and a second shape for them
    would be a second place to get a denominator wrong.

    Both bounds are optional and neither has a default, because how much history
    is enough to argue from belongs to the person arguing (ADR-071 §8).
    """
    return agreement(dispatch_repo.proposal_record(conn, since=since, until=until))


def _answer(error: Exception) -> HTTPException:
    """404 for a proposal that is not there, 409 for one somebody else settled."""
    if isinstance(error, NoProposal):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(error))
    return HTTPException(status.HTTP_409_CONFLICT, str(error))


@router.post(
    "/dispatch/proposals/{work_order_ref}/confirm",
    response_model=ProposalAnswered,
    status_code=status.HTTP_201_CREATED,
)
def confirm_proposal(
    work_order_ref: str,
    conn: Db,
    clock: Time,
    rounds: Rounds,
    confirming: Confirming,
    account: Annotated[Account, Depends(requires(*_MAY_CONFIRM, action="confirm_proposal"))],
    reassignment: Reassignment | None = None,
) -> ProposalAnswered:
    """The press the advisor asked for: this goes out, to these people, now.

    **The delivery is queued here**, in the request's transaction, and not by the
    round that decided it. ADR-068 wrote the delivery row beside the placement so
    that a ticket could never be somebody's job without something knowing it had
    to go out; with a person in the middle, the transaction that makes it
    somebody's job is this one (ADR-071 §5). Queued rather than sent: the worker
    drains the outstanding rows, so a destination that is down delays a ticket
    instead of failing a supervisor's button.

    **With a body naming `assignee`, the job goes to that person instead**
    (ADR-132): the lead agrees it should go now and disagrees about who. The
    person must be an active technician on the shift running now and hold the
    skill the job asks for - the conditions a round crews by - or the request is
    refused with a sentence, before anything is written. It is recorded as
    `reassigned`, so the agreement measure does not count it as agreement.
    """
    crew: tuple[Assignee, ...] = ()
    try:
        if reassignment is not None:
            crew = _crew_for(conn, rounds, work_order_ref, reassignment.assignee)
        answered = confirming.confirm(
            conn, work_order_ref, by=account.user, role=account.role, crew=crew
        )
    except (NoProposal, AlreadyAnswered) as error:
        raise _answer(error) from error

    at = clock.now()
    deliveries.queue(conn, [WorkOrderRef(work_order_ref)], at=at)
    return ProposalAnswered(
        ref=work_order_ref,
        state=answered.state,
        at=at,
        by=str(account.user),
        given_to=_names(conn, (one.user for one in answered.confirmed_assignees)),
    )


def _crew_for(
    conn: Connection[Any], rounds: Rounds, ref: str, chosen: UserId
) -> tuple[Assignee, ...]:
    """The crew with `chosen` as primary, or a 422 saying why they cannot take it."""
    proposal = dispatch_repo.pending_proposal(conn, ref)
    if proposal is None:
        raise NoProposal(f"{ref} ไม่ได้รอการยืนยันแล้ว อาจมีคนตอบไปก่อน ลองโหลดหน้าใหม่")
    order = work.get(conn, ref)
    skill = order.required_skill if order is not None else None
    (name,) = _names(conn, [chosen])
    refusal = why_not(
        name=name,
        technician={one.user: one for one in dispatch_repo.technicians(conn)}.get(chosen),
        rostered=chosen in rounds.rostered_now(conn),
        required_skill=skill,
        skill_name=rounds.config.wording().skill(skill) if skill is not None else None,
    )
    if refusal is not None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, refusal)
    return crew_with(proposal.assignees, chosen)


@router.post(
    "/dispatch/proposals/{work_order_ref}/reject",
    response_model=ProposalAnswered,
    status_code=status.HTTP_201_CREATED,
)
def reject_proposal(
    work_order_ref: str,
    objection: Objection,
    conn: Db,
    clock: Time,
    confirming: Confirming,
    account: Annotated[Account, Depends(requires(*_MAY_CONFIRM, action="reject_proposal"))],
) -> ProposalAnswered:
    """Not now, and here is why - and the order is set aside for this shift.

    No delivery is queued, because nothing became anybody's job. The crew is
    freed at once, and no round proposes the order again until the shift ends or
    the lead brings it back (ADR-120, which replaces ADR-071 §4: proposed again
    every five minutes, a rejection read as a button that did nothing).
    """
    try:
        confirming.reject(
            conn,
            work_order_ref,
            by=account.user,
            role=account.role,
            reason=objection.reason,
        )
    except (NoProposal, AlreadyAnswered) as error:
        raise _answer(error) from error

    return ProposalAnswered(
        ref=work_order_ref,
        state=ProposalState.REJECTED,
        at=clock.now(),
        by=str(account.user),
        reason=objection.reason,
    )


@router.post(
    "/dispatch/set-aside/{work_order_ref}/bring-back",
    response_model=ProposalAnswered,
    status_code=status.HTTP_201_CREATED,
)
def bring_back(
    work_order_ref: str,
    conn: Db,
    clock: Time,
    rounds: Rounds,
    confirming: Confirming,
    account: Annotated[Account, Depends(requires(*_MAY_CONFIRM, action="bring_back_set_aside"))],
) -> ProposalAnswered:
    """The shift lead takes their "not now" back; the next round ranks the order."""
    since = rounds.shift_started_at()
    try:
        if since is None:
            raise NotSetAside(f"{work_order_ref} ไม่ได้ถูกพักไว้ในกะนี้")
        confirming.bring_back(conn, work_order_ref, by=account.user, since=since)
    except NotSetAside as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    return ProposalAnswered(
        ref=work_order_ref, state=ProposalState.REJECTED, at=clock.now(), by=str(account.user)
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


def _manual_titles(conn: Connection[Any], ids: set[str]) -> dict[str, str]:
    """ "R-2000iC Maintenance Manual (Edition 3)" per document id."""
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT document_id, title, edition FROM document WHERE document_id = ANY(%s)",
        (sorted(ids),),
    ).fetchall()
    return {row[0]: f"{row[1]} ({row[2]})" if row[2] else row[1] for row in rows}


# How many pages of a waiting draft are offered: enough to find the procedure,
# few enough that the list is read (the draft's first pages are where it starts).
_DRAFT_PAGES_SHOWN = 3


def _where_to_look(
    conn: Connection[Any], config: Config, order: WorkOrder
) -> tuple[WhereToLook, ...]:
    """The pages a waiting draft cites, then the manuals in service (ADR-118)."""
    try:
        model = config.model_of(order.machine_id)
    except KeyError:
        return ()
    symptom = work.symptom_of(conn, order)
    found: list[WhereToLook] = []
    if symptom is not None:
        waiting = playbooks_repo.awaiting_review(conn, symptom_code=symptom, machine_model=model)
        draft = playbooks_repo.proposal(conn, waiting) if waiting is not None else None
        if draft is not None:
            cited = list(dict.fromkeys((str(step.source_doc), step.page) for step in draft.steps))
            titles = _manual_titles(conn, {document for document, _ in cited})
            found += [
                WhereToLook(
                    document_id=document,
                    manual=titles.get(document, document[:12]),
                    page=page,
                    from_unapproved_draft=True,
                )
                for document, page in cited[:_DRAFT_PAGES_SHOWN]
            ]
    rows = conn.execute(
        "SELECT document_id, title, edition FROM document "
        "WHERE machine_model = %s AND status = 'active' ORDER BY uploaded_at DESC, document_id",
        (str(model),),
    ).fetchall()
    found += [
        WhereToLook(document_id=row[0], manual=f"{row[1]} ({row[2]})" if row[2] else row[1])
        for row in rows
    ]
    return tuple(found)


def pm_page_note(origin: WorkOrderOrigin, *, has_steps: bool, task_title: str | None) -> str | None:
    """Where a scheduled job with no approved steps sends the technician.

    A PM task in `plant.yaml` records an interval, not a manual page, so the
    ticket has a manual and no page to open it at. Principle 5: the screen says
    which part of the manual to read and that no page is on record, rather than
    showing a bare title or guessing a page (fourth trial, finding 11).
    """
    if origin is not WorkOrderOrigin.SCHEDULED or has_steps:
        return None
    note = (
        "งานบำรุงรักษาตามรอบนี้ยังไม่ได้บันทึกเลขหน้าในคู่มือไว้ ระบบจึงไม่ชี้หน้าให้ "
        "ให้เปิดหัวข้อตารางบำรุงรักษาตามรอบ (maintenance schedule) ในคู่มือของเครื่อง"
    )
    if task_title:
        note += f" แล้วหารายการ “{task_title}”"
    return note


def _pm_title(config: Config, order: WorkOrder) -> str | None:
    if order.pm_task_ref is None:
        return None
    for task in config.pm_tasks:
        if task.pm_task_ref == order.pm_task_ref:
            return task.title
    return None


def _symptom_of(conn: Connection[Any], order: WorkOrder) -> SymptomCode | None:
    """What the order is about, from whatever raised it."""
    if order.finding_ref is not None:
        row = conn.execute(
            "SELECT symptom_code FROM finding WHERE finding_ref = %s", (order.finding_ref,)
        ).fetchone()
        return SymptomCode(row[0]) if row else None
    if order.pm_task_ref is not None:
        row = conn.execute(
            "SELECT symptom_code FROM pm_task WHERE pm_task_ref = %s", (order.pm_task_ref,)
        ).fetchone()
        return SymptomCode(row[0]) if row else None
    return None


def _title(conn: Connection[Any], config: Config, order: WorkOrder) -> str:
    """ "MC-001 มอเตอร์สายพานร้อนเกินกำหนด": machine and symptom (fourth trial)."""
    return title(order, work.symptom_of(conn, order), config.wording())


def _also_open(
    conn: Connection[Any], config: Config, ref: str, order: WorkOrder
) -> tuple[str, ...]:
    """The other work open on this machine now, by title.

    Read with the ticket rather than written into its reason: written once, it
    went on naming a ticket that had closed (fourth trial, finding 5)."""
    if order.status.value not in work.OPEN_STATUSES:
        return ()
    return tuple(
        _title(conn, config, other)
        for other_ref, other in work.open_for_machine(conn, order.machine_id)
        if other_ref != ref
    )


def _tools(
    conn: Connection[Any], playbook_ref: str | None
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The tools the approved playbook lists, and the approver's Thai for them
    (ADR-102, ADR-130). The snapshot freezes the steps; the tool list is read
    from the served playbook and shown as that."""
    if not playbook_ref or "/" not in playbook_ref:
        return (), ()
    symptom, model = playbook_ref.split("/", 1)
    found = playbooks_repo.get(conn, SymptomCode(symptom), MachineModel(model))
    if found is None:
        return (), ()
    return tuple(found[0].tools), tuple(found[0].tools_th)


def _station(config: Config, machine_id: MachineId) -> str | None:
    """ "สถานี 3", or None for a machine the current layout does not place (ADR-048)."""
    try:
        return f"สถานี {config.station_of(machine_id).seq}"
    except KeyError:
        return None


def _station_name(config: Config, machine_id: MachineId) -> str | None:
    try:
        return config.station_of(machine_id).name
    except KeyError:
        return None


def _machine_model(config: Config, machine_id: MachineId) -> str | None:
    try:
        return str(config.model_of(machine_id))
    except KeyError:
        return None


def _reading(conn: Connection[Any], config: Config, order: WorkOrder) -> Reading | None:
    """The figures the Finding behind this order was raised on (ADR-134).

    From its `evidence`, which a detection fills with the reading and a forecast
    with the slope and, since ADR-134, the reading it was fitted up to.
    """
    if order.finding_ref is None:
        return None
    finding = findings.get(conn, order.finding_ref)
    if finding is None:
        return None
    rule_id = str(finding.rule_id).split("/", 1)[0]
    rule = next((one for one in config.rules.rules if str(one.rule_id) == rule_id), None)
    evidence = finding.evidence

    def number(key: str) -> float | None:
        value = evidence.get(key)
        return (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )

    measured = evidence.get("measured_at")
    metric = evidence.get("metric_name") or (rule.metric_name if rule else None)
    if metric is None:
        return None
    return Reading(
        metric_name=str(metric),
        metric_title=rule.metric_title if rule else None,
        unit=str(evidence["unit"]) if evidence.get("unit") else None,
        value=number("value"),
        measured_at=datetime.fromisoformat(measured) if isinstance(measured, str) else None,
        threshold=number("threshold")
        if "threshold" in evidence
        else (rule.threshold if rule else None),
        comparison=str(evidence.get("comparison") or (rule.comparison if rule else "")) or None,
        slope_per_hour=number("slope_per_hour"),
    )


def _history(
    conn: Connection[Any], config: Config, ref: str, order: WorkOrder
) -> tuple[PastJob, ...]:
    """The last three jobs closed on this machine, newest first (ADR-134)."""
    return tuple(
        PastJob(
            ref=past_ref,
            title=_title(conn, config, past),
            closed_at=closed_at,
            # `outcome` is never None on a closed row: the database refuses one.
            outcome=past.outcome or WorkOutcome.FIXED,
            minutes=past.actual_minutes,
            by=_names(conn, (one.user for one in past.assignees)),
            page=past.playbook_snapshot[0].page if past.playbook_snapshot else None,
            note=past.technician_feedback,
        )
        for past_ref, past, closed_at in work.closed_on_machine(
            conn, order.machine_id, besides=ref, limit=3
        )
    )


def _approval(conn: Connection[Any], order: WorkOrder, manuals: dict[str, str]) -> Approval | None:
    if order.snapshot_approved_by is None or order.snapshot_approved_at is None:
        return None
    revision = None
    if order.playbook_ref and "/" in order.playbook_ref:
        symptom, model = order.playbook_ref.split("/", 1)
        served = playbooks_repo.get(conn, SymptomCode(symptom), MachineModel(model))
        if served is not None and served[0].approved_at == order.snapshot_approved_at:
            revision = served[0].revision
    first = order.playbook_snapshot[0] if order.playbook_snapshot else None
    return Approval(
        approved_by=_names(conn, (order.snapshot_approved_by,))[0],
        approved_at=order.snapshot_approved_at,
        revision=revision,
        manual=manuals.get(str(first.source_doc)) if first else None,
    )


def _engineer(conn: Connection[Any], config: Config, order: WorkOrder) -> str | None:
    try:
        model = config.model_of(order.machine_id)
    except KeyError:
        return None
    approver = playbooks_repo.last_approver(conn, model)
    return _names(conn, (approver,))[0] if approver is not None else None


@router.get("/work-orders/{work_order_ref}", response_model=TicketView)
def ticket(
    work_order_ref: str,
    conn: Db,
    config: Plant,
    clock: Time,
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
    manuals = _manual_titles(conn, {str(step.source_doc) for step in order.playbook_snapshot})
    tools, tools_th = _tools(conn, order.playbook_ref)
    return TicketView(
        ref=work_order_ref,
        machine_id=str(order.machine_id),
        title=_title(conn, config, order),
        severity=order.severity,
        status=order.status,
        origin=order.origin,
        reason=order.reason,
        also_open=_also_open(conn, config, work_order_ref, order),
        priority_reason=order.priority_reason,
        priority_score=order.priority_score,
        estimated_minutes=order.estimated_minutes,
        estimate_is_fallback=order.estimate_is_fallback,
        required_skill=str(order.required_skill) if order.required_skill else None,
        required_skill_name=(
            config.wording().skill(order.required_skill) if order.required_skill else None
        ),
        station=_station(config, order.machine_id),
        required_technicians=order.required_technicians,
        assignees=tuple(str(who.user) for who in order.assignees),
        playbook_warning=order.playbook_warning,
        handover_note=order.handover_note,
        finding_kind=order.finding_kind,
        eta_text=when_expected(order, config.wording(), now=clock.now()),
        eta=order.eta,
        eta_confidence_minutes=(
            None
            if order.eta_confidence is None
            else round(order.eta_confidence.total_seconds() / 60)
        ),
        steps=tuple(
            Step(
                text=step.text,
                text_th=step.text_th,
                source_doc=str(step.source_doc),
                page=step.page,
                manual=manuals.get(str(step.source_doc)),
                kind=step.kind,
                hazards=step.hazards,
                isolation_points=step.isolation_points,
                wait_minutes=step.wait_minutes,
            )
            for step in order.playbook_snapshot
        ),
        tools=tools,
        tools_th=tools_th,
        where_to_look=() if order.playbook_snapshot else _where_to_look(conn, config, order),
        where_to_look_note=pm_page_note(
            order.origin,
            has_steps=bool(order.playbook_snapshot),
            task_title=_pm_title(config, order),
        ),
        recurrence=_recurrence(conn, order),
        station_name=_station_name(config, order.machine_id),
        machine_model=_machine_model(config, order.machine_id),
        started_at=min((one.started_at for one in order.work_segments), default=None),
        step_reached=work.step_reached(conn, work_order_ref),
        reading=_reading(conn, config, order),
        history=_history(conn, config, work_order_ref, order),
        approval=_approval(conn, order, manuals),
        engineer=_engineer(conn, config, order),
        confirmations=tuple(
            PointConfirmed(
                step=one.step,
                point_id=one.point_id,
                item=one.item,
                by=str(one.confirmed_by),
                at=one.confirmed_at,
            )
            for one in locks.confirmations(conn, work_order_ref)
        ),
        locks=tuple(
            LockOn(
                point_id=one.point_id,
                lock_no=one.lock_no,
                owner=str(one.owner),
                owner_name=_names(conn, (one.owner,))[0],
                work_order_ref=one.work_order_ref,
                step=one.step,
                applied_at=one.applied_at,
            )
            for one in locks.open_locks(conn, machine_id=order.machine_id)
        ),
        your_lock_numbers=tuple(locks.lock_numbers_of(conn, account.user)),
        missing_verify=bool(uncovered(order.playbook_snapshot)),
        unverified_points=tuple(uncovered(order.playbook_snapshot)),
        restore_checks=tuple(
            RestoreCheckView(key=one.key, label=one.label)
            for one in config.policy.safety.restore_checks
        ),
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
            f"{work_order_ref} ถูกปล่อยไปแล้ว กำลังรอรอบถัดไปจัดช่าง",
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
            f"ระบบไม่ได้กัน {work_order_ref} ไว้แล้ว ลองโหลดหน้าใหม่",
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

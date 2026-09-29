"""Per-machine health, computed when asked, from what the system already holds.

Two contributions and no third number. `HistoryContribution` is what a machine
has done before - closed work orders and the PM tasks standing against it -
and `CurrentContribution` is what it is saying now - the Findings still open.
They are returned side by side and are never combined, because the actions they
imply differ: history says schedule an inspection, now says send somebody
(ADR-072 section 2).

There are therefore **two orderings** and never one list. `by_history` ranks by
failures per hundred observed days; `by_now` ranks by the highest severity
standing open. A single ranking of machines would be the blended number ADR-072
refuses, arriving as a sort key instead of a field (ADR-076 section 2).

Two things this deliberately does not do, both of them ADR-072's:

- **It creates no work.** Nothing here returns a work order or a Finding, and
  `.importlinter` makes that structural rather than a promise - this package
  cannot reach `pdm.work`, `pdm.dispatch` or `pdm.triggers` at all.
- **It predicts nothing.** No figure here is a time to failure. ADR-020 owns
  that question, answers it with an interval and measures its error; a second
  answer would leave a technician believing whichever screen they opened.

Pure by construction: no connection reaches this file, so the whole of it is
tested against orders and Findings written out by hand (invariant 10, ADR-030).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    Finding,
    FindingKind,
    FindingStatus,
    MachineId,
    PMTask,
    Severity,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.contracts.wording import SEVERITY as SEVERITY_TH

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# One of the four history figures ADR-072 section 2 asked for, and the one
# nothing in this repository can compute. Carried as a field on every reading
# rather than left in a document, because the person it matters to is looking at
# a number and not at an ADR (principle 5, ADR-076 section 5).
AGE_AGAINST_ITS_CLASS_IS_ABSENT = (
    "อายุเครื่องเทียบกับรุ่นเดียวกัน: ระบบยังไม่มีทะเบียนเครื่องจักร (วันเริ่มใช้งาน "
    "อัตราเสียของแต่ละรุ่น) จึงบอกไม่ได้ว่าเครื่องนี้เสียบ่อยกว่าเครื่องรุ่นเดียวกันหรือไม่ "
    "ข้อมูลนี้จะมาพร้อมข้อมูลจากระบบใบสั่งงานของโรงงาน"
)

_DAYS = 86_400.0

# The shortest span a failure rate is reported over (ADR-116). Provenance:
# recorded decision. A week holds every shift pattern once; below it a single
# failure reads as several per hundred days, and an acceptance walk saw three
# minutes of history printed as 41,647.5. What is known is still shown - how
# many repairs, how many were failures - only the rate waits.
MINIMUM_OBSERVED_DAYS = 7.0


class ClosedRepair(BaseModel):
    """One closed order, reduced to what a machine's history may learn from.

    A reduction rather than the order itself, for the reason `estimates.ClosedJob`
    is one: the fields that matter here are four, and a function that took whole
    orders would be a function that could quietly start reading a sixth.

    `closed_at` is passed in rather than derived. A `WorkOrder` carries work
    segments and no close time (ADR-025), and the last segment's end is when
    somebody stopped working, which is not the same moment and would silently
    shift every history by the length of the paperwork.
    """

    model_config = _FROZEN

    work_order_ref: WorkOrderRef
    machine_id: MachineId
    closed_at: datetime
    origin: WorkOrderOrigin
    outcome: WorkOutcome

    @property
    def is_failure(self) -> bool:
        """Something was wrong with this machine and somebody dealt with it.

        Scheduled work is excluded whatever it found: a PM task that replaced a
        worn part on time is the system working, and counting it as a failure
        would rank the best-maintained machines highest. Manual work is included,
        because a person reporting a fault that turned out to be real is a
        failure that happened to be noticed by eye rather than by a rule
        (ADR-010's three origins, read for what each one means here).
        """
        return (
            self.origin is not WorkOrderOrigin.SCHEDULED
            and self.outcome is not WorkOutcome.NO_PROBLEM_FOUND
        )

    @property
    def is_false_alarm(self) -> bool:
        """Somebody was sent and found nothing. Counted, and not ranked on.

        A machine whose orders keep closing `no_problem_found` has a rule problem
        rather than a machine problem, and ADR-073 owns what to do about it.
        Ranking it up would send somebody to a healthy machine on the strength of
        having been sent there for nothing before (ADR-076 section 3).
        """
        return self.outcome is WorkOutcome.NO_PROBLEM_FOUND

    @classmethod
    def from_order(
        cls,
        work_order_ref: WorkOrderRef,
        order: WorkOrder,
        *,
        closed_at: datetime,
    ) -> ClosedRepair:
        if order.status is not WorkOrderStatus.CLOSED or order.outcome is None:
            raise ValueError(
                "only a closed order is history: an open one is a job in progress, and "
                "counting it would report a failure the machine has not finished having"
            )
        return cls(
            work_order_ref=work_order_ref,
            machine_id=order.machine_id,
            closed_at=closed_at,
            origin=order.origin,
            outcome=order.outcome,
        )


class HistoryContribution(BaseModel):
    """What this machine has done before, and over how much evidence.

    Every count is carried beside the span it was counted over. "0.8 failures per
    hundred days" reads the same whether it rests on a year or on a fortnight,
    and only one of those is worth acting on (ADR-076 section 4).
    """

    model_config = _FROZEN

    # The window every machine in one assessment is counted over - the same span
    # for all of them, so the rates compare. A machine whose first record is late
    # did not fail earlier, and that is a fact about the machine rather than
    # about the evidence.
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    observed_days: float = Field(default=0.0, ge=0.0)

    closed_orders: int = Field(default=0, ge=0)
    failures: int = Field(default=0, ge=0)
    # None rather than zero when there is no span to divide by. Zero would say
    # "this machine does not fail", which is a claim, and the honest answer here
    # is that nothing has been observed yet (principle 5).
    failures_per_100_days: float | None = None

    last_failure_at: datetime | None = None
    days_since_last_failure: float | None = None

    # Reported, and deliberately not in the ordering: a machine with overdue PM
    # wants those tasks scheduled, which is a different thing to do than sending
    # somebody to look at it (ADR-076 section 3).
    pm_completed: int = Field(default=0, ge=0)
    pm_overdue: int = Field(default=0, ge=0)
    pm_overdue_days: float | None = None

    # Same footing, sharper reason: this is evidence about a rule (ADR-073).
    false_alarms: int = Field(default=0, ge=0)

    # Figures ADR-072 asked for that could not be computed, named rather than
    # dropped. Never silently empty: section 5 of ADR-076 has one entry in it.
    absent: tuple[str, ...] = ()

    reason: str = Field(min_length=1)


class CurrentContribution(BaseModel):
    """What this machine is saying now: the Findings still standing open.

    Counts and the worst severity, and nothing derived. The ETA is repeated from
    the Finding that carries it and is not recomputed here - ADR-020 owns
    prediction, and a second answer to "when will this fail" is worse than one
    (ADR-072 section 6).
    """

    model_config = _FROZEN

    # Open and acknowledged both count as standing: somebody having seen a
    # Finding does not make the machine well.
    open_findings: int = Field(default=0, ge=0)
    acknowledged: int = Field(default=0, ge=0)
    detected: int = Field(default=0, ge=0)
    predicted: int = Field(default=0, ge=0)

    highest_severity: Severity | None = None

    soonest_eta: datetime | None = None
    hours_to_soonest_eta: float | None = None

    reason: str = Field(min_length=1)


class MachineHealth(BaseModel):
    """One machine's standing reading: two contributions, and no third figure.

    There is deliberately no `score` here, and adding one is the change this
    whole record exists to refuse. "MC-012 is at 61%" tells a supervisor nothing
    they can act on and hides which of the two halves moved (ADR-072 section 2).
    """

    model_config = _FROZEN

    machine_id: MachineId
    history: HistoryContribution
    now: CurrentContribution


def assess(
    machines: Sequence[MachineId],
    *,
    repairs: Sequence[ClosedRepair] = (),
    pm_tasks: Sequence[PMTask] = (),
    findings: Sequence[Finding] = (),
    now: datetime,
    observed_from: datetime | None = None,
) -> tuple[MachineHealth, ...]:
    """A reading for every machine asked about, in the order they were asked.

    `machines` is the list rather than whatever the records happen to mention, so
    a machine with no history at all still gets a row saying so. A machine that
    has never failed and a machine nobody has any records for look identical in a
    list built from records, and they are not the same thing.

    `now` is passed in and never read from a clock: this file may not have one
    (ADR-028), and a health figure that changed with the wall clock could not be
    tested at all.

    `observed_from` defaults to the earliest closed order in the whole set. One
    span for every machine, so the rates compare (ADR-076 section 4).
    """
    if observed_from is None and repairs:
        observed_from = min(repair.closed_at for repair in repairs)
    if observed_from is not None and observed_from > now:
        raise ValueError("the observation window cannot start after the moment it is read at")

    span_days = 0.0 if observed_from is None else (now - observed_from).total_seconds() / _DAYS

    return tuple(
        MachineHealth(
            machine_id=machine_id,
            history=_history_of(
                machine_id,
                [repair for repair in repairs if repair.machine_id == machine_id],
                [task for task in pm_tasks if task.machine_id == machine_id],
                now=now,
                observed_from=observed_from,
                span_days=span_days,
            ),
            now=_current_of(
                machine_id,
                [finding for finding in findings if finding.machine_id == machine_id],
                now=now,
            ),
        )
        for machine_id in machines
    )


def _history_of(
    machine_id: MachineId,
    repairs: Sequence[ClosedRepair],
    pm_tasks: Sequence[PMTask],
    *,
    now: datetime,
    observed_from: datetime | None,
    span_days: float,
) -> HistoryContribution:
    failures = [repair for repair in repairs if repair.is_failure]
    false_alarms = [repair for repair in repairs if repair.is_false_alarm]
    pm_done = [repair for repair in repairs if repair.origin is WorkOrderOrigin.SCHEDULED]

    last_failure = max((repair.closed_at for repair in failures), default=None)
    since_last = None if last_failure is None else (now - last_failure).total_seconds() / _DAYS

    rate = None if span_days < MINIMUM_OBSERVED_DAYS else len(failures) / span_days * 100.0

    overdue = [task for task in pm_tasks if task.is_due(now)]
    worst_overdue = (
        None
        if not overdue
        else max((now - task.due_at).total_seconds() / _DAYS for task in overdue)
    )
    # Overdue since when, for a task nobody has ever recorded as done? Since it
    # was registered, which is a fact about this system and not about the
    # machine. The count travels into the sentence so that a supervisor reading
    # "overdue by 3 days" is not told the belt was changed three days late when
    # nobody knows when it was changed (ADR-083 section 4).
    unrecorded = sum(1 for task in overdue if task.last_done_at is None)

    return HistoryContribution(
        observed_from=observed_from,
        observed_to=None if observed_from is None else now,
        observed_days=span_days,
        closed_orders=len(repairs),
        failures=len(failures),
        failures_per_100_days=rate,
        last_failure_at=last_failure,
        days_since_last_failure=since_last,
        pm_completed=len(pm_done),
        pm_overdue=len(overdue),
        pm_overdue_days=worst_overdue,
        false_alarms=len(false_alarms),
        absent=(AGE_AGAINST_ITS_CLASS_IS_ABSENT,),
        reason=_history_reason(
            machine_id,
            failures=len(failures),
            rate=rate,
            span_days=span_days,
            since_last=since_last,
            pm_overdue=len(overdue),
            worst_overdue=worst_overdue,
            unrecorded=unrecorded,
            false_alarms=len(false_alarms),
        ),
    )


def _history_reason(
    machine_id: MachineId,
    *,
    failures: int,
    rate: float | None,
    span_days: float,
    since_last: float | None,
    pm_overdue: int,
    worst_overdue: float | None,
    unrecorded: int,
    false_alarms: int,
) -> str:
    """A sentence a supervisor can act on, and one they can check.

    Every clause names the count it came from. A reason that said "history is
    poor" would be the blended number of ADR-072 section 2 written out in words.
    """
    if rate is None and span_days > 0.0:
        head = (
            f"ประวัติของ {machine_id} มีแค่ {span_days:.1f} วัน ยังสั้นเกินกว่าจะบอกอัตราการเสีย "
            f"(ต้องอย่างน้อย {MINIMUM_OBSERVED_DAYS:.0f} วัน) · เสีย {failures} ครั้งในช่วงนี้"
        )
    elif rate is None:
        head = f"ยังไม่มีใบงานที่ปิดแล้วของ {machine_id} ในข้อมูลที่มี"
    elif failures == 0:
        head = f"{machine_id} ไม่เสียเลยตลอด {span_days:.0f} วันที่นับ ({rate:.1f} ครั้งต่อ 100 วัน)"
    else:
        head = f"{machine_id} เสีย {failures} ครั้งใน {span_days:.0f} วันที่นับ ({rate:.1f} ครั้งต่อ 100 วัน)"
        if since_last is not None:
            head += f" ครั้งล่าสุดเมื่อ {since_last:.0f} วันก่อน"

    clauses = [head]
    if pm_overdue and worst_overdue is not None:
        clause = (
            f"งานบำรุงรักษาตามแผนเลยกำหนด {pm_overdue} งาน นานสุด {worst_overdue:.0f} วัน "
            f"ควรจัดเข้าแผน ไม่ใช่เหตุให้ส่งคนไปทันที"
        )
        if unrecorded:
            clause += f" ในนี้ {unrecorded} งานไม่เคยมีบันทึกว่าทำ จึงนับวันเลยกำหนดตั้งแต่วันที่ลงทะเบียนเข้าระบบ"
        clauses.append(clause)
    if false_alarms:
        clauses.append(
            f"ปิดงานแบบไม่พบปัญหา {false_alarms} ครั้ง แปลว่าเกณฑ์แจ้งเตือนอาจไวเกินไป ไม่ได้แปลว่าเครื่องมีปัญหา"
        )
    return " · ".join(clauses)


def _current_of(
    machine_id: MachineId,
    findings: Sequence[Finding],
    *,
    now: datetime,
) -> CurrentContribution:
    standing = [
        finding
        for finding in findings
        if finding.status in (FindingStatus.OPEN, FindingStatus.ACKNOWLEDGED)
    ]
    if not standing:
        return CurrentContribution(
            reason=f"ตอนนี้ {machine_id} ไม่มีเรื่องค้าง",
        )

    acknowledged = [f for f in standing if f.status is FindingStatus.ACKNOWLEDGED]
    predicted = [f for f in standing if f.kind is FindingKind.PREDICTED]
    detected = [f for f in standing if f.kind is FindingKind.DETECTED]
    worst = max(standing, key=lambda finding: finding.severity.rank).severity
    etas = [f.eta for f in predicted if f.eta is not None]
    soonest = min(etas, default=None)
    hours = None if soonest is None else (soonest - now).total_seconds() / 3600.0

    clauses = [
        f"{machine_id} มีสัญญาณผิดปกติค้างอยู่ {len(standing)} เรื่อง หนักสุดระดับ{SEVERITY_TH[worst.value]}"
    ]
    if detected:
        clauses.append(f"เกินเกณฑ์แล้ว {len(detected)} เรื่อง")
    if predicted and soonest is not None and hours is not None:
        clauses.append(f"คาดว่าจะเกินเกณฑ์ {len(predicted)} เรื่อง เร็วสุดในอีกราว {hours:.0f} ชั่วโมง")
    if acknowledged:
        clauses.append(f"รับทราบแล้ว {len(acknowledged)} เรื่อง แต่เครื่องยังไม่ได้รับการแก้")
    return CurrentContribution(
        open_findings=len(standing),
        acknowledged=len(acknowledged),
        detected=len(detected),
        predicted=len(predicted),
        highest_severity=worst,
        soonest_eta=soonest,
        hours_to_soonest_eta=hours,
        reason=" · ".join(clauses),
    )


def by_history(readings: Iterable[MachineHealth]) -> tuple[MachineHealth, ...]:
    """Machines that have failed most often, over the same observed span.

    Ties are broken by the most recent failure first, then by machine id so that
    the order is total and a measurement of it reproduces. Machines with no rate
    at all - no records handed over - sort last, because "nothing is known" is
    not the same claim as "nothing has happened" (ADR-076 section 2).

    PM standing and the false-alarm count are **not** keys here. Both are on the
    reading, both are displayed, and both mean something a supervisor does
    differently about (ADR-076 section 3).
    """

    def key(reading: MachineHealth) -> tuple[bool, float, float, str]:
        rate = reading.history.failures_per_100_days
        since = reading.history.days_since_last_failure
        return (
            rate is None,
            -(rate or 0.0),
            float("inf") if since is None else since,
            str(reading.machine_id),
        )

    return tuple(sorted(readings, key=key))


def by_now(readings: Iterable[MachineHealth]) -> tuple[MachineHealth, ...]:
    """Machines with the worst thing standing open against them right now.

    Severity first, then how many are open, then the soonest forecast crossing.
    Machines with nothing open sort last. This is an ordering of what is on the
    machines, not a prediction of what will be: the ETA is a tie-break among
    machines that already have a Finding, and it never promotes one that has
    none.
    """

    def key(reading: MachineHealth) -> tuple[bool, int, int, float, str]:
        worst = reading.now.highest_severity
        hours = reading.now.hours_to_soonest_eta
        return (
            worst is None,
            -(worst.rank if worst is not None else 0),
            -reading.now.open_findings,
            float("inf") if hours is None else hours,
            str(reading.machine_id),
        )

    return tuple(sorted(readings, key=key))

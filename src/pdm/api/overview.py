"""The two read paths behind the overview screen (ADR-050, ADR-060, ADR-063).

`/overview/gaps` is what the system has no answer for yet; `/overview/line` is
what the line is doing right now. Both obey the same rule, which is the one the
screen is built around: **show operational state that is already computed and
that somebody can act on now.** Nothing here invents an aggregate in order to
have something to display, and the test for every figure is one question - when
this number is bad, who does what immediately?

## What the system has no answer for yet (design.md 4, ADR-038, ADR-060)

A symptom arriving with no playbook is queued for authoring and ordered by how
often it is seen, so the system works out for itself which playbook is worth
writing next. That mechanism has been built for several slices and there has been
nowhere to look at it, which leaves an engineer choosing what to write next by
memory - and that choice is the one that decides whether the store ever covers
the long tail.

Three lists, and every figure on them is a count of rows that already exist:
Findings that were raised, proposals that are pending, playbooks the withdrawal
cascade flagged. **Nothing here computes an aggregate in order to have something
to display** (ADR-050): no summary table, no scheduled recomputation, and no
number a reader cannot act on. The test for each list is the same one the
overview screen has to pass - *when this number is bad, who does what
immediately?* - and each answers it with an identifier that takes somebody
straight to the queue.

## The line (ADR-020, ADR-021, ADR-050)

The advisor's first requirement was "monitor **and** predict", and until this
endpoint both were visible in exactly one place: a ticket in one technician's
hand, which is a monitoring system nobody can watch. Two things it carries look
like detail and are not - the buffers between stations, without which a reader
cannot see why the ranking is what it is (ADR-021), and the prediction interval,
which is the half of an ETA a person actually plans around (ADR-020).
"""

from __future__ import annotations

from collections.abc import Callable, Container, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, model_validator

from pdm.api.deps import Db, Plant, Rounds, Time, requires
from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    Line,
    MachineId,
    MachineModel,
    PMTask,
    Role,
    RuleId,
    Severity,
    Station,
    StationId,
    SymptomCode,
    WorkOrderRef,
)
from pdm.contracts.wording import Wording
from pdm.health import ClosedRepair, MachineHealth, assess, by_history, by_now
from pdm.platform.auth.domain import Account
from pdm.playbooks import repo as playbooks
from pdm.playbooks.domain import PendingForPair
from pdm.triggers import repo as triggers
from pdm.triggers.domain import SymptomSeen
from pdm.work import repo as work

router = APIRouter(tags=["overview"])

# An engineer decides what to write next; a shift lead is the person who asks
# why the queue is not moving (ADR-024). Neither list is a technician's: what a
# technician needs from a missing playbook is the honest "not found" on their own
# ticket, which is principle 5 and a different screen.
_MAY_READ = (Role.ENGINEER, Role.SUPERVISOR)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SymptomGap(BaseModel):
    """One symptom, on one machine model, with nothing approved to serve for it.

    `machine_model` is half the identifier of a playbook (ADR-018) and half of
    what a drafting request takes, so this row is what the overview's
    "[ Write it ]" button posts to `/playbooks/drafts`.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel
    # The symptom as the plant names it (ADR-093), for the screen to print.
    title: str | None = None

    # Findings raised, then firings within them. Ranked on the first, for the
    # reason `SymptomSeen` records: one channel stuck over its threshold all
    # morning is one event, however many times the rule fired.
    findings: int
    occurrences: int
    machines: tuple[MachineId, ...]

    first_seen: datetime
    last_seen: datetime

    # Whether somebody has already asked for this one. Without it the row reads
    # as "nobody has done anything", and the button posts a second drafting job
    # for work that is already queued behind the one GPU (ADR-029, ADR-040).
    proposals_waiting: int = 0


class ModelQueue(BaseModel):
    """The review queue for one machine model, which is how it is worked.

    Grouped rather than listed because a reviewer stays in one context: reading
    two manuals alternately is how a step from the wrong model gets waved
    through, which is the one thing ADR-015's recall setting does not relax.
    """

    model_config = _FROZEN

    machine_model: MachineModel
    waiting: int
    oldest: datetime


class FlaggedPlaybook(BaseModel):
    """A playbook being served right now with a warning on it (ADR-018).

    On this screen because it is the only list that says how much of what
    technicians are working from is out of date. The row is not a fault; it is a
    debt, and one an engineer clears in the same queue as everything else.
    """

    model_config = _FROZEN

    title: str | None = None

    symptom_code: SymptomCode
    machine_model: MachineModel
    revision: int
    review_reason: str | None = None


class Unanswered(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[SymptomGap, ...]


class AwaitingReview(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[ModelQueue, ...]


class ManualChanged(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[FlaggedPlaybook, ...]


class Gaps(BaseModel):
    """The three lists, each with its total beside the rows returned.

    The totals are of everything found, not of what fits: a list truncated to the
    first twenty rows still reports that there are sixty, because a silent cap
    reads as "that is all there is" (ADR-045's rule about what a summary owes its
    reader, one screen up).
    """

    model_config = _FROZEN

    at: datetime
    no_playbook: Unanswered
    awaiting_review: AwaitingReview
    manual_changed: ManualChanged

    # Machines that raised Findings and are not in `plant.yaml` any more.
    # Reported rather than dropped, for ADR-048's reason: their symptoms cannot
    # be filed under a machine model, so they cannot be drafted for, and a gap
    # list that quietly discarded them would say the store covers work it does
    # not. Every round already counts the same drift.
    unplaced_machines: tuple[MachineId, ...] = ()


@dataclass
class _Fold:
    """One gap being accumulated across the machines of one model.

    Mutable, private, and never returned: the row that leaves this module is a
    frozen `SymptomGap`. Folding into a dict of dicts was the first version and
    cost more in casts than the class costs in lines.
    """

    findings: int
    occurrences: int
    machines: set[MachineId]
    first_seen: datetime
    last_seen: datetime

    def absorb(self, row: SymptomSeen) -> None:
        self.findings += row.findings
        self.occurrences += row.occurrences
        self.machines.add(row.machine_id)
        self.first_seen = min(self.first_seen, row.first_seen)
        self.last_seen = max(self.last_seen, row.last_seen)


def rank_gaps(
    seen: Iterable[SymptomSeen],
    *,
    model_of: Callable[[MachineId], MachineModel],
    served: set[tuple[SymptomCode, MachineModel]],
    pending: Iterable[PendingForPair],
) -> tuple[list[SymptomGap], list[MachineId]]:
    """Fold what was seen onto machine models, drop what is answered, rank.

    Pure, and separate from the handler for the usual reason (invariant 10): the
    ordering is the whole content of the first list, and it should be testable
    without a database, a session and a plant.

    What is ranked, and what counts as answered, is ADR-060. Findings are per
    machine and playbooks are per model (ADR-018), so the fold is where the two
    meet. A symptom on four machines of one model is one gap
    worth four events, not four gaps - the playbook that answers it is one row.
    """
    waiting = {(row.symptom_code, row.machine_model): row.waiting for row in pending}
    folded: dict[tuple[SymptomCode, MachineModel], _Fold] = {}
    unplaced: set[MachineId] = set()

    for row in seen:
        try:
            model = model_of(row.machine_id)
        except KeyError:
            # The layout moved on and this machine went with it. Named, not
            # silently discarded (ADR-048 section 3).
            unplaced.add(row.machine_id)
            continue

        pair = (row.symptom_code, model)
        if pair in served:
            continue

        gathered = folded.get(pair)
        if gathered is None:
            folded[pair] = _Fold(
                findings=row.findings,
                occurrences=row.occurrences,
                machines={row.machine_id},
                first_seen=row.first_seen,
                last_seen=row.last_seen,
            )
            continue
        gathered.absorb(row)

    rows = [
        SymptomGap(
            symptom_code=symptom_code,
            machine_model=model,
            findings=gathered.findings,
            occurrences=gathered.occurrences,
            machines=tuple(sorted(gathered.machines)),
            first_seen=gathered.first_seen,
            last_seen=gathered.last_seen,
            proposals_waiting=waiting.get((symptom_code, model), 0),
        )
        for (symptom_code, model), gathered in folded.items()
    ]
    # Most often seen first, then the most recent: two symptoms seen twice each
    # are not equally worth writing if one of them stopped in March. The pair
    # itself is the last key so that the same data always ranks the same way and
    # a test can say what the order is rather than what it is not.
    rows.sort(
        key=lambda gap: (
            -gap.findings,
            -gap.occurrences,
            -gap.last_seen.timestamp(),
            gap.symptom_code,
            gap.machine_model,
        )
    )
    return rows, sorted(unplaced)


def group_by_model(pending: Iterable[PendingForPair]) -> list[ModelQueue]:
    """The pending proposals as the reviewer meets them: one model at a time."""
    counted: dict[MachineModel, ModelQueue] = {}
    for row in pending:
        current = counted.get(row.machine_model)
        if current is None:
            counted[row.machine_model] = ModelQueue(
                machine_model=row.machine_model, waiting=row.waiting, oldest=row.oldest
            )
            continue
        counted[row.machine_model] = ModelQueue(
            machine_model=row.machine_model,
            waiting=current.waiting + row.waiting,
            oldest=min(current.oldest, row.oldest),
        )
    # Oldest queue first: the model nobody has looked at for three weeks is the
    # one the screen should name, not the one whose name sorts first.
    return sorted(counted.values(), key=lambda group: (group.oldest, group.machine_model))


def _titled(station: StationView, wording: Wording) -> StationView:
    if station.symptom_code is None:
        return station
    return station.model_copy(update={"symptom_title": wording.symptom(station.symptom_code)})


@router.get("/overview/gaps", response_model=Gaps)
def gaps(
    conn: Db,
    clock: Time,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_gaps"))],
    # Bounded like every other list route, and the total is returned beside it so
    # the bound is visible rather than silent.
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Gaps:
    """Three questions an engineer otherwise answers from memory.

    Read-only, computed from the rows as they stand at the moment of asking, and
    stamped with when that was - a screen reporting a queue has to say whether it
    is describing now or five minutes ago (ADR-050).
    """
    pending = playbooks.pending_by_pair(conn)
    ranked, unplaced = rank_gaps(
        triggers.symptoms_seen(conn),
        model_of=plant.model_of,
        served=playbooks.served_pairs(conn),
        pending=pending,
    )
    wording = plant.wording()
    ranked = [row.model_copy(update={"title": wording.symptom(row.symptom_code)}) for row in ranked]
    flagged = [
        FlaggedPlaybook(
            title=wording.symptom(playbook.symptom_code),
            symptom_code=playbook.symptom_code,
            machine_model=playbook.machine_model,
            revision=playbook.revision,
            review_reason=review_reason,
        )
        for playbook, review_reason in playbooks.needing_review(conn)
    ]
    by_model = group_by_model(pending)

    return Gaps(
        at=clock.now(),
        no_playbook=Unanswered(count=len(ranked), rows=tuple(ranked[:limit])),
        awaiting_review=AwaitingReview(
            count=sum(group.waiting for group in by_model), rows=tuple(by_model[:limit])
        ),
        manual_changed=ManualChanged(count=len(flagged), rows=tuple(flagged[:limit])),
        unplaced_machines=tuple(unplaced),
    )


# ─────────────────────────────────────────────────────────────
# The line, as the overview will draw it (ADR-020, ADR-021, ADR-050, ADR-063)
# ─────────────────────────────────────────────────────────────


class StationState(StrEnum):
    """What one position on the line is doing, in one word.

    Three states and no fourth. "Degraded", "warning" and the rest are gradations
    of the same two facts - it has crossed, or it is going to - and a scale a
    reader has to interpret is a scale two readers interpret differently.
    """

    NORMAL = "normal"
    PREDICTED = "predicted"
    OVER_THRESHOLD = "over_threshold"


class StationView(BaseModel):
    """One station: where it sits, what it buys, and what is wrong with it.

    The buffer is here because ADR-021 prices downtime with it, and a screen
    that could not draw it would leave a reader unable to see why the ranking is
    what it is: a red station with twenty units in front of it is not a red
    bottleneck, and equal boxes say they are.
    """

    model_config = _FROZEN

    station_id: StationId
    seq: int
    # Both, deliberately. The units are what `plant.yaml` holds and what an
    # engineer argues about; the minutes are that at the line's takt, which is
    # the only form comparable with a repair time (ADR-021).
    buffer_units: int
    buffer_minutes: float
    bottleneck: bool
    bottleneck_multiplier: float
    machines: tuple[MachineId, ...] = ()

    state: StationState = StationState.NORMAL

    # The fault the marker stands for, when there is one. A station is one marker
    # and may hold several faults, so `live_findings` says how many there are:
    # showing one of three without saying so reads as though there were one.
    machine_id: MachineId | None = None
    component: ComponentLabel | None = None
    symptom_code: SymptomCode | None = None
    # The symptom as the plant names it, for the screen to print instead of the
    # code (ADR-093; the owner's second trial read "SYM-014 · belt_motor").
    symptom_title: str | None = None
    severity: Severity | None = None
    rule_id: RuleId | None = None
    live_findings: int = 0

    over_threshold_minutes: int | None = None
    eta: datetime | None = None
    eta_confidence_minutes: int | None = None

    @model_validator(mode="after")
    def _a_prediction_is_never_shown_without_its_interval(self) -> StationView:
        """ADR-020's rule, enforced by the shape rather than by the handler.

        "About six hours" reads as more trustworthy than "about six hours, give
        or take two", and it is a promise the system cannot keep. The tidier
        screen is the dishonest one, so the model refuses to be built that way -
        including by whatever assembles this later for a test or a fixture.
        """
        predicted = self.state is StationState.PREDICTED
        if predicted and (self.eta is None or self.eta_confidence_minutes is None):
            raise ValueError(
                "a predicted station carries its eta and its interval together, always (ADR-020)"
            )
        if not predicted and (self.eta is not None or self.eta_confidence_minutes is not None):
            raise ValueError(
                f"a {self.state.value} station has no crossing to expect; an eta on one would "
                "read as a forecast nobody made"
            )
        over = self.state is StationState.OVER_THRESHOLD
        if over is (self.over_threshold_minutes is None):
            raise ValueError(
                "over_threshold_minutes belongs to a station that is over its threshold, and to "
                "no other"
            )
        return self


class LineView(BaseModel):
    """One production line and its stations, in the order units pass through."""

    model_config = _FROZEN

    line_id: str
    # The seconds the buffers are measured in. On the response so a screen
    # redrawing at a different scale does not have to fetch the plant.
    takt_seconds: float
    stations: tuple[StationView, ...] = ()


class ShiftBand(BaseModel):
    """How loaded the shift is, taken from the round rather than recomputed.

    Every figure here is one the round already produced (ADR-050). `held` is a
    count and not the list, because the list is `/dispatch/round`'s answer and
    two endpoints returning the same rows is how they come to disagree - the
    screen asks the other one when the shift lead opens the panel.
    """

    model_config = _FROZEN

    shift_id: str | None = None
    on_date: date | None = None
    band: str
    load_ratio: float | None = None
    capacity_minutes: int
    committed_minutes: int
    technicians_on_shift: int
    open_orders: int
    held: int
    summary: str


class LineOverview(BaseModel):
    """The screen the project is demonstrated from, as data.

    `at` is the moment the whole response describes - the one the round was
    computed at, so the stations and the shift band cannot be reporting two
    different instants (ADR-050).
    """

    model_config = _FROZEN

    at: datetime
    # A fact about the plant rather than about the device holding the screen: a
    # supervisor reading this from a laptop set to UTC still has to see the
    # shift's own clock (ADR-045 §7).
    timezone: str
    lines: tuple[LineView, ...] = ()
    shift: ShiftBand
    # Machines with a live Finding and no station in `plant.yaml`. Named rather
    # than dropped, exactly as the gap list names them: their fault cannot be
    # drawn anywhere, and a line that quietly omitted them would read as quieter
    # than it is (ADR-048 §3).
    unplaced_machines: tuple[MachineId, ...] = ()


def group_by_machine(
    findings: Iterable[Finding], *, known: Container[MachineId]
) -> tuple[dict[MachineId, list[Finding]], list[MachineId]]:
    """Live Findings against the machines that stand somewhere, and the rest."""
    grouped: dict[MachineId, list[Finding]] = {}
    unplaced: set[MachineId] = set()
    for finding in findings:
        if finding.machine_id not in known:
            unplaced.add(finding.machine_id)
            continue
        grouped.setdefault(finding.machine_id, []).append(finding)
    return grouped, sorted(unplaced)


def _worst_detected(findings: Sequence[Finding]) -> Finding:
    """The fault the marker stands for, among several that have crossed.

    Severity first, because that is what the load gate admits on and what a
    shift lead is deciding between; then the one that has been over longest,
    because at equal severity the older fault is the one nobody has reached.
    The machine and the rule end the key so the same data always draws the same
    screen.
    """
    return min(
        findings,
        key=lambda one: (-one.severity.rank, one.detected_at, one.machine_id, one.rule_id),
    )


def _soonest_predicted(findings: Sequence[Finding]) -> Finding:
    """Among forecasts, the crossing that arrives first.

    Not the most severe: a critical crossing in nine hours and a medium one in
    two are decided in the other order, and the second is the one the shift in
    front of somebody has to absorb (ADR-011's quiet-shift argument).
    """
    return min(
        findings,
        # `eta` is not optional here: the caller admits only predictions that
        # carry one, which the contract guarantees they all do (ADR-020).
        key=lambda one: (one.eta, -one.severity.rank, one.machine_id, one.rule_id),
    )


def _marker(view: dict[str, object], finding: Finding) -> None:
    """Fill in the fault a station's marker stands for."""
    view["machine_id"] = finding.machine_id
    view["component"] = finding.component
    view["symptom_code"] = finding.symptom_code
    view["severity"] = finding.severity
    view["rule_id"] = finding.rule_id


def read_the_line(
    line: Line,
    stations: Iterable[Station],
    *,
    live: Mapping[MachineId, Sequence[Finding]],
    now: datetime,
) -> tuple[StationView, ...]:
    """Fold the live Findings onto the layout, in the order units flow.

    Pure, and separate from the handler for the reason invariant 10 gives: what
    a station shows when it holds two faults at once is the whole content of the
    top band, and it should be assertable without a database, a session and a
    plant.

    **A crossing that has happened outranks one that is expected.** Both can be
    live at the same station - ADR-023 §7 has a detection supersede an open
    prediction, and until it does there are two - and the one already costing
    production is the one a shift lead is deciding about.
    """
    drawn: list[StationView] = []
    for station in sorted(stations, key=lambda one: (one.seq, one.station_id)):
        here = [
            finding for machine_id in station.machine_ids for finding in live.get(machine_id, ())
        ]
        view: dict[str, object] = {
            "station_id": station.station_id,
            "seq": station.seq,
            "buffer_units": station.buffer_units,
            "buffer_minutes": station.buffer_minutes(line),
            # The only signal `plant.yaml` carries for it. A station whose
            # downtime is priced above the rest of the line is a bottleneck; the
            # multiplier is returned beside the flag so a reader can see by how
            # much rather than take the word for it (ADR-021).
            "bottleneck": station.bottleneck_multiplier > 1.0,
            "bottleneck_multiplier": station.bottleneck_multiplier,
            "machines": station.machine_ids,
            "live_findings": len(here),
        }

        crossed = [one for one in here if one.kind is FindingKind.DETECTED]
        expected = [
            one for one in here if one.kind is FindingKind.PREDICTED and one.eta is not None
        ]

        if crossed:
            leading = _worst_detected(crossed)
            _marker(view, leading)
            view["state"] = StationState.OVER_THRESHOLD
            # Floored at zero rather than allowed negative: a Finding detected
            # after `now` is a clock that moved, and "-3 minutes over threshold"
            # is not something to put in front of somebody at a machine.
            view["over_threshold_minutes"] = max(
                0, int((now - leading.detected_at).total_seconds() // 60)
            )
        elif expected:
            leading = _soonest_predicted(expected)
            _marker(view, leading)
            view["state"] = StationState.PREDICTED
            view["eta"] = leading.eta
            assert leading.eta_confidence is not None  # the contract guarantees the pair
            view["eta_confidence_minutes"] = round(leading.eta_confidence.total_seconds() / 60)
        else:
            view["state"] = StationState.NORMAL

        drawn.append(StationView.model_validate(view))
    return tuple(drawn)


@router.get("/overview/line", response_model=LineOverview)
def line_overview(
    conn: Db,
    plant: Plant,
    rounds: Rounds,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_line_overview"))],
) -> LineOverview:
    """Monitor and predict, on one screen, for the shift in front of somebody.

    Three reads and no arithmetic of its own: the layout from `plant.yaml`, the
    live Findings from the table, and the shift from the same `dispatch()` the
    rounds use. Nothing is stored and nothing is summarised into a figure that
    could drift from what the scheduler thinks (ADR-050).
    """
    decided = rounds.decide(conn)
    known = {
        machine_id for station in plant.stations.values() for machine_id in station.machine_ids
    }
    grouped, unplaced = group_by_machine(triggers.live(conn).values(), known=known)
    wording = plant.wording()

    return LineOverview(
        # The round's own moment, so the stations and the band describe one
        # instant. A second clock read here would put them milliseconds apart
        # and invite a reader to compare them.
        at=decided.at,
        timezone=plant.plant.timezone,
        lines=tuple(
            LineView(
                line_id=str(line_id),
                takt_seconds=line.takt_seconds,
                stations=tuple(
                    _titled(station, wording)
                    for station in read_the_line(
                        line,
                        [one for one in plant.stations.values() if one.line_id == line_id],
                        live=grouped,
                        now=decided.at,
                    )
                ),
            )
            for line_id, line in sorted(plant.lines.items())
        ),
        shift=ShiftBand(
            shift_id=str(decided.shift_id) if decided.shift_id is not None else None,
            on_date=decided.on_date,
            band=decided.band.value,
            load_ratio=decided.load_ratio,
            capacity_minutes=decided.capacity_minutes,
            committed_minutes=decided.committed_minutes,
            technicians_on_shift=decided.technicians_on_shift,
            open_orders=decided.open_orders,
            held=len(decided.held),
            summary=decided.summary,
        ),
        unplaced_machines=tuple(unplaced),
    )


# ─────────────────────────────────────────────────────────────
# Machine health (ADR-072, ADR-076, ADR-081)
# ─────────────────────────────────────────────────────────────

# What this reader could not ask, written where the person reading the numbers
# is looking. `HistoryContribution.pm_overdue` is an `int` with a default of 0,
# so a machine with no PM task reads as a machine with nothing overdue - which
# is a claim, drawn from an empty set, shown to somebody deciding what to look
# at (ADR-081 section 2).
#
# Since slice 16.1 the table exists and this reader passes what is in it. The
# two sentences below are what a zero can still mean: nothing registered at all,
# or nothing registered for that machine.
PM_STANDING_IS_ABSENT = (
    "งานบำรุงรักษาตามแผน: ยังไม่มีการลงทะเบียนงานบำรุงรักษาเลย จึงบอกไม่ได้ว่าเครื่องไหนเลยกำหนด"
)

PM_NOT_EVERY_MACHINE = (
    "งานบำรุงรักษาตามแผน: เครื่อง {machines} ยังไม่มีงานบำรุงรักษาลงทะเบียน "
    "เพราะคู่มือไม่ได้ระบุรอบไว้ เลขศูนย์ของเครื่องเหล่านี้จึงแปลว่ายังไม่มีใครกำหนด ไม่ใช่ไม่มีงานค้าง"
)


def _pm_absences(tasks: Sequence[PMTask], machines: Iterable[MachineId]) -> tuple[str, ...]:
    """Which sentence a zero needs, if it needs one.

    Nothing registered anywhere is a different statement from nothing
    registered here, and a screen that carried both would be telling a
    supervisor the same thing twice in two ways.
    """
    if not tasks:
        return (PM_STANDING_IS_ABSENT,)
    scheduled = {task.machine_id for task in tasks}
    without = sorted(str(machine) for machine in machines if machine not in scheduled)
    if not without:
        return ()
    return (PM_NOT_EVERY_MACHINE.format(machines=", ".join(without)),)


class HealthOverview(BaseModel):
    """Two orderings of the same readings, and no third number anywhere.

    There is deliberately no field here that blends the two, sorts one by the
    other, or reduces a machine to a percentage. ADR-072 section 2 is the record
    this response exists to obey, and a response model is where obeying it is
    visible: adding the blended figure means adding a field to this class, which
    means editing a file that says not to.

    The span is on the response as well as on every reading. A rate is only as
    good as the window behind it - one failure over a fortnight is "7 per 100
    days" and over a year is "0.3" - so nothing here serves a rate that a reader
    could meet without the span beside it (ADR-076 section 4, ADR-081 section 3).
    """

    model_config = _FROZEN

    at: datetime

    # The window every reading was counted over, repeated from the readings
    # because the panel names it once rather than per row.
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    observed_days: float = 0.0

    by_history: tuple[MachineHealth, ...]
    by_now: tuple[MachineHealth, ...]

    # What this reading cannot say, collected once rather than repeated on every
    # row. The domain writes one of these onto each reading and keeps it there,
    # because a reading handed to something that is not this screen has to
    # arrive with it; here the same sentence four times would be a caveat
    # nobody finishes reading (ADR-081 section 2).
    absent: tuple[str, ...] = ()

    # Machines the records mention and `plant.yaml` does not, reported for
    # ADR-048's reason: the machine did not stop existing because the file is
    # stale, and a reading that dropped it silently would hide the drift.
    unplaced_machines: tuple[str, ...] = ()


@router.get("/overview/health", response_model=HealthOverview)
def machine_health(
    conn: Db,
    clock: Time,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_machine_health"))],
) -> HealthOverview:
    """Which machines deserve attention, and why - for a person, not for a round.

    The advisor's answer to "where should I start" (ADR-072). Load, hand to
    `assess()`, sort with the two orderings, serialise: no arithmetic happens in
    this function, because the arithmetic is the thing somebody has to be able
    to check against records written out by hand (invariant 10, ADR-081 §5).

    **Four loads, and the fourth is the PM schedule.** Until slice 16.1 there was
    no `pm_task` table, `assess()` was handed nothing, and every `pm_overdue`
    came back zero from an empty set. It now reads the table; where a zero still
    means "nobody asked", `_pm_absences` says so in `absent` rather than letting
    the zero speak (ADR-081 §2, ADR-083 §6).
    """
    now = clock.now()
    known = {
        machine_id for station in plant.stations.values() for machine_id in station.machine_ids
    }
    repairs = [
        ClosedRepair.from_order(WorkOrderRef(ref), order, closed_at=closed_at)
        for ref, order, closed_at in work.closed_orders(conn)
    ]
    findings = list(triggers.live(conn).values())
    tasks = work.pm_tasks(conn)

    readings = assess(sorted(known), repairs=repairs, pm_tasks=tasks, findings=findings, now=now)

    # Every reading carries the same window, so the first is the answer for all
    # of them; an empty plant has none and the defaults stand.
    span = readings[0].history if readings else None

    mentioned = {repair.machine_id for repair in repairs} | {
        finding.machine_id for finding in findings
    }
    # dict.fromkeys rather than a set: the order these were written in is the
    # order they are read in, and a set would shuffle the caveats per request.
    written = dict.fromkeys(sentence for reading in readings for sentence in reading.history.absent)

    return HealthOverview(
        at=now,
        observed_from=span.observed_from if span is not None else None,
        observed_to=span.observed_to if span is not None else None,
        observed_days=span.observed_days if span is not None else 0.0,
        by_history=by_history(readings),
        by_now=by_now(readings),
        absent=(*written, *_pm_absences(tasks, sorted(known))),
        unplaced_machines=tuple(sorted(str(one) for one in mentioned - known)),
    )

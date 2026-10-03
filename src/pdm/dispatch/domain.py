"""The load gate and the 3C score, as one pure function (ADR-011, ADR-045).

Nothing here opens a connection, reads a clock or iterates a set. `dispatch()` is
a function of its arguments and only of its arguments, which is invariant 10 and
the precondition for two things that come later: the simulator running hundreds
of scenarios in CI (design.md 7), and Loop 6 replaying real scheduling decisions
against alternative weights. A single clock read inside here would make every
measurement in the report irreproducible, and would do it quietly.

Two mechanisms, deliberately not one (ADR-011):

  the **gate** decides how deep into the queue the system reaches, from one
  number a supervisor can be told - "this shift is at 92%, four non-urgent jobs
  are being held";
  the **score** decides the order within whatever the gate admitted.

Folded into a single objective function, the load term would have a weight nobody
could interpret and the sentence above could not be written.

**Every term is normalised to 0-1 before its weight applies** (ADR-045 §1), so
`priority_score` compares orders *within one round* and means nothing between
rounds. The two unbounded terms - downtime and waiting - are divided by the
largest in the round; the alternative is a constant nobody can source.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    FindingKind,
    Line,
    Severity,
    ShiftId,
    Station,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.contracts.wording import BAND as BAND_TH
from pdm.contracts.wording import SEVERITY as SEVERITY_TH
from pdm.contracts.wording import duration
from pdm.platform.config.loader import Config

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Statuses that mean this job is spoken for. They consume their assignees'
# capacity and count as committed work, and a round never touches them
# (ADR-045 §4).
#
# PROPOSED is on the list although nobody has agreed to it yet (ADR-071 §3). A
# proposal that did not consume capacity would make the shift read emptier than
# it is, and ADR-011's gate answers an empty-looking shift by releasing *more*
# work - so every unconfirmed proposal would be proposed again, to somebody who
# is already spoken for, until the supervisor's screen filled with duplicates of
# the same decision.
TAKEN = (
    WorkOrderStatus.PROPOSED,
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.HANDED_OVER,
)


class Queued(BaseModel):
    """One open order as the scheduler sees it.

    The reference and the creation time come with it rather than on the contract:
    both belong to the database (`Issued` keeps the reference separate for the
    same reason), and the waiting term needs the second one. A `WorkOrder` that
    carried either could be built without ever having been written down.
    """

    model_config = _FROZEN

    ref: str = Field(min_length=1)
    order: WorkOrder
    created_at: datetime

    # A shift lead has taken this one out of the gate's hands (ADR-011, ADR-059).
    # It arrives on the queue item because `dispatch()` may not read a table to
    # find out (invariant 10): the released set is part of the world the round is
    # handed, exactly like the roster and the orders themselves. The gate skips a
    # released order; nothing else about the round changes, and in particular it
    # is not scored differently - a supervisor released this job, they did not
    # rank it.
    released: bool = False

    # The shift lead said "not now" to this one, and why (ADR-120). Handed in on
    # the queue item for the same reason `released` is: `dispatch()` may not
    # read a table. A job set aside is not ranked, gated or crewed this round.
    set_aside: str | None = None

    @property
    def person_minutes(self) -> int:
        """What this job costs the shift (ADR-025, design.md 13.2).

        The multiplication is the whole reason the unit is person-minutes on both
        sides of `load_ratio`. Counting a two-person hour as sixty minutes makes
        every shift with one in it read emptier than it is, and the gate then
        releases more work than there are people for.
        """
        return self.order.estimated_minutes * self.order.required_technicians


class Band(StrEnum):
    """Which of ADR-011's three regimes this round is in, or neither.

    NO_CAPACITY is not a fourth load level. It is the answer when there is no
    shift covering this moment or nobody rostered on it, where a ratio cannot be
    computed at all - and treating that as zero load would release the whole
    queue to nobody.
    """

    LIGHT = "light"
    NORMAL = "normal"
    HEAVY = "heavy"
    NO_CAPACITY = "no_capacity"


class Terms(BaseModel):
    """Each term of the score, after normalisation and before its weight.

    Returned with every placement because opening a weighted sum costs nothing
    and ADR-005 wants the answer where the job is. (The expensive explanation -
    "delaying this adds twelve minutes of downtime" - is 3D's, and design.md 6.3
    defers that one until somebody asks.)
    """

    model_config = _FROZEN

    severity: float = 0.0
    downtime: float = 0.0
    skill_match: float = 0.0
    waiting: float = 0.0
    eta_urgency: float = 0.0
    # True where the layout could not price this machine at all (ADR-048). A
    # repair shorter than the buffer also scores zero, and the two mean opposite
    # things: one is a line that will not feel this, the other is a line we
    # cannot speak for. One number could not tell a supervisor which.
    downtime_is_unknown: bool = False


class RawFacts(BaseModel):
    """The two quantities behind the normalised terms, before the division.

    Carried alongside `Terms` because the sentence a technician reads quotes
    these and not those: ADR-045 §1 makes downtime and waiting a comparison
    within one round, and says the result must not be presented as a magnitude.
    Forty units of production is true whatever else is in the queue; 1.0 only
    means "the most in this round", which is not a sentence anybody can act on.
    """

    model_config = _FROZEN

    downtime_units: float = 0.0
    waited_minutes: float = 0.0


class Placement(BaseModel):
    """An order this round is releasing, and to whom."""

    model_config = _FROZEN

    ref: str
    assignees: tuple[Assignee, ...] = ()
    priority_score: float
    priority_reason: str = Field(min_length=1)
    terms: Terms
    facts: RawFacts = RawFacts()
    # Minutes from `now` until this job is meant to begin. `dispatch()` leaves it
    # None and means it: a ranked queue says who a job belongs to and nothing
    # about when it starts, and a zero there would be a promise the greedy
    # assignment never made. Only `schedule()` fills it in, because a solver that
    # places work over a horizon knows the answer (ADR-054).
    starts_in_minutes: int | None = None


class Withheld(BaseModel):
    """An order this round is not releasing, and why in a sentence."""

    model_config = _FROZEN

    ref: str
    why: str = Field(min_length=1)


class Round(BaseModel):
    """Everything one dispatch round decided, and the numbers behind it.

    Returned rather than written: this module decides and the caller persists,
    which is what keeps the decision replayable (invariant 10).
    """

    model_config = _FROZEN

    at: datetime
    shift_id: ShiftId | None = None
    on_date: date | None = None
    capacity_minutes: int = 0
    committed_minutes: int = 0
    # How many people the capacity above was summed over, and how many open
    # orders the round was handed - taken ones included, which is why this is not
    # `len(placed) + len(unassigned) + len(held)`.
    #
    # Counts, not decisions: nothing here changes what the round does. They are
    # on the round because the overview reports them beside the ratio, and the
    # alternative was a second roster query and a second pass over the same
    # orders - a copy of the gate's own arithmetic, which is the thing ADR-050
    # exists to prevent.
    technicians_on_shift: int = 0
    open_orders: int = 0
    # None when there is no capacity to divide by - not zero, which would read as
    # an empty shift with people on it.
    load_ratio: float | None = None
    band: Band
    placed: tuple[Placement, ...] = ()
    # Admitted by the gate and nobody free to take it. Reported rather than
    # silently held: "nobody with electrical has time left this shift" is a fact
    # a supervisor can act on, and a ticket that simply did not appear is not.
    unassigned: tuple[Withheld, ...] = ()
    held: tuple[Withheld, ...] = ()
    # What the shift lead put aside themselves, with their reason (ADR-120).
    # Separate from `held`: that is the gate's decision and can be released,
    # this is a person's and can be brought back.
    set_aside: tuple[Withheld, ...] = ()
    summary: str = ""


def load_ratio(committed_minutes: int, capacity_minutes: int) -> float | None:
    """Person-minutes of committed work over person-minutes available.

    None where there is no capacity. Both sides are person-minutes and neither is
    wall-clock time; if one side counted differently the gate would be wrong on
    every shift containing a two-person job, and nothing would report it
    (design.md 13.2).
    """
    if capacity_minutes <= 0:
        return None
    return committed_minutes / capacity_minutes


def committed(queue: Iterable[Queued]) -> int:
    """The work this shift has taken on: everything open except unreleased PM.

    **Queued scheduled work is the reserve, not demand** (ADR-045 §2). Counting
    it here makes a shift with a maintenance backlog read busy, and the gate then
    holds back the condition work that actually has to happen - exactly backwards,
    and invisible, because the numbers all move; they just move the wrong way.
    """
    return sum(
        item.person_minutes
        for item in queue
        if not (
            item.order.origin is WorkOrderOrigin.SCHEDULED
            and item.order.status is WorkOrderStatus.QUEUED
        )
    )


def waiting(queue: Iterable[Queued]) -> list[Queued]:
    """The orders a round may rank: queued, and not set aside by the shift lead.

    A set-aside order stays in `committed` - the work has not gone away - and is
    left out of the ranking, so its absence does not move anybody else's
    normalised terms in a way the lead did not ask for beyond that (ADR-120).
    """
    return [
        item
        for item in queue
        if item.order.status is WorkOrderStatus.QUEUED and item.set_aside is None
    ]


def _set_aside(queue: Iterable[Queued]) -> tuple[Withheld, ...]:
    return tuple(
        Withheld(ref=item.ref, why=item.set_aside)
        for item in queue
        if item.order.status is WorkOrderStatus.QUEUED and item.set_aside
    )


def _band(ratio: float | None, config: Config) -> Band:
    if ratio is None:
        return Band.NO_CAPACITY
    load = config.policy.load
    if ratio >= load.heavy_at_or_above:
        return Band.HEAVY
    if ratio < load.light_below:
        return Band.LIGHT
    return Band.NORMAL


def downtime_units(order: WorkOrder, station: Station, line: Line) -> float:
    """Production lost if this machine stays down for the length of the repair.

    ADR-021, and the term that makes this a scheduler for a vehicle assembly line
    rather than for a generic factory: stations are in series, so one machine
    stopping stops the line - but a station with twenty units queued ahead of it
    buys the technician twenty minutes, and a bottleneck with no buffer buys
    nothing. Weighted equally, the system orders work in a way a technician can
    see is wrong immediately.
    """
    unbuffered = max(0.0, order.estimated_minutes - station.buffer_minutes(line))
    units_per_minute = 60.0 / line.takt_seconds
    return unbuffered * units_per_minute * station.bottleneck_multiplier


def downtime_or_unknown(order: WorkOrder, config: Config) -> float | None:
    """Production lost, or None where the layout cannot say (ADR-048).

    A work order carries the machine it was created against and outlives the
    layout it was created under: ADR-027 keeps `plant.yaml` free to change when
    the line is rearranged, precisely so old records keep meaning what they
    meant. An order for a machine since moved or decommissioned is therefore
    ordinary, not corrupt - and until this returned None it raised `KeyError`
    here and the whole round returned nothing, so one stale order left every
    machine still on the line unscheduled.
    """
    try:
        station = config.station_of(order.machine_id)
        line = config.line_of(order.machine_id)
    except KeyError:
        return None
    return downtime_units(order, station, line)


def _skill_match(order: WorkOrder, available: Sequence[Technician]) -> float:
    """1 where somebody on this shift holds the skill, 0.5 where none is named.

    Rostered and active, **not** free (ADR-049 §1). ADR-045 §1's table says
    "free" and means this: whether anybody has minutes left is answered by
    `_assign`, and answering it here as well would count one fact twice and
    re-rank the queue every time somebody finished a job - under a technician
    already walking to a machine, which design.md 6.2 refuses.

    The middle value is for the orders ADR-041 deliberately leaves without a
    skill: a job priced from `fallback_minutes` names none, because guessing one
    sends the wrong person. They must not score as unmatchable - that would push
    exactly the long-tail work ADR-011 wants released on a quiet shift to the
    bottom of every queue - and they must not score as a perfect match either.
    """
    if order.required_skill is None:
        return 0.5
    return 1.0 if any(person.can_perform(order.required_skill) for person in available) else 0.0


def _eta_urgency(order: WorkOrder, now: datetime, horizon_hours: int) -> float:
    """How close a prediction's crossing is, on the horizon's own scale.

    Only predictions (`policy.yaml` says so, and the weight is named for it).
    A detection scores zero here and loses nothing by it: what makes it urgent is
    already in severity and downtime, and a term named "ETA urgency" that gave
    the maximum to work with no ETA would be counting the same fact twice.
    """
    if order.finding_kind is not FindingKind.PREDICTED or order.eta is None:
        return 0.0
    hours_away = (order.eta - now).total_seconds() / 3600.0
    if hours_away <= 0:
        return 1.0
    return max(0.0, 1.0 - hours_away / horizon_hours)


def _reason(
    terms: Terms,
    order: WorkOrder,
    config: Config,
    *,
    downtime: float,
    waited: float,
    now: datetime,
) -> str:
    """Why this job is ranked where it is, in a technician's words (ADR-005).

    Built from the terms that actually moved it - the two or three largest
    contributions - because a sentence listing five terms including three near
    zero reads as a formula rather than as a reason, and the point is to be
    believed by somebody who knows the machine better than the system does.

    **The quantities are the raw ones, never the normalised terms.** ADR-045 §1
    divides downtime and waiting by the largest in the round, which makes them a
    comparison and not a magnitude, and says in as many words that the result
    must not be presented as one. A ticket reading "downtime 1.0" would be
    printing exactly the number that record forbids. Forty units of production
    and three hours of waiting are facts about the plant, true whatever else is
    in the queue, and they are what somebody standing at the machine can check.

    No model writes any of this. Every clause is assembled from a number the
    system computed (ADR-003).
    """
    weights = config.policy.weights
    wording = config.wording()
    contributions = [
        (
            weights.severity * terms.severity,
            f"ความรุนแรงระดับ{SEVERITY_TH[order.severity.value]}",
        ),
        (
            # Zero for scheduled work, whose waiting stops nothing (ADR-127).
            weights.downtime * terms.downtime,
            f"ถ้างานนี้รอ สายการผลิตจะเสียราว {downtime:,.0f} คัน",
        ),
        (
            weights.skill_match * terms.skill_match,
            f"กะนี้มี{wording.skill(order.required_skill)}ที่รับงานนี้ได้"
            if order.required_skill is not None
            else "งานนี้ไม่ต้องใช้ทักษะเฉพาะ ใครว่างก็รับได้",
        ),
        # A job that has waited under a minute has nothing to say about waiting,
        # whatever its normalised term came to against an equally fresh round.
        # Neither of these two prints a time (ADR-126). The sentence is frozen
        # when the round proposes the job and read for up to half an hour after;
        # "in about 41 minutes" beside a live "14:56" that had already passed
        # was the third trial's first blocker. The live forecast is the card's
        # own `eta_text`; how long a job has waited is the card's to compute.
        (weights.waiting * terms.waiting if waited >= 1 else 0.0, "รอในคิวนานกว่างานอื่น"),
        (weights.eta_urgency * terms.eta_urgency, "พยากรณ์ว่าใกล้ถึงเกณฑ์"),
    ]
    # 0.05 is presentational and its provenance is ADR-049 §2: it decides which
    # clauses appear in this sentence and nothing else. Every term is already in
    # the weighted sum, which was computed before this function was called, so
    # no threshold here can move a score, an ordering or an assignment.
    strongest = [text for value, text in sorted(contributions, key=lambda c: -c[0]) if value > 0.05]
    sentence = " · ".join(strongest[:3]) if strongest else "งานนี้ไม่เร่งด่วน ได้คิวเพราะกะนี้ยังมีกำลังคนเหลือ"
    if order.origin is WorkOrderOrigin.SCHEDULED and downtime > 0:
        # Not a reason for the rank - it did not move it (ADR-127) - but what
        # doing the job costs the line is what a shift lead weighs before
        # releasing it, so it is stated as a fact (ADR-104).
        sentence += f" · งานนี้ต้องหยุดเครื่อง ถ้าทำระหว่างเดินสาย การผลิตจะหายราว {downtime:,.0f} คัน"
    if terms.downtime_is_unknown:
        # ADR-005 wants the caveat where the job is, not in a log. A technician
        # reading this knows the ranking did not count the line stopping,
        # because nothing here could work out whether it would.
        sentence += (
            f" · เครื่อง {order.machine_id} ไม่อยู่ในผังสายการผลิตปัจจุบัน จึงไม่ได้นับความเสียหายจากการที่เครื่องหยุด"
        )
    return sentence


def _span(minutes: float) -> str:
    """A duration a technician reads at a glance, not an ISO interval.

    Rounded on purpose: "3 ชม. 20 นาที" is a fact somebody can check against the
    clock on the wall, and "3:19:47" claims a precision the estimate behind it
    does not have.
    """
    return duration(minutes)


def _normalised(values: Sequence[float]) -> list[float]:
    """Divide by the largest, or leave a list of zeros alone.

    Within the round and nowhere else (ADR-045 §1). A fixed divisor would be a
    number with no source, and one for waiting time would have to encode how long
    a job may wait - which is what the weight is for.
    """
    top = max(values, default=0.0)
    if top <= 0:
        return [0.0 for _ in values]
    return [value / top for value in values]


def capacity_left(
    technicians: Sequence[Technician],
    minutes: dict[UserId, int],
    queue: Sequence[Queued],
) -> dict[UserId, int]:
    """Minutes each person has left after the work already on them.

    Work in progress is not re-planned (ADR-045 §4), but it is not free either:
    a technician halfway through a ninety-minute job has ninety fewer minutes to
    give, and a round that ignored that would hand them a full shift of new work.
    """
    left = {person.user: minutes.get(person.user, 0) for person in technicians}
    for item in queue:
        if item.order.status not in TAKEN:
            continue
        for assignee in item.order.assignees:
            if assignee.user in left:
                left[assignee.user] -= item.order.estimated_minutes
    return left


def _no_capacity_cause(shift_id: ShiftId | None, assignments: Sequence[tuple[UserId, int]]) -> str:
    """Which of the ways of having no capacity this round hit (ADR-045 §3).

    "Nobody is rostered" and "there is no shift at this hour" are fixed by
    different people: the first is a supervisor filling a roster, the second is
    a plant that does not run at this hour and a tick that should not have asked.
    A round that says the first when it means the second sends somebody looking
    for a roster that was never missing.

    `shift_id` is None exactly when no shift covers `now` - it is `shift_at`
    returning None, passed through by the caller.
    """
    if shift_id is None:
        return "ตอนนี้ไม่มีกะทำงาน"
    # "This shift", not its id: `afternoon` is plant.yaml's word, the round is
    # always about the shift running now, and the screens printed the id as it
    # was (2026-09-30, ADR-093).
    if not assignments:
        return "ยังไม่มีช่างลงชื่อในกะนี้"
    # Rostered, but every one of them is already spent. Saying "nobody is
    # rostered" here would be false about people who are standing on the line.
    return "ช่างทุกคนในกะนี้มีงานเต็มเวลาแล้ว"


def dispatch(
    queue: Sequence[Queued],
    *,
    technicians: Sequence[Technician],
    assignments: Sequence[tuple[UserId, int]],
    config: Config,
    now: datetime,
    shift_id: ShiftId | None = None,
    on_date: date | None = None,
) -> Round:
    """One scheduling round: gate, score, assign, explain.

    `assignments` is (technician, available_minutes) for this shift, already
    resolved by the caller - the roster is a table and this function may not read
    one (invariant 10). `on_date` is carried through for the record only.

    `shift_id` is None when **no shift covers `now`** - what `shift_at` returns
    at an hour the plant does not run. It is not "the caller did not bother":
    a round with no capacity says which way it was, and this is the only thing
    separating an hour with no shift from a shift with nobody on it.

    Same arguments, same answer, every time. Every sort names its tie-break and
    no set iteration reaches an output.
    """
    capacity = sum(minutes for _, minutes in assignments)
    committed_minutes = committed(queue)
    ratio = load_ratio(committed_minutes, capacity)
    band = _band(ratio, config)

    rostered = {user for user, _ in assignments}
    available = sorted(
        (person for person in technicians if person.active and person.user in rostered),
        key=lambda person: person.user,
    )

    placeable = waiting(queue)
    ranked = _rank(placeable, available=available, config=config, now=now)

    if band is Band.NO_CAPACITY:
        cause = _no_capacity_cause(shift_id, assignments)
        return Round(
            at=now,
            shift_id=shift_id,
            on_date=on_date,
            capacity_minutes=capacity,
            committed_minutes=committed_minutes,
            technicians_on_shift=len(assignments),
            open_orders=len(queue),
            load_ratio=None,
            band=band,
            held=tuple(
                Withheld(
                    ref=item.ref,
                    why=f"{cause} จึงยังจัดงานให้ใครไม่ได้",
                )
                for item, _, _, _ in ranked
            ),
            set_aside=_set_aside(queue),
            summary=f"{cause} · มีงานรออยู่ {len(ranked)} ใบ",
        )

    assert ratio is not None
    admitted, held = _admit(ranked, band=band, ratio=ratio, capacity=capacity, config=config)
    placed, unassigned = _assign(
        admitted,
        available=available,
        assignments=assignments,
        queue=queue,
        config=config,
        now=now,
    )

    return Round(
        at=now,
        shift_id=shift_id,
        on_date=on_date,
        capacity_minutes=capacity,
        committed_minutes=committed_minutes,
        technicians_on_shift=len(assignments),
        open_orders=len(queue),
        load_ratio=ratio,
        band=band,
        placed=tuple(placed),
        unassigned=tuple(unassigned),
        held=tuple(held),
        set_aside=_set_aside(queue),
        summary=_summary(
            band,
            ratio,
            placed,
            unassigned,
            held,
            unpriced=sum(1 for _, _, terms, _ in ranked if terms.downtime_is_unknown),
        ),
    )


_Ranked = tuple[Queued, float, Terms, RawFacts]


def ranking(
    queue: Sequence[Queued],
    *,
    technicians: Sequence[Technician],
    assignments: Sequence[tuple[UserId, int]],
    config: Config,
    now: datetime,
) -> dict[str, _Ranked]:
    """The score, the five terms and the raw facts, per queued order.

    `dispatch()` computes these on its way to a decision and a `Round` carries
    only the ones it placed - an order the gate admitted and greedy could not
    crew comes back as a `Withheld`, which is a reference and a sentence.

    3D places some of exactly those, and their tickets have to carry the same
    explanation as everybody else's (ADR-005). Rather than let the solver
    approximate it, or widen `Withheld` for one caller, the ranking is offered
    here as what it already was: a function of the round's arguments.

    Ranking twice costs a sort over the queue and is worth it. The alternative
    is two implementations of the score, and the second one is wrong the first
    time a weight changes.
    """
    rostered = {user for user, _ in assignments}
    available = sorted(
        (person for person in technicians if person.active and person.user in rostered),
        key=lambda person: person.user,
    )
    placeable = waiting(queue)
    return {
        item.ref: entry
        for entry in _rank(placeable, available=available, config=config, now=now)
        for item in (entry[0],)
    }


def _rank(
    placeable: Sequence[Queued],
    *,
    available: Sequence[Technician],
    config: Config,
    now: datetime,
) -> list[_Ranked]:
    """Score every queued order and sort, highest first.

    The two unbounded terms are normalised across exactly this list, which is
    what makes the score a within-round comparison (ADR-045 §1).
    """
    weights = config.policy.weights
    horizon = config.policy.triggers.trend.max_horizon_hours

    raw_downtime: list[float] = []
    delay_cost: list[float] = []
    raw_waiting: list[float] = []
    unpriced: list[bool] = []
    for item in placeable:
        cost = downtime_or_unknown(item.order, config)
        unpriced.append(cost is None)
        # Zero rather than absent: the normalisation below divides by the largest
        # in this list, so leaving an order out would move every other order's
        # term (ADR-045 §1, ADR-048).
        raw_downtime.append(0.0 if cost is None else cost)
        # What delaying the job costs, which is what the term ranks on. A
        # scheduled job's machine is running while it waits, so delaying it
        # costs nothing; its downtime figure is what *doing* it costs, and
        # ranking on that put the PM that stops the line longest first (ADR-127).
        scheduled = item.order.origin is WorkOrderOrigin.SCHEDULED
        delay_cost.append(0.0 if scheduled else raw_downtime[-1])
        raw_waiting.append(max(0.0, (now - item.created_at).total_seconds() / 60.0))

    downtime = _normalised(delay_cost)
    waiting = _normalised(raw_waiting)

    scored: list[_Ranked] = []
    for index, item in enumerate(placeable):
        terms = Terms(
            severity=item.order.severity.rank / Severity.CRITICAL.rank,
            downtime=downtime[index],
            skill_match=_skill_match(item.order, available),
            waiting=waiting[index],
            eta_urgency=_eta_urgency(item.order, now, horizon),
            downtime_is_unknown=unpriced[index],
        )
        score = (
            weights.severity * terms.severity
            + weights.downtime * terms.downtime
            + weights.skill_match * terms.skill_match
            + weights.waiting * terms.waiting
            + weights.eta_urgency * terms.eta_urgency
        )
        scored.append(
            (
                item,
                score,
                terms,
                RawFacts(downtime_units=raw_downtime[index], waited_minutes=raw_waiting[index]),
            )
        )

    # Tie-break by age then reference. Two orders with identical scores are
    # common - two low-severity PM jobs on the same station - and leaving their
    # order to the sort's input would make the round unreplayable (invariant 10).
    scored.sort(key=lambda entry: (-entry[1], entry[0].created_at, entry[0].ref))
    return scored


def _admit(
    ranked: Sequence[_Ranked],
    *,
    band: Band,
    ratio: float,
    capacity: int,
    config: Config,
) -> tuple[list[_Ranked], list[Withheld]]:
    """How deep into the ranked queue this round reaches (ADR-011).

    Heavy: high severity only. Normal: condition and manual work. Light: the
    same, then PM work released in score order while the ratio stays within the
    light boundary with each job added (ADR-109) - not all of it, because a
    quiet shift handed its whole maintenance backlog is a heavy shift one round
    later, and the work released last is the
    work most likely to be abandoned at handover.

    An order a shift lead has released passes all of that (ADR-059), and it is
    priced into the shift **before** the round decides how much more maintenance
    to pull forward - see `_released_demand`. It still has to be crewed:
    releasing work does not conjure a technician, and an order nobody can take
    comes back unassigned with the same sentence as everybody else's.
    """
    load = config.policy.load
    admitted: list[_Ranked] = []
    held: list[Withheld] = []
    running = ratio + _released_demand(ranked, capacity=capacity)

    for entry in ranked:
        item, _, _, _ = entry
        order = item.order
        scheduled = order.origin is WorkOrderOrigin.SCHEDULED

        if item.released:
            # A supervisor has answered the question the gate was going to ask,
            # in writing (ADR-011's sentence runs in both directions). Its
            # minutes are already in `running`.
            admitted.append(entry)
            continue

        if band is Band.HEAVY and order.severity.rank < Severity.HIGH.rank:
            held.append(
                Withheld(
                    ref=item.ref,
                    why=(
                        f"กะนี้ใช้กำลังคนไป {ratio:.0%} แล้ว และงานนี้ความรุนแรง"
                        f"{SEVERITY_TH[order.severity.value]} · เมื่อภาระถึง "
                        f"{load.heavy_at_or_above:.0%} ระบบปล่อยเฉพาะงานความรุนแรงสูงและวิกฤต"
                    ),
                )
            )
            continue

        if scheduled:
            if band is not Band.LIGHT:
                held.append(
                    Withheld(
                        ref=item.ref,
                        why=(
                            f"งานบำรุงรักษาตามแผนรอกะที่งานเบา · กะนี้ใช้กำลังคนไป {ratio:.0%} "
                            f"ต้องต่ำกว่า {load.light_below:.0%} จึงจะปล่อย"
                        ),
                    )
                )
                continue
            # A job is released only if the shift stays within the ceiling with
            # it (ADR-109). Checked before adding, a 90-minute job on a shift at
            # 0% took it to 90% - from quiet to heavy in one round. A smaller job
            # further down the list may still fit, so the loop goes on.
            after = running + item.person_minutes / capacity
            if after > load.light_below:
                held.append(
                    Withheld(
                        ref=item.ref,
                        why=(
                            f"ถ้าปล่อยงานนี้ ภาระของกะจะเป็น {after:.0%} "
                            f"เกินเพดานของงานบำรุงรักษาตามแผน ({load.light_below:.0%})"
                        ),
                    )
                )
                continue
            # Releasing PM work is what makes it demand (ADR-045 §2), so the
            # ratio moves as the round decides - which is what makes this
            # terminate rather than release the whole backlog at once.
            running = after

        admitted.append(entry)

    return (admitted, held)


def _released_demand(ranked: Sequence[_Ranked], *, capacity: int) -> float:
    """What the hand-released maintenance work costs the shift, as a ratio.

    Counted once, up front, and only for scheduled work. Two decisions are in
    that sentence (ADR-059).

    **Only scheduled.** Queued PM work is the reserve rather than demand
    (ADR-045 §2), so it is not in `load_ratio` yet and releasing it is what makes
    it demand. Condition and manual work is already counted there, and adding it
    again would spend the same hour twice - the shift would top up one PM job
    fewer than it has room for, every round, with every number still adding up.

    **Up front**, rather than as the loop reaches each one, so that a release
    changes *which* maintenance the shift does and not *how much*. Added in rank
    order instead, a release would displace the automatic top-up when it happened
    to rank high and pile on top of it when it happened to rank low, and the
    boundary a supervisor is being shown would mean two different things
    depending on how old their ticket was.
    """
    return sum(
        item.person_minutes / capacity
        for item, _, _, _ in ranked
        if item.released and item.order.origin is WorkOrderOrigin.SCHEDULED
    )


def put_down_by(order: WorkOrder) -> frozenset[UserId]:
    """Who put this job down, if it is back in the queue after a handover.

    A round does not offer it straight back to them (ADR-126). In the third
    trial a technician handed a job over - "the belt is the wrong size, waiting
    for the part" - and the next round proposed it to the same technician.
    They put it down for a reason the round cannot read; the shift lead can
    still send it to them by hand.
    """
    if order.handover_note is None or order.assignees:
        return frozenset()
    return frozenset(segment.user for segment in order.work_segments)


def _assign(
    admitted: Sequence[_Ranked],
    *,
    available: Sequence[Technician],
    assignments: Sequence[tuple[UserId, int]],
    queue: Sequence[Queued],
    config: Config,
    now: datetime,
) -> tuple[list[Placement], list[Withheld]]:
    """Greedy down the ranked list: the best-matched free people, or nobody.

    A `required_technicians` job takes that many or none at all. Half of a
    two-person job cannot be started, and assigning half of it spends one
    person's shift to achieve nothing (ADR-025).
    """
    left = capacity_left(available, dict(assignments), queue)
    placed: list[Placement] = []
    unassigned: list[Withheld] = []

    for item, score, terms, facts in admitted:
        order = item.order
        candidates = [
            person
            for person in available
            if (order.required_skill is None or person.can_perform(order.required_skill))
            and left[person.user] >= order.estimated_minutes
            and person.user not in put_down_by(order)
        ]
        # Most free capacity first, so a shift's work spreads rather than filling
        # one person; user id breaks the tie, because two people with the same
        # free minutes must not be ordered by whichever the roster listed first.
        candidates.sort(key=lambda person: (-left[person.user], person.user))

        if len(candidates) < order.required_technicians:
            wanted = (
                config.wording().skill(order.required_skill)
                if order.required_skill is not None
                else "ช่างทักษะใดก็ได้"
            )
            unassigned.append(
                Withheld(
                    ref=item.ref,
                    why=(
                        f"ต้องการ{wanted} {order.required_technicians} คน ที่มีเวลาว่าง "
                        f"{order.estimated_minutes} นาที · ตอนนี้มีว่าง {len(candidates)} คน"
                    ),
                )
            )
            continue

        chosen = candidates[: order.required_technicians]
        for person in chosen:
            left[person.user] -= order.estimated_minutes
        placed.append(
            Placement(
                ref=item.ref,
                assignees=tuple(
                    Assignee(
                        user=person.user,
                        role=AssigneeRole.PRIMARY if index == 0 else AssigneeRole.HELPER,
                    )
                    for index, person in enumerate(chosen)
                ),
                priority_score=score,
                priority_reason=_reason(
                    terms,
                    order,
                    config,
                    downtime=facts.downtime_units,
                    waited=facts.waited_minutes,
                    now=now,
                ),
                facts=facts,
                terms=terms,
            )
        )

    return (placed, unassigned)


def _summary(
    band: Band,
    ratio: float,
    placed: Sequence[Placement],
    unassigned: Sequence[Withheld],
    held: Sequence[Withheld],
    unpriced: int,
) -> str:
    """The sentence ADR-011 kept the gate separate in order to be able to write.

    A supervisor reads this one line and knows both what the system did and what
    it is sitting on. Folded into the score, this could not be said at all.
    """
    parts = [
        f"กะนี้ใช้กำลังคนไป {ratio:.0%} ({BAND_TH[band.value]})",
        # What the next round would propose, said as that: "ปล่อยงาน 0 ใบ" beside
        # four cards waiting read as a count of something already done (ADR-126).
        f"รอบถัดไปจะเสนองานเพิ่ม {len(placed)} ใบ" if placed else "ไม่มีงานใหม่ที่จะเสนอ",
    ]
    if held:
        parts.append(f"กันไว้ก่อน {len(held)} ใบ")
    if unassigned:
        parts.append(f"{len(unassigned)} ใบรอช่างว่าง")
    if unpriced:
        # The half of ADR-048 that keeps a stale layout loud. The work flowed;
        # the file still needs somebody to look at it, and this says so every
        # round until they do.
        parts.append(f"{unpriced} ใบระบุเครื่องที่ไม่มีในผังสายการผลิต")
    return " · ".join(parts)

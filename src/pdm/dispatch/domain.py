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
from pdm.platform.config.loader import Config

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Statuses that mean somebody has this job. They consume their assignees'
# capacity and count as committed work, and a round never touches them
# (ADR-045 §4).
TAKEN = (
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


def _downtime_or_unknown(order: WorkOrder, config: Config) -> float | None:
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
    contributions = [
        (weights.severity * terms.severity, f"severity is {order.severity.value}"),
        (
            weights.downtime * terms.downtime,
            f"the line loses about {downtime:.0f} unit(s) while this waits",
        ),
        (
            weights.skill_match * terms.skill_match,
            f"somebody on this shift holds {order.required_skill}"
            if order.required_skill is not None
            else "this job names no skill, so anybody free can take it",
        ),
        (weights.waiting * terms.waiting, f"it has been waiting {_span(waited)}"),
        (
            weights.eta_urgency * terms.eta_urgency,
            f"the predicted crossing is about {_span((order.eta - now).total_seconds() / 60.0)} "
            f"away"
            if order.eta is not None
            else "the predicted crossing is close",
        ),
    ]
    # 0.05 is presentational and its provenance is ADR-049 §2: it decides which
    # clauses appear in this sentence and nothing else. Every term is already in
    # the weighted sum, which was computed before this function was called, so
    # no threshold here can move a score, an ordering or an assignment.
    strongest = [text for value, text in sorted(contributions, key=lambda c: -c[0]) if value > 0.05]
    sentence = (
        "; ".join(strongest[:3])
        if strongest
        else "nothing about this job is urgent; it is here because the shift has room"
    )
    if terms.downtime_is_unknown:
        # ADR-005 wants the caveat where the job is, not in a log. A technician
        # reading this knows the ranking did not count the line stopping,
        # because nothing here could work out whether it would.
        sentence += (
            f"; {order.machine_id} is not in the current line layout, so the cost of "
            "leaving it down was not counted"
        )
    return sentence


def _span(minutes: float) -> str:
    """A duration a technician reads at a glance, not an ISO interval.

    Rounded on purpose: "3h 20m" is a fact somebody can check against the clock
    on the wall, and "3:19:47" claims a precision the estimate behind it does
    not have.
    """
    total = max(0, int(minutes))
    hours, rest = divmod(total, 60)
    if hours and rest:
        return f"{hours}h {rest}m"
    if hours:
        return f"{hours}h"
    return f"{rest}m"


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


def _capacity_left(
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
        return "no shift covers this moment"
    if not assignments:
        return f"nobody is rostered on the {shift_id} shift"
    # Rostered, but every one of them is already spent. Saying "nobody is
    # rostered" here would be false about people who are standing on the line.
    return f"everybody on the {shift_id} shift has no minutes left to give"


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

    placeable = [item for item in queue if item.order.status is WorkOrderStatus.QUEUED]
    ranked = _rank(placeable, available=available, config=config, now=now)

    if band is Band.NO_CAPACITY:
        cause = _no_capacity_cause(shift_id, assignments)
        return Round(
            at=now,
            shift_id=shift_id,
            on_date=on_date,
            capacity_minutes=capacity,
            committed_minutes=committed_minutes,
            load_ratio=None,
            band=band,
            held=tuple(
                Withheld(
                    ref=item.ref,
                    why=f"{cause}, so there is no capacity to schedule against",
                )
                for item, _, _, _ in ranked
            ),
            summary=f"no capacity: {cause}; {len(ranked)} order(s) are waiting",
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
        load_ratio=ratio,
        band=band,
        placed=tuple(placed),
        unassigned=tuple(unassigned),
        held=tuple(held),
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
    raw_waiting: list[float] = []
    unpriced: list[bool] = []
    for item in placeable:
        cost = _downtime_or_unknown(item.order, config)
        unpriced.append(cost is None)
        # Zero rather than absent: the normalisation below divides by the largest
        # in this list, so leaving an order out would move every other order's
        # term (ADR-045 §1, ADR-048).
        raw_downtime.append(0.0 if cost is None else cost)
        raw_waiting.append(max(0.0, (now - item.created_at).total_seconds() / 60.0))

    downtime = _normalised(raw_downtime)
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
    same, then PM work released in score order until the ratio reaches the light
    boundary - not all of it, because a quiet shift handed its whole maintenance
    backlog is a heavy shift one round later, and the work released last is the
    work most likely to be abandoned at handover.
    """
    load = config.policy.load
    admitted: list[_Ranked] = []
    held: list[Withheld] = []
    running = ratio

    for entry in ranked:
        item, _, _, _ = entry
        order = item.order
        scheduled = order.origin is WorkOrderOrigin.SCHEDULED

        if band is Band.HEAVY and order.severity.rank < Severity.HIGH.rank:
            held.append(
                Withheld(
                    ref=item.ref,
                    why=(
                        f"the shift is at {ratio:.0%} and this is {order.severity.value} "
                        f"severity; at or above {load.heavy_at_or_above:.0%} only high and "
                        "critical work is released"
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
                            f"scheduled maintenance waits for a quiet shift; this one is at "
                            f"{ratio:.0%} and the boundary is {load.light_below:.0%}"
                        ),
                    )
                )
                continue
            if running >= load.light_below:
                held.append(
                    Withheld(
                        ref=item.ref,
                        why=(
                            f"releasing this would take the shift past {load.light_below:.0%}, "
                            f"which is as far as maintenance work is pulled forward"
                        ),
                    )
                )
                continue
            # Releasing PM work is what makes it demand (ADR-045 §2), so the
            # ratio moves as the round decides - which is what makes this
            # terminate rather than release the whole backlog at once.
            running += item.person_minutes / capacity

        admitted.append(entry)

    return (admitted, held)


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
    left = _capacity_left(available, dict(assignments), queue)
    placed: list[Placement] = []
    unassigned: list[Withheld] = []

    for item, score, terms, facts in admitted:
        order = item.order
        candidates = [
            person
            for person in available
            if (order.required_skill is None or person.can_perform(order.required_skill))
            and left[person.user] >= order.estimated_minutes
        ]
        # Most free capacity first, so a shift's work spreads rather than filling
        # one person; user id breaks the tie, because two people with the same
        # free minutes must not be ordered by whichever the roster listed first.
        candidates.sort(key=lambda person: (-left[person.user], person.user))

        if len(candidates) < order.required_technicians:
            wanted = order.required_skill or "any skill"
            unassigned.append(
                Withheld(
                    ref=item.ref,
                    why=(
                        f"needs {order.required_technicians} technician(s) with {wanted} and "
                        f"{order.estimated_minutes} free minutes; {len(candidates)} available"
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
    parts = [f"the shift is at {ratio:.0%} ({band.value} load)", f"{len(placed)} order(s) released"]
    if held:
        parts.append(f"{len(held)} held back")
    if unassigned:
        parts.append(f"{len(unassigned)} admitted with nobody free to take it")
    if unpriced:
        # The half of ADR-048 that keeps a stale layout loud. The work flowed;
        # the file still needs somebody to look at it, and this says so every
        # round until they do.
        parts.append(f"{unpriced} order(s) name a machine the layout does not describe")
    return ", ".join(parts)

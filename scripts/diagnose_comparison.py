"""Why the comparison came out the way it did, measured rather than argued.

`compare_policies.py` produced a result the design did not predict: 3C reaches a
machine in about half the time 3A takes, and 3A still loses slightly less
production. `docs/results/README.md` offered two explanations for that and chose
neither, which was the honest thing to write at the time and is not a place to
leave a report. This script asks the questions that separate them.

Issue #27 put tuning out of scope and said in as many words that a weight which
turns out to be wrong is **a finding to report, not something to quietly fix**.
Nothing here changes a weight in `config/policy.yaml`. Every sweep below builds
a throwaway `Config` in memory, reports what it saw, and drops it.

Four questions, in the order they have to be asked - each one is only worth
asking if the one before it came back clean:

1. **Is the comparison measuring its own adapter?** `GateAndScore._starting_now`
   keeps one placement per technician per round and drops the rest. If those
   drops are work somebody free could have started, 3C is being handicapped by
   the harness rather than by its policy, and nothing else here means anything.
2. **Is the gate what costs 3C the production?** The load gate is the part of
   ADR-011 a reader is most likely to suspect, because holding work back is the
   one thing 3C does that neither baseline does.
3. **If not the gate, which term of the score?** The five weights are the only
   other thing that separates 3C from 3B.
4. **Is ADR-021's downtime term doing anything at all?** That record is the
   argument that this is a scheduler for a vehicle assembly line rather than a
   generic one. If its term does not move the outcome, the report has to say so.

Usage:

    uv run python -m scripts.diagnose_comparison            # writes docs/results/
    uv run python -m scripts.diagnose_comparison --seeds 4  # a quicker pass

Run as a module, not as a path: it imports `compare_policies` so that the
adapter under test is the committed one rather than a copy that could drift
away from it.
"""

from __future__ import annotations

import argparse
import statistics
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pdm.dispatch.domain as dispatch_domain
from pdm.baselines import FirstComeFirstServed, PriorityMatrix
from pdm.contracts import MachineId, ShiftAssignment, Technician, UserId, WorkOrder
from pdm.dispatch import Queued, Withheld, dispatch
from pdm.platform.config import Config, load_config
from pdm.sim import Placement, RoundState, SimScenario, run
from pdm.sim.scenarios import LINE_A_ONE_SHIFT
from scripts.compare_policies import REPO, RESULTS, GateAndScore, with_uniform_buffers

# Question 4 is the only one that leaves the shipped layout, because "does the
# downtime term do anything" cannot be answered at one buffer setting - that is
# the same argument ADR-021 made for having a sweep at all. Everything else in
# this file is the cell the committed table's headline row is drawn from: the
# shipped layout at the shipped arrival rate, so the diagnosis and the result it
# is diagnosing are the same shift.
DOWNTIME_BUFFERS: tuple[int | None, ...] = (0, 5, None, 20, 40)

# Section 5's axis. `sim/scenarios.py` says of its three technicians that "it is
# a scenario parameter and 7.3 is expected to vary it, because the roster size
# is the other half of every load ratio in this file" - and the committed sweep
# does not vary it. Three is in the list so the shipped scenario is a row rather
# than a reference point off the side of the table.
ROSTER_SWEEP: tuple[int, ...] = (1, 2, 3, 4, 6, 8)


@dataclass(frozen=True)
class Measure:
    """What one policy did over the seeds.

    The three measures 7.3 reports, and total down-minutes alongside them.
    That fourth one is not a measure of the policy - it is close to fixed for a
    given scenario, because the repairs are the repairs - and it is here for
    exactly that reason: a shift where every policy accumulates the same
    down-minutes and different units lost is a shift where the only lever is
    *which* machine is down, which is the reading section 4 rests on.
    """

    units_lost: float
    response_minutes: float
    unfinished: float
    down_minutes: float


@dataclass(frozen=True)
class MachineProfile:
    """One machine's shift under one policy.

    `waiting_minutes` and `repair_minutes` will not add up to `down_minutes`,
    and the discrepancy is the mechanism rather than a bug: a machine is down
    while *any* unfinished ticket names it, so a second failure during a repair
    extends the same outage instead of opening another. Where the two sums
    exceed the outage, the machine was failing again faster than it could be
    put back.
    """

    units_lost: float
    down_minutes: float
    waiting_minutes: float
    repair_minutes: float
    tickets: float


@dataclass
class Accounting:
    """What the shipped 3C threw away, and whether anybody could have taken it.

    Both counts are about the same suspicion from two directions: the adapter
    drops placements and the gate holds tickets, and either is only a cost if
    somebody was standing free who could have done that job. "Could" is the
    whole test - the right skill, enough minutes left, and a crew of the size
    the ticket asks for (ADR-025). A drop that nobody was free to take is a
    queue in front of a working technician, which is what a shift looks like.
    """

    rounds: int = 0
    placements_produced: int = 0
    placements_started: int = 0
    rounds_that_dropped: int = 0
    rounds_that_dropped_while_idle: int = 0
    rounds_that_held: int = 0
    rounds_that_held_while_idle: int = 0

    @property
    def placements_dropped(self) -> int:
        return self.placements_produced - self.placements_started


class Instrumented(GateAndScore):
    """The shipped 3C, counting what it declined to start and why.

    Subclassed rather than reimplemented on purpose. The question is what the
    committed adapter does; a copy of it here could answer the question
    correctly about the wrong code.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.books = Accounting()

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        starting = super().choose(state)
        decided = self.rounds[-1]
        books = self.books

        books.rounds += 1
        books.placements_produced += len(decided.placed)
        books.placements_started += len(starting)

        idle = _idle_after(state, starting)
        orders = {ticket.ref: ticket.order for ticket in (*state.pending, *state.in_progress)}
        left = dict(state.remaining_minutes)

        started_refs = {one.ref for one in starting}
        dropped = [one.ref for one in decided.placed if one.ref not in started_refs]
        if dropped:
            books.rounds_that_dropped += 1
            if _any_taker(dropped, orders, idle, left):
                books.rounds_that_dropped_while_idle += 1

        if decided.held:
            books.rounds_that_held += 1
            if _any_taker([one.ref for one in decided.held], orders, idle, left):
                books.rounds_that_held_while_idle += 1

        return starting


class FillTheRound(GateAndScore):
    """3C with the one-placement-per-technician rule lifted, to price it.

    Every decision is still `dispatch()`'s. The round simply does not stop after
    the first pass: the people who started something and the tickets that were
    started are removed, and the same function is asked again, until it adds
    nothing. That is the most generous version of the adapter that still obeys
    ADR-047 - nobody starts two machines at once - so if 3C's numbers do not
    move under it, `_starting_now` is not what the comparison is measuring.

    It is a measuring instrument and not a proposal. A real round asking the
    scheduler four times would re-rank the queue under a technician mid-walk,
    which design.md 6.2 rules out for a reason that has nothing to do with
    throughput.
    """

    name = "gate+score (round filled)"

    # Three technicians cannot need more passes than there are of them; the
    # bound is here so that a mistake below becomes a wrong number rather than
    # a run that never ends.
    _MAX_PASSES = 8

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        queue = [
            Queued(ref=ticket.ref, order=ticket.order, created_at=ticket.created_at)
            for ticket in (*state.pending, *state.in_progress)
        ]
        free = [one for one in state.technicians if one.user not in state.busy]

        starting: list[Placement] = []
        taken: set[UserId] = set()
        placed: set[str] = set()

        for pass_number in range(self._MAX_PASSES):
            candidates = [one for one in free if one.user not in taken]
            if not candidates:
                break
            decided = dispatch(
                [item for item in queue if item.ref not in placed],
                technicians=candidates,
                assignments=list(state.remaining_minutes),
                config=self.config,
                now=state.now,
                shift_id=state.shift_id,
                on_date=state.on_date,
            )
            # Only the first pass is the round this policy decided. The later
            # ones are the instrument; recording them would make `held` and
            # `bands` count the same round several times.
            if pass_number == 0:
                self.rounds.append(decided)
            fresh = [one for one in self._starting_now(decided) if not set(one.users) & taken]
            if not fresh:
                break
            for one in fresh:
                starting.append(one)
                placed.add(one.ref)
                taken.update(one.users)

        return tuple(starting)


def _idle_after(state: RoundState, starting: Sequence[Placement]) -> list[Technician]:
    """Rostered, active, not already under a machine, and given nothing this round."""
    working = {user for one in starting for user in one.users}
    return [
        one
        for one in state.technicians
        if one.active and one.user not in state.busy and one.user not in working
    ]


def _any_taker(
    refs: Sequence[str],
    orders: dict[str, WorkOrder],
    idle: Sequence[Technician],
    left: dict[UserId, int],
) -> bool:
    """Could one of the idle people have started one of these tickets?"""
    for ref in refs:
        order = orders.get(ref)
        if order is None:
            continue
        able = [
            one
            for one in idle
            if (order.required_skill is None or one.can_perform(order.required_skill))
            and left.get(one.user, 0) >= order.estimated_minutes
        ]
        if len(able) >= order.required_technicians:
            return True
    return False


def _admit_everything(
    ranked: Sequence[Any],
    *,
    band: Any,
    ratio: float,
    capacity: int,
    config: Config,
) -> tuple[list[Any], list[Withheld]]:
    """The load gate, removed. Ranking and assignment are left exactly as they are."""
    return list(ranked), []


@contextmanager
def without_the_gate() -> Iterator[None]:
    """An ablation, and it belongs here rather than behind a flag in `pdm/`.

    ADR-011 is a decision about how the system behaves, not a setting; giving
    the gate an off switch in production code would invite somebody to turn it
    off in a plant. The experiment is allowed to reach in because the experiment
    is not the system (ADR-051), and `patch` raises rather than passing quietly
    if the seam it reaches for is ever renamed.

    The thresholds cannot express this: `heavy_at_or_above` is capped at 1.0 and
    a stress window pushes `load_ratio` well past that, so no configuration puts
    every round in the light band.
    """
    with patch.object(dispatch_domain, "_admit", _admit_everything):
        yield


def with_weights(config: Config, **changes: float) -> Config:
    """The same configuration with some of the five weights moved.

    In memory and never written. `policy.yaml` says the weights are starting
    values to be derived from the simulator and Loop 6; this file is allowed to
    ask what they do and not to answer what they should be.
    """
    weights = config.policy.weights.model_copy(update=changes)
    return Config(config.plant, config.rules, config.policy.model_copy(update={"weights": weights}))


def _gate_and_score(config: Config) -> Callable[[], GateAndScore]:
    """A 3C factory bound to one configuration.

    A function rather than a lambda written inside the sweep loops: a closure
    over a loop variable is correct here only because `measure` is called in the
    same iteration, and that is precisely the kind of thing that stops being
    true when somebody collects the factories first.
    """
    return lambda: GateAndScore(config)


def with_roster(scenario: SimScenario, size: int) -> SimScenario:
    """The same shift with more or fewer people on it.

    Everything else is held: the same line, the same arrivals, the same
    available minutes each. The technicians are copies of the scenario's own
    first one, so the skill vocabulary comes from there rather than being
    restated here - a roster whose skills drifted from the scenario's would
    change what the w3 term does while claiming to change only headcount.
    """
    template = scenario.technicians[0]
    minutes = scenario.assignments[0].available_minutes
    roster = tuple(
        template.model_copy(update={"user": UserId(f"tech-{index}")})
        for index in range(1, size + 1)
    )
    return scenario.model_copy(
        update={
            "technicians": roster,
            "assignments": tuple(
                ShiftAssignment(
                    shift_id=scenario.shift_id,
                    on_date=scenario.starts_at.date(),
                    technician=one.user,
                    available_minutes=minutes,
                )
                for one in roster
            ),
        }
    )


def measure(
    factory: Callable[[], Any],
    *,
    config: Config,
    seeds: Sequence[int],
    scenario: SimScenario = LINE_A_ONE_SHIFT,
) -> Measure:
    """One policy over the seeds. A fresh instance per run - `GateAndScore`
    accumulates the rounds it decided, so a shared one reports two shifts."""
    lost: list[float] = []
    response: list[float] = []
    unfinished: list[float] = []
    down: list[float] = []
    for seed in seeds:
        result = run(scenario, policy=factory(), config=config, seed=seed)
        lost.append(result.units_lost)
        if result.mean_response_minutes is not None:
            response.append(result.mean_response_minutes)
        unfinished.append(float(result.tickets_unfinished))
        down.append(result.downtime_minutes)
    return Measure(
        units_lost=statistics.fmean(lost),
        response_minutes=statistics.fmean(response) if response else 0.0,
        unfinished=statistics.fmean(unfinished),
        down_minutes=statistics.fmean(down),
    )


def account(
    config: Config, seeds: Sequence[int], scenario: SimScenario = LINE_A_ONE_SHIFT
) -> Accounting:
    """The shipped 3C over the seeds, with its books kept."""
    total = Accounting()
    for seed in seeds:
        policy = Instrumented(config)
        run(scenario, policy=policy, config=config, seed=seed)
        books = policy.books
        total.rounds += books.rounds
        total.placements_produced += books.placements_produced
        total.placements_started += books.placements_started
        total.rounds_that_dropped += books.rounds_that_dropped
        total.rounds_that_dropped_while_idle += books.rounds_that_dropped_while_idle
        total.rounds_that_held += books.rounds_that_held
        total.rounds_that_held_while_idle += books.rounds_that_held_while_idle
    return total


def per_machine(
    factory: Callable[[], Any],
    *,
    config: Config,
    seeds: Sequence[int],
    scenario: SimScenario = LINE_A_ONE_SHIFT,
) -> dict[MachineId, MachineProfile]:
    """Where each machine's downtime went, under one policy.

    The total says which policy won; this says where, and ADR-021's whole claim
    is about where. Four numbers rather than one, because "3C lost the same at
    the critical station" has two completely different explanations and only
    this split tells them apart: a policy that never got there, or a policy that
    got there sooner and could not bank it.
    """
    lost: dict[MachineId, list[float]] = defaultdict(list)
    down: dict[MachineId, list[float]] = defaultdict(list)
    waiting: dict[MachineId, list[float]] = defaultdict(list)
    repairing: dict[MachineId, list[float]] = defaultdict(list)
    raised: dict[MachineId, list[float]] = defaultdict(list)

    for seed in seeds:
        result = run(scenario, policy=factory(), config=config, seed=seed)
        run_lost: dict[MachineId, float] = defaultdict(float)
        run_down: dict[MachineId, float] = defaultdict(float)
        run_wait: dict[MachineId, float] = defaultdict(float)
        run_repair: dict[MachineId, float] = defaultdict(float)
        run_count: dict[MachineId, float] = defaultdict(float)
        for outage in result.outages:
            run_lost[outage.machine_id] += outage.units_lost
            run_down[outage.machine_id] += outage.down_minutes
        for ticket in result.tickets:
            run_count[ticket.machine_id] += 1
            if ticket.response_minutes is not None:
                run_wait[ticket.machine_id] += ticket.response_minutes
            if ticket.started_at is not None:
                run_repair[ticket.machine_id] += ticket.repair_minutes
        for machine in _machines(config):
            lost[machine].append(run_lost.get(machine, 0.0))
            down[machine].append(run_down.get(machine, 0.0))
            waiting[machine].append(run_wait.get(machine, 0.0))
            repairing[machine].append(run_repair.get(machine, 0.0))
            raised[machine].append(run_count.get(machine, 0.0))

    return {
        machine: MachineProfile(
            units_lost=statistics.fmean(lost[machine]),
            down_minutes=statistics.fmean(down[machine]),
            waiting_minutes=statistics.fmean(waiting[machine]),
            repair_minutes=statistics.fmean(repairing[machine]),
            tickets=statistics.fmean(raised[machine]),
        )
        for machine in lost
    }


def _machines(config: Config) -> list[MachineId]:
    return sorted(
        machine.machine_id
        for line in config.plant.lines
        if line.line_id == LINE_A_ONE_SHIFT.line_id
        for station in line.stations
        for machine in station.machines
    )


def _station_label(config: Config, machine: MachineId) -> str:
    for line in config.plant.lines:
        for station in line.stations:
            for one in station.machines:
                if one.machine_id == machine:
                    bottleneck = (
                        f" x{station.bottleneck_multiplier:g}"
                        if station.bottleneck_multiplier != 1.0
                        else ""
                    )
                    return f"{station.station_id} buf {station.buffer_units}{bottleneck}"
    return str(machine)


@dataclass(frozen=True)
class Diagnosis:
    """Everything the four questions turned up, so that the write-up below and
    a test can read the same values."""

    seeds: tuple[int, ...]
    technicians: int
    fifo: Measure
    matrix: Measure
    shipped: Measure
    filled: Measure
    ungated: Measure
    books: Accounting
    waiting_sweep: tuple[tuple[float, Measure], ...]
    downtime_sweep: tuple[tuple[int | None, str, Measure], ...]
    roster_sweep: tuple[tuple[int, str, Measure], ...]
    machines: tuple[tuple[str, MachineProfile, MachineProfile], ...]


def diagnose(*, seeds: Sequence[int], config: Config, technicians: int | None = None) -> Diagnosis:
    """The whole diagnosis. Deterministic: same arguments, same answer.

    `technicians` diagnoses the same shift with a different roster - the one the
    roster sweeps of `compare_policies.py --technicians` ran (ADR-124). With the
    shipped three the policies barely differ, so a diagnosis of why they differ
    is most informative where they do. Sections 1 to 4 run on that roster;
    section 5 sweeps the roster itself and does not depend on it.
    """
    seeds = tuple(seeds)
    shift = LINE_A_ONE_SHIFT if technicians is None else with_roster(LINE_A_ONE_SHIFT, technicians)

    def on_shift(factory: Callable[[], Any], variant: Config) -> Measure:
        return measure(factory, config=variant, seeds=seeds, scenario=shift)

    fifo = on_shift(FirstComeFirstServed, config)
    matrix = on_shift(PriorityMatrix, config)
    shipped = on_shift(_gate_and_score(config), config)
    filled = on_shift(lambda: FillTheRound(config), config)
    with without_the_gate():
        ungated = on_shift(_gate_and_score(config), config)

    books = account(config, seeds, shift)

    waiting: list[tuple[float, Measure]] = []
    for weight in (0.0, config.policy.weights.waiting, 1.0, 3.0, 10.0, 30.0):
        variant = with_weights(config, waiting=weight)
        waiting.append((weight, on_shift(_gate_and_score(variant), variant)))

    downtime: list[tuple[int | None, str, Measure]] = []
    for units in DOWNTIME_BUFFERS:
        shaped = with_uniform_buffers(config, units)
        downtime.append((units, "3A", on_shift(FirstComeFirstServed, shaped)))
        for weight in (0.0, shaped.policy.weights.downtime, 4.0):
            variant = with_weights(shaped, downtime=weight)
            downtime.append(
                (units, f"w_downtime={weight:g}", on_shift(_gate_and_score(variant), variant))
            )

    roster: list[tuple[int, str, Measure]] = []
    for size in ROSTER_SWEEP:
        sized = with_roster(LINE_A_ONE_SHIFT, size)
        roster.append(
            (size, "3A", measure(FirstComeFirstServed, config=config, seeds=seeds, scenario=sized))
        )
        without_w2 = with_weights(config, downtime=0.0)
        roster.append(
            (
                size,
                "3C w_downtime=0",
                measure(
                    _gate_and_score(without_w2),
                    config=without_w2,
                    seeds=seeds,
                    scenario=sized,
                ),
            )
        )
        roster.append(
            (
                size,
                "3C shipped",
                measure(_gate_and_score(config), config=config, seeds=seeds, scenario=sized),
            )
        )

    fifo_machines = per_machine(FirstComeFirstServed, config=config, seeds=seeds, scenario=shift)
    shipped_machines = per_machine(
        _gate_and_score(config), config=config, seeds=seeds, scenario=shift
    )
    machines = tuple(
        (_station_label(config, machine), fifo_machines[machine], shipped_machines[machine])
        for machine in _machines(config)
    )

    return Diagnosis(
        seeds=seeds,
        technicians=len(shift.technicians),
        fifo=fifo,
        matrix=matrix,
        shipped=shipped,
        filled=filled,
        ungated=ungated,
        books=books,
        waiting_sweep=tuple(waiting),
        downtime_sweep=tuple(downtime),
        roster_sweep=tuple(roster),
        machines=machines,
    )


def _row(label: str, measured: Measure) -> str:
    return (
        f"| {label} | {measured.units_lost:.1f} | "
        f"{measured.response_minutes:.2f} | {measured.unfinished:.2f} |"
    )


def _percent(change: float, base: float) -> float:
    return change / base * 100 if base else 0.0


def _shipped_roster(found: Diagnosis) -> str:
    shipped = len(LINE_A_ONE_SHIFT.technicians)
    note = " (the shipped roster)" if found.technicians == shipped else f" (shipped: {shipped})"
    people = "technician" if found.technicians == 1 else "technicians"
    return f"{found.technicians} {people}{note}"


def _verdict_on_both(first: str, a: Measure, second: str, b: Measure) -> str:
    """Which of two policies is better on units lost and on response, said once."""
    units = a.units_lost - b.units_lost
    response = a.response_minutes - b.response_minutes
    if abs(_percent(units, b.units_lost)) < 0.5 and abs(response) < 0.1:
        return f"**{first} and {second} are indistinguishable here on both measures.**"
    if units < 0 and response <= 0:
        return f"**{first} is better than {second} on both measures here.**"
    if units > 0 and response >= 0:
        return f"**{second} is better than {first} on both measures here.**"
    cheaper = first if units < 0 else second
    faster = first if response < 0 else second
    return (
        f"**{cheaper} loses less production and {faster} reaches machines sooner: "
        "the two measures trade against each other here and neither policy "
        "dominates.**"
    )


def write_markdown(found: Diagnosis, path: Path) -> None:
    """The write-up. Every sentence that draws a conclusion is computed from the
    table above it; the earlier version argued a mechanism in fixed prose, and
    ADR-124 left that prose describing a model that no longer existed."""
    books = found.books
    dropped_share = _percent(books.placements_dropped, books.placements_produced)

    lines = [
        "# Why the comparison came out the way it did",
        "",
        "**Generated by `scripts/diagnose_comparison.py`. Do not edit by hand.**",
        "",
        f"- scenario: `{LINE_A_ONE_SHIFT.name}` with {_shipped_roster(found)}, "
        "the shipped layout, arrival multiplier 1.0",
        f"- seeds: {', '.join(str(seed) for seed in found.seeds)} "
        f"({len(found.seeds)} runs behind every number)",
        "",
        "`comparison.md` reports what happened. This file asks why, in the only",
        "way available without a plant: by removing one piece at a time and",
        "running the same shifts again. No weight in `config/policy.yaml` is",
        "changed by any of it (issue #27 put tuning out of scope).",
        "",
        "Since ADR-124 a machine that is already stopped does not fail again. The",
        "mechanism earlier versions of this file argued - a critical station",
        "failing again before a faster response could be banked - was a property",
        "of the old model and is withdrawn. Every sentence below that draws a",
        "conclusion is now computed from the table above it.",
        "",
        "## 1. Is the comparison measuring its own adapter?",
        "",
        "`GateAndScore._starting_now` keeps each technician's highest-ranked",
        "placement and drops the rest, because `dispatch()` answers *who is this",
        "assigned to* and the simulator asks *who starts now*. `FillTheRound`",
        "prices that: it calls `dispatch()` again with the started people and",
        "tickets removed, until the round adds nothing.",
        "",
        "| | units lost | response (min) | unfinished |",
        "|---|---:|---:|---:|",
        _row("3C as shipped", found.shipped),
        _row("3C, round filled by re-dispatching", found.filled),
        "",
        f"Across {len(found.seeds)} shifts the adapter dropped "
        f"{books.placements_dropped} of the {books.placements_produced} placements "
        f"`dispatch()` produced ({dropped_share:.0f}%), in "
        f"{books.rounds_that_dropped} rounds of {books.rounds} - and in "
        f"**{books.rounds_that_dropped_while_idle}** of those rounds was there a "
        "technician left idle who could have taken one of them.",
        "",
    ]
    if books.rounds_that_dropped_while_idle == 0:
        lines += [
            "What the adapter drops is therefore the queue in front of somebody",
            "already working, which is what a shift looks like rather than a loss.",
            "",
        ]
    else:
        lines += [
            "So the adapter does leave somebody idle who could have worked, and the",
            "filled row above is what that costs.",
            "",
        ]

    gate_change = found.ungated.units_lost - found.shipped.units_lost
    gate_share = _percent(gate_change, found.shipped.units_lost)
    lines += [
        "## 2. Does the gate cost 3C production?",
        "",
        "The gate removed entirely - admitting everything, ranking and assigning",
        "unchanged:",
        "",
        "| | units lost | response (min) | unfinished |",
        "|---|---:|---:|---:|",
        _row("3C as shipped", found.shipped),
        _row("3C with the gate removed", found.ungated),
        _row("3A first-come-first-served", found.fifo),
        "",
        f"{books.rounds_that_held} rounds held something, and in "
        f"**{books.rounds_that_held_while_idle}** of them was a technician left "
        "idle who could have taken a held ticket.",
    ]
    if books.rounds_that_held == 0:
        lines.append("The gate never held anything on this roster, so the two rows cannot differ.")
    elif abs(gate_share) < 1.0:
        lines.append(
            f"Removing it moves units lost by {gate_change:+.1f} ({gate_share:+.1f}%): "
            "**the gate is not what separates 3C from 3A.**"
        )
    elif gate_change < 0:
        lines.append(
            f"Removing it lowers units lost by {-gate_change:.1f} ({gate_share:.1f}%): "
            "**on this roster holding work back costs production.**"
        )
    else:
        lines.append(
            f"Removing it raises units lost by {gate_change:.1f} ({gate_share:+.1f}%): "
            "**on this roster holding work back pays.**"
        )

    shipped_weight = found.shipped
    heaviest_weight, heaviest = found.waiting_sweep[-1]
    lines += [
        "",
        "## 3. The waiting term",
        "",
        "One weight moved at a time, everything else at its shipped value:",
        "",
        "| w_waiting | units lost | response (min) | unfinished |",
        "|---:|---:|---:|---:|",
    ]
    for weight, measured in found.waiting_sweep:
        lines.append(_row(f"{weight:g}", measured))
    lines += [
        _row("*3A, for reference*", found.fifo),
        "",
        f"From the shipped weight to {heaviest_weight:g}, units lost go from "
        f"{shipped_weight.units_lost:.1f} to {heaviest.units_lost:.1f} (3A "
        f"{found.fifo.units_lost:.1f}) and response from "
        f"{shipped_weight.response_minutes:.2f} to {heaviest.response_minutes:.2f} "
        f"minutes (3A {found.fifo.response_minutes:.2f}).",
        _verdict_on_both("3C", found.shipped, "3A", found.fifo),
        "No value in the column above is a recommendation: 3E is the tool for",
        "setting these, and guessing again is what ADR-045 declined to do.",
        "",
        "## 4. ADR-021's downtime term",
        "",
        "Units lost, by uniform buffer setting:",
        "",
        "| buffer | policy | units lost | response (min) |",
        "|---|---|---:|---:|",
    ]
    spread_by_layout: dict[int | None, list[float]] = defaultdict(list)
    for units, label, measured in found.downtime_sweep:
        buffer_label = "as configured" if units is None else f"{units} units"
        lines.append(
            f"| {buffer_label} | {label} | {measured.units_lost:.1f} "
            f"| {measured.response_minutes:.2f} |"
        )
        if label != "3A":
            spread_by_layout[units].append(measured.units_lost)
    widest = max(
        _percent(max(values) - min(values), statistics.fmean(values))
        for values in spread_by_layout.values()
    )
    lines += [
        "",
        f"Turning w2 off and turning it up to four moves units lost by at most "
        f"{widest:.1f}% at any layout, the unbuffered one included. Where the lost",
        "production sits:",
        "",
        "| station | 3A units lost | 3C units lost | 3A down-min | 3C down-min |",
        "|---|---:|---:|---:|---:|",
    ]
    worst = max(found.machines, key=lambda one: one[2].units_lost)
    for label, under_fifo, under_gate in found.machines:
        lines.append(
            f"| {label} | {under_fifo.units_lost:.1f} | {under_gate.units_lost:.1f} "
            f"| {under_fifo.down_minutes:.1f} | {under_gate.down_minutes:.1f} |"
        )
    total_shipped = sum(one[2].units_lost for one in found.machines)
    share = _percent(worst[2].units_lost, total_shipped)
    worst_gap = worst[2].units_lost - worst[1].units_lost
    total_gap = sum(one[2].units_lost - one[1].units_lost for one in found.machines)
    lines += [
        "",
        f"`{worst[0]}` is {share:.0f}% of everything 3C loses. Of the "
        f"{total_gap:+.1f}-unit gap between 3C and 3A, {worst_gap:+.1f} is at that "
        f"station and {total_gap - worst_gap:+.1f} at the others. Total down-minutes: "
        f"{found.fifo.down_minutes:.1f} under 3A against "
        f"{found.shipped.down_minutes:.1f} under 3C.",
        "",
        "Each machine's tickets split into the time they waited and the time they",
        "were repaired, with the failures each machine raised per shift:",
        "",
        "| station | 3A waiting | 3C waiting | 3A repair | 3C repair | failures |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for label, under_fifo, under_gate in found.machines:
        lines.append(
            f"| {label} | {under_fifo.waiting_minutes:.1f} "
            f"| {under_gate.waiting_minutes:.1f} | {under_fifo.repair_minutes:.1f} "
            f"| {under_gate.repair_minutes:.1f} | {under_gate.tickets:.2f} |"
        )
    sooner = worst[2].waiting_minutes < worst[1].waiting_minutes
    lines += [
        "",
        f"At `{worst[0]}` 3C's tickets waited {worst[2].waiting_minutes:.1f} minutes "
        f"against 3A's {worst[1].waiting_minutes:.1f}: "
        + (
            "3C does reach the critical station sooner."
            if sooner
            else "3C does not reach the critical station sooner on this roster."
        ),
        "",
        "## 5. The roster",
        "",
        "The same shift with more or fewer people, everything else held:",
        "",
        "| technicians | policy | units lost | response (min) | unfinished |",
        "|---:|---|---:|---:|---:|",
    ]
    for size, label, measured in found.roster_sweep:
        lines.append(
            f"| {size} | {label} | {measured.units_lost:.1f} "
            f"| {measured.response_minutes:.2f} | {measured.unfinished:.2f} |"
        )

    by_size: dict[int, dict[str, Measure]] = {}
    for size, label, measured in found.roster_sweep:
        by_size.setdefault(size, {})[label] = measured
    lines += [
        "",
        "What w2 is worth at each roster size, and what the whole score is worth",
        "against first-come-first-served (positive: 3C is better):",
        "",
        "| technicians | w2 off - w2 on (units) | 3A - 3C (units) | 3A - 3C (response, min) |",
        "|---:|---:|---:|---:|",
    ]
    w2_worth: list[float] = []
    for size in sorted(by_size):
        cell = by_size[size]
        w2 = cell["3C w_downtime=0"].units_lost - cell["3C shipped"].units_lost
        against = cell["3A"].units_lost - cell["3C shipped"].units_lost
        faster = cell["3A"].response_minutes - cell["3C shipped"].response_minutes
        w2_worth.append(_percent(abs(w2), cell["3C shipped"].units_lost))
        lines.append(f"| {size} | {w2:+.1f} | {against:+.1f} | {faster:+.1f} |")

    smallest, biggest = min(by_size), max(by_size)
    thin = (
        by_size[smallest]["3A"].response_minutes - by_size[smallest]["3C shipped"].response_minutes
    )
    thick = (
        by_size[biggest]["3A"].response_minutes - by_size[biggest]["3C shipped"].response_minutes
    )
    costlier = [
        size
        for size in sorted(by_size)
        if by_size[size]["3C shipped"].units_lost > by_size[size]["3A"].units_lost * 1.005
    ]
    lines += [
        "",
        f"The downtime term is worth at most {max(w2_worth):.1f}% of units lost at "
        f"any roster size from {smallest} to {biggest}. 3C's response advantage over "
        f"first-come-first-served is {thin:+.1f} minutes with {smallest} "
        f"technician{'s' if smallest != 1 else ''} and {thick:+.1f} with {biggest}"
        + (
            ": **scheduling is worth most when there are not enough people**, which "
            "is the condition a plant installs one for."
            if thin > thick + 1.0
            else "."
        ),
        (
            "3C loses more production than first-come-first-served (by more than "
            f"half a percent) with {', '.join(str(size) for size in costlier)} "
            "technicians: reaching machines sooner is not the same as stopping the "
            "line for less time."
            if costlier
            else "3C loses no more production than first-come-first-served at any roster size."
        ),
        "",
        "Every figure here is at the one arrival rate the shipped scenario assumes,",
        "and `mean_hours_between_failures` has no measurement behind it (ADR-046",
        "§4); `comparison.md` sweeps it.",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose the policy comparison.")
    parser.add_argument("--seeds", type=int, default=20, help="how many seeds per cell")
    parser.add_argument(
        "--technicians",
        type=int,
        default=None,
        help="diagnose the shift with this many people (default: the scenario's own)",
    )
    parser.add_argument("--out", type=Path, default=RESULTS, help="where to write the results")
    args = parser.parse_args(argv)

    config = load_config(REPO / "config")
    found = diagnose(seeds=range(args.seeds), config=config, technicians=args.technicians)
    write_markdown(found, args.out / "diagnosis.md")

    print(f"3A first-come-first-served   units lost {found.fifo.units_lost:8.1f}")
    print(f"3C as shipped                units lost {found.shipped.units_lost:8.1f}")
    print(f"3C, round filled             units lost {found.filled.units_lost:8.1f}")
    print(f"3C, gate removed             units lost {found.ungated.units_lost:8.1f}")
    print(f"written: {args.out / 'diagnosis.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

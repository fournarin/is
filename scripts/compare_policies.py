"""Run the three policies over the same shifts and write down what happened.

Phase 2's deliverable. Two baselines - what a plant does today - against the
gate and the score, over a grid of seeds, buffer maps and arrival rates, and the
output committed so that a reader can check it rather than take it.

**The sweep is the point, not the headline number.** ADR-021 refused a single
buffer map because the layout is assumed, and ADR-046 §4 refused a single
arrival rate for the same reason: `mean_hours_between_failures` is the one
figure in this project with no measurement behind it. A table with one row would
be a table of assumptions presented as results. So every figure here carries the
buffer setting and the arrival rate it was produced under, and the interesting
column is how the gap between the policies *moves* as those change.

Nothing here tunes anything. If the weights come out looking wrong, that is a
finding for the report (`policy.yaml` says they are starting values), not
something to quietly correct until the table flatters us.

Usage:

    uv run python scripts/compare_policies.py                # writes docs/results/
    uv run python scripts/compare_policies.py --seeds 4      # a quicker pass
"""

from __future__ import annotations

import argparse
import csv
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pdm.baselines import FirstComeFirstServed, PriorityMatrix
from pdm.contracts import UserId
from pdm.dispatch import Band, Queued, Round, dispatch
from pdm.platform.config import Config, load_config
from pdm.platform.config.schema import LineConfig, PlantConfig, StationConfig
from pdm.sim import Placement, RoundState, SimRun, SimScenario, run
from pdm.sim.scenarios import LINE_A_ONE_SHIFT

REPO = Path(__file__).resolve().parent.parent
RESULTS = REPO / "docs" / "results"

# Uniform stock at every station, in units. The shipped layout is in the table
# as well, unchanged, because it is the only one that came from anywhere.
BUFFER_SWEEP: tuple[int | None, ...] = (None, 0, 5, 10, 20, 40)

# Multipliers on every window's mean time between failures. Above 1.0 is a
# quieter plant than the scenario assumes, below it a busier one. ADR-046 §4
# requires this column to exist; it does not say what the true value is, and
# neither does this file.
ARRIVAL_SWEEP: tuple[float, ...] = (0.5, 1.0, 2.0)


class GateAndScore:
    """3C: `dispatch()` behind the simulator's policy protocol.

    An adapter and not a rewrite, which is what ADR-046 §5 shaped `RoundState`
    to allow. Three translations matter and each fails quietly if it is wrong:

    * `pending` and `in_progress` go in as one queue, because `load_ratio` is a
      sum over everything open (design.md 13.2) and a round that saw only the
      waiting half would read the shift as emptier than it is;
    * a technician in `busy` stays in `assignments` - their minutes are capacity
      the shift really has - and is kept out of `technicians`, because they
      cannot take a second machine;
    * `remaining_minutes` goes in as it stands. It counts a job when it finishes
      rather than while it runs, and `dispatch()` subtracts work in flight
      itself; passing something already net of it would charge the shift twice.

    It lives here rather than in `pdm/` because it is a subject of this
    experiment, not part of the system (ADR-051).
    """

    name = "gate+score"

    def __init__(self, config: Config) -> None:
        self.config = config
        self.rounds: list[Round] = []

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        queue = [
            Queued(ref=ticket.ref, order=ticket.order, created_at=ticket.created_at)
            for ticket in (*state.pending, *state.in_progress)
        ]
        free = [technician for technician in state.technicians if technician.user not in state.busy]
        decided = dispatch(
            queue,
            technicians=free,
            assignments=list(state.remaining_minutes),
            config=self.config,
            now=state.now,
            shift_id=state.shift_id,
            on_date=state.on_date,
        )
        self.rounds.append(decided)
        return self._starting_now(decided)

    @staticmethod
    def _starting_now(decided: Round) -> tuple[Placement, ...]:
        """The fourth translation, and the one the seam does not make obvious.

        `dispatch()` answers "who is this job assigned to", and a technician with
        eight hours left can be assigned four two-hour jobs in one round - that
        is a queue in front of a person, and it is what a real shift looks like.
        The simulator asks a different question: **who starts now**. Nobody
        starts two machines at once, and the engine refuses a round that says so
        (ADR-046 §5).

        So each technician's highest-ranked placement is taken and the rest are
        left pending. Nothing is lost and nothing is reordered: `decided.placed`
        is already in score order, the round after this one ranks what is still
        waiting, and a five-minute cadence means the wait for the second job is
        five minutes rather than a shift.

        A crew is all or nothing here too: a two-person job whose second member
        was already taken by a higher-ranked job waits for a round in which both
        are free, rather than being started by half its crew (ADR-025).
        """
        taken: set[UserId] = set()
        starting: list[Placement] = []
        for placement in decided.placed:
            users = tuple(one.user for one in placement.assignees)
            if any(user in taken for user in users):
                continue
            taken.update(users)
            starting.append(
                Placement(
                    ref=placement.ref,
                    users=users,
                    priority_score=placement.priority_score,
                    priority_reason=placement.priority_reason,
                )
            )
        return tuple(starting)

    @property
    def held(self) -> int:
        """Tickets the gate declined to release, counted across the shift.

        Held is not lost: the same ticket held in ten consecutive rounds counts
        ten times here, and that is the honest reading of "how much work was the
        gate sitting on" rather than of "how many jobs were affected".
        """
        return sum(len(one.held) for one in self.rounds)

    @property
    def bands(self) -> dict[str, int]:
        """How many rounds sat in each of ADR-011's regimes. The whole claim of
        that record is that behaviour changes between them, so a comparison that
        did not say which band the shift was in would be hiding the mechanism."""
        counted: dict[str, int] = {}
        for one in self.rounds:
            counted[one.band.value] = counted.get(one.band.value, 0) + 1
        return counted


@dataclass(frozen=True)
class Row:
    """One cell of the experiment: a policy, a layout, a rate, a seed."""

    policy: str
    buffer_units: int | None
    arrival_multiplier: float
    seed: int
    units_lost: float
    downtime_minutes: float
    tickets_raised: int
    tickets_finished: int
    tickets_unfinished: int
    mean_response_minutes: float | None
    held_rounds: int = 0
    light_rounds: int = 0
    normal_rounds: int = 0
    heavy_rounds: int = 0
    no_capacity_rounds: int = 0

    @property
    def buffer_label(self) -> str:
        return "as configured" if self.buffer_units is None else f"{self.buffer_units} units"


def with_uniform_buffers(config: Config, units: int | None) -> Config:
    """The same plant with the same machines and a different amount of stock.

    Only `buffer_units` moves. `bottleneck_multiplier` is deliberately left
    alone: what this sweep varies is how much a station can absorb before the
    line feels it, and changing two things at once would produce a table nobody
    could read a cause out of.
    """
    if units is None:
        return config
    plant: PlantConfig = config.plant
    lines = tuple(
        LineConfig(
            line_id=line.line_id,
            takt_seconds=line.takt_seconds,
            stations=tuple(
                StationConfig(
                    station_id=station.station_id,
                    seq=station.seq,
                    buffer_units=units,
                    bottleneck_multiplier=station.bottleneck_multiplier,
                    machines=station.machines,
                )
                for station in line.stations
            ),
        )
        for line in plant.lines
    )
    return Config(plant.model_copy(update={"lines": lines}), config.rules, config.policy)


def with_arrival_multiplier(scenario: SimScenario, multiplier: float) -> SimScenario:
    """The same shift with failures arriving more or less often.

    Multiplies the mean time *between* failures, so a multiplier above one is a
    quieter plant. The windows keep their names, because the band each of them
    reaches is what the comparison is read against.
    """
    if multiplier == 1.0:
        return scenario
    windows = tuple(
        window.model_copy(
            update={"mean_hours_between_failures": window.mean_hours_between_failures * multiplier}
        )
        for window in scenario.windows
    )
    return scenario.model_copy(update={"windows": windows})


def _row(
    policy_name: str,
    result: SimRun,
    *,
    buffer_units: int | None,
    multiplier: float,
    seed: int,
    gate: GateAndScore | None,
) -> Row:
    bands = gate.bands if gate is not None else {}
    return Row(
        policy=policy_name,
        buffer_units=buffer_units,
        arrival_multiplier=multiplier,
        seed=seed,
        units_lost=result.units_lost,
        downtime_minutes=result.downtime_minutes,
        tickets_raised=result.tickets_raised,
        tickets_finished=result.tickets_finished,
        tickets_unfinished=result.tickets_unfinished,
        mean_response_minutes=result.mean_response_minutes,
        held_rounds=gate.held if gate is not None else 0,
        light_rounds=bands.get(Band.LIGHT.value, 0),
        normal_rounds=bands.get(Band.NORMAL.value, 0),
        heavy_rounds=bands.get(Band.HEAVY.value, 0),
        no_capacity_rounds=bands.get(Band.NO_CAPACITY.value, 0),
    )


def compare(
    *,
    seeds: Sequence[int],
    buffers: Sequence[int | None] = BUFFER_SWEEP,
    arrivals: Sequence[float] = ARRIVAL_SWEEP,
    scenario: SimScenario = LINE_A_ONE_SHIFT,
    config: Config | None = None,
) -> list[Row]:
    """The whole grid. Deterministic: same arguments, same rows, every time."""
    base = config or load_config(REPO / "config")
    rows: list[Row] = []
    for units in buffers:
        shaped = with_uniform_buffers(base, units)
        for multiplier in arrivals:
            variant = with_arrival_multiplier(scenario, multiplier)
            for seed in seeds:
                for name, policy, gate in _policies(shaped):
                    result = run(variant, policy=policy, config=shaped, seed=seed)
                    rows.append(
                        _row(
                            name,
                            result,
                            buffer_units=units,
                            multiplier=multiplier,
                            seed=seed,
                            gate=gate,
                        )
                    )
    return rows


def _policies(config: Config) -> list[tuple[str, Any, GateAndScore | None]]:
    """Fresh instances per run. `GateAndScore` accumulates the rounds it decided,
    so reusing one across seeds would report the second shift's gate behaviour on
    top of the first's."""
    gate = GateAndScore(config)
    return [
        ("3A first-come-first-served", FirstComeFirstServed(), None),
        ("3B priority matrix", PriorityMatrix(), None),
        ("3C gate + score", gate, gate),
    ]


@dataclass
class Summary:
    """Rows for one (policy, buffer, arrival) cell, averaged over the seeds."""

    policy: str
    buffer_label: str
    arrival_multiplier: float
    runs: list[Row] = field(default_factory=list)

    def mean(self, attribute: str) -> float | None:
        values = [
            value for value in (getattr(row, attribute) for row in self.runs) if value is not None
        ]
        return statistics.fmean(values) if values else None


def summarise(rows: Iterable[Row]) -> list[Summary]:
    grouped: dict[tuple[str, str, float], Summary] = {}
    for row in rows:
        key = (row.policy, row.buffer_label, row.arrival_multiplier)
        grouped.setdefault(key, Summary(row.policy, row.buffer_label, row.arrival_multiplier))
        grouped[key].runs.append(row)
    return list(grouped.values())


def write_csv(rows: Sequence[Row], path: Path) -> None:
    """Every run, not the averages. The summary is a reading of this file, and a
    reader who disagrees with the reading needs the rows to do their own."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        # `csv` writes CRLF by default, which would make a committed file churn
        # between platforms and every diff of it unreadable.
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(
            [
                "policy",
                "buffer_units",
                "arrival_multiplier",
                "seed",
                "units_lost",
                "downtime_minutes",
                "tickets_raised",
                "tickets_finished",
                "tickets_unfinished",
                "mean_response_minutes",
                "held_rounds",
                "light_rounds",
                "normal_rounds",
                "heavy_rounds",
                "no_capacity_rounds",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row.policy,
                    "" if row.buffer_units is None else row.buffer_units,
                    row.arrival_multiplier,
                    row.seed,
                    f"{row.units_lost:.2f}",
                    f"{row.downtime_minutes:.2f}",
                    row.tickets_raised,
                    row.tickets_finished,
                    row.tickets_unfinished,
                    "" if row.mean_response_minutes is None else f"{row.mean_response_minutes:.2f}",
                    row.held_rounds,
                    row.light_rounds,
                    row.normal_rounds,
                    row.heavy_rounds,
                    row.no_capacity_rounds,
                ]
            )


def _cell(value: float | None, places: int = 1) -> str:
    return "-" if value is None else f"{value:.{places}f}"


def write_markdown(rows: Sequence[Row], path: Path, *, seeds: Sequence[int]) -> None:
    summaries = summarise(rows)
    arrivals = sorted({one.arrival_multiplier for one in summaries})
    buffers = [label for label in dict.fromkeys(one.buffer_label for one in summaries)]
    policies = list(dict.fromkeys(one.policy for one in summaries))

    lines = [
        "# Three policies over the same shifts",
        "",
        "**Generated by `scripts/compare_policies.py`. Do not edit by hand.**",
        "",
        f"- scenario: `{LINE_A_ONE_SHIFT.name}`, "
        f"{int(LINE_A_ONE_SHIFT.duration.total_seconds() // 3600)} hours, "
        f"{len(LINE_A_ONE_SHIFT.technicians)} technicians",
        f"- seeds: {', '.join(str(seed) for seed in seeds)} "
        f"({len(seeds)} runs behind every number below)",
        f"- buffer settings: {', '.join(buffers)}",
        f"- arrival multipliers: {', '.join(str(one) for one in arrivals)} "
        "(multiplies the mean time *between* failures, so above 1.0 is a quieter plant)",
        "",
        "Every figure is a mean over the seeds. `docs/results/comparison.csv` holds "
        "each run, so the reading below can be checked rather than taken.",
        "",
        "Read `README.md` in this directory first. It says what this is not.",
        "",
    ]

    for multiplier in arrivals:
        lines += [
            f"## Arrival multiplier {multiplier}",
            "",
            "| buffer | policy | units lost | unfinished | mean response (min) "
            "| rounds held | light / normal / heavy |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for label in buffers:
            for policy in policies:
                found = [
                    one
                    for one in summaries
                    if one.policy == policy
                    and one.buffer_label == label
                    and one.arrival_multiplier == multiplier
                ]
                if not found:
                    continue
                cell = found[0]
                bands = (
                    f"{_cell(cell.mean('light_rounds'), 0)} / "
                    f"{_cell(cell.mean('normal_rounds'), 0)} / "
                    f"{_cell(cell.mean('heavy_rounds'), 0)}"
                    if policy.startswith("3C")
                    else "-"
                )
                lines.append(
                    f"| {label} | {policy} | {_cell(cell.mean('units_lost'))} "
                    f"| {_cell(cell.mean('tickets_unfinished'))} "
                    f"| {_cell(cell.mean('mean_response_minutes'))} "
                    f"| {_cell(cell.mean('held_rounds'), 0)} | {bands} |"
                )
        lines.append("")

    lines += [
        "## The gap, and what closes it",
        "",
        "The column worth reading is not any single number but how the distance "
        "between the policies moves down the rows. ADR-021's claim is that a "
        "station's buffer decides what a stopped machine costs the line, so the "
        "advantage of a policy that knows about buffers might be expected to "
        "shrink as every station gets thicker ones. Whether it does is what this "
        "table is for; it is not assumed here, and the numbers below are "
        "reported whichever way they fall.",
        "",
        "| buffer | 3A - 3C units lost | 3B - 3C units lost |",
        "|---|---:|---:|",
    ]
    for label in buffers:
        gaps: dict[str, float] = {}
        for policy in policies:
            values = [
                one.mean("units_lost")
                for one in summaries
                if one.policy == policy and one.buffer_label == label
            ]
            usable = [value for value in values if value is not None]
            if usable:
                gaps[policy] = statistics.fmean(usable)
        if len(gaps) == len(policies):
            gate = gaps[policies[2]]
            lines.append(
                f"| {label} | {gaps[policies[0]] - gate:+.1f} | {gaps[policies[1]] - gate:+.1f} |"
            )
    lines += [
        "",
        "A positive number means the baseline lost more production than the gate "
        "and score did; a negative one means it lost less. Averaged across the "
        "arrival multipliers, so this table is coarser than the ones above it "
        "and is a shape rather than a result.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=20, help="how many seeds per cell")
    parser.add_argument("--out", type=Path, default=RESULTS, help="where to write the results")
    args = parser.parse_args(argv)

    seeds = list(range(args.seeds))
    rows = compare(seeds=seeds)
    write_csv(rows, args.out / "comparison.csv")
    write_markdown(rows, args.out / "comparison.md", seeds=seeds)

    print(f"{len(rows)} runs -> {args.out / 'comparison.csv'} and comparison.md")
    for summary in summarise(rows):
        if summary.buffer_label == "as configured" and summary.arrival_multiplier == 1.0:
            print(
                f"  {summary.policy:<28} units lost {_cell(summary.mean('units_lost'))}"
                f"  unfinished {_cell(summary.mean('tickets_unfinished'))}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

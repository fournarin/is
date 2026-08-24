"""Does the history ranking find the machines the generator degraded (ADR-072 §5)?

Run by hand:

    PYTHONPATH=. uv run python scripts/measure_health.py

No database and no model, so this one *could* run in CI - and does not, for the
reason `measure_prediction.py` does not: it is a measurement whose output belongs
in a document with a date on it, and a number that changes silently on every
commit is a number nobody trusts.

**What is measured.** `fixtures/history` generates a year of closed work orders
for the four machines of `config/plant.yaml`, degrading two of them inside
windows it records. `pdm.health.by_history` then ranks all four from those orders
alone, and the ranking is scored against the windows.

**What is not measured, and why.** Nothing here says anything about the *now*
half of a health reading. A maintenance-history generator writes closed work
orders, not signals, and inventing open Findings to go with them would be
scoring a ranking against Findings placed where it would find them. The live
half's ground truth exists already and belongs to ADR-020, which measures ETA
error against the noise-free curve; `docs/prediction-baseline.md` is where that
number lives (ADR-076 section 6).

**Write the output into `docs/results/health.md` when it changes.**
"""

from __future__ import annotations

import sys
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from fixtures.history import LINE_A_ONE_YEAR, HistoryPlan, SyntheticHistory
from pdm.contracts import MachineId
from pdm.health import MachineHealth, assess, by_history

# Twenty seeds is what `compare_policies.py` runs and forty is cheap here, since
# one draw is a few dozen work orders rather than a simulated shift. The point of
# more than one is the same: a single history is an anecdote, and the interesting
# figure is how often the ranking is right rather than whether it was once.
SEEDS = 40


class Ranked(BaseModel):
    """One machine's place in one draw, and the figures that put it there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int
    machine_id: MachineId
    rank: int
    degraded: bool
    failures: int
    failures_per_100_days: float | None
    days_since_last_failure: float | None
    pm_overdue: int
    false_alarms: int


class Measurement(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    plan: str
    seeds: int
    machines: int
    degraded: tuple[MachineId, ...]
    rows: tuple[Ranked, ...]

    @property
    def top_slots_correct(self) -> int:
        """Draws where the degraded machines took the first places, all of them."""
        found = 0
        for seed in range(self.seeds):
            top = {
                row.machine_id
                for row in self.rows
                if row.seed == seed and row.rank <= len(self.degraded)
            }
            if top == set(self.degraded):
                found += 1
        return found

    @property
    def first_place_correct(self) -> int:
        return sum(1 for row in self.rows if row.rank == 1 and row.degraded)

    def mean_rank(self, *, degraded: bool) -> float:
        ranks = [row.rank for row in self.rows if row.degraded is degraded]
        return sum(ranks) / len(ranks)

    def mean_rate(self, *, degraded: bool) -> float:
        rates = [
            row.failures_per_100_days
            for row in self.rows
            if row.degraded is degraded and row.failures_per_100_days is not None
        ]
        return sum(rates) / len(rates)


def rank_one(plan: HistoryPlan, seed: int) -> tuple[MachineHealth, ...]:
    """One draw of the plan, assessed and ordered by history.

    `observed_from` is the plan's own start rather than the earliest record, so
    every machine is counted over the same span even in a draw where one of them
    happens to have no orders until March.
    """
    history = SyntheticHistory(plan, seed=seed)
    readings = assess(
        plan.machine_ids,
        repairs=history.repairs(),
        pm_tasks=history.pm_tasks(),
        findings=(),
        now=plan.ends_at,
        observed_from=plan.starts_at,
    )
    return by_history(readings)


def measure(plan: HistoryPlan, *, seeds: int) -> Measurement:
    degraded = plan.degraded
    rows: list[Ranked] = []
    for seed in range(seeds):
        for rank, reading in enumerate(rank_one(plan, seed), start=1):
            rows.append(
                Ranked(
                    seed=seed,
                    machine_id=reading.machine_id,
                    rank=rank,
                    degraded=reading.machine_id in degraded,
                    failures=reading.history.failures,
                    failures_per_100_days=reading.history.failures_per_100_days,
                    days_since_last_failure=reading.history.days_since_last_failure,
                    pm_overdue=reading.history.pm_overdue,
                    false_alarms=reading.history.false_alarms,
                )
            )
    return Measurement(
        plan=plan.name,
        seeds=seeds,
        machines=len(plan.machines),
        degraded=tuple(sorted(degraded)),
        rows=tuple(rows),
    )


def _machine_table(result: Measurement) -> str:
    lines = [
        f"{'machine':10} {'degraded':>9} {'mean rank':>10} {'mean rate':>10} "
        f"{'first':>6} {'PM over':>8} {'no fault':>9}"
    ]
    lines.append("-" * len(lines[0]))
    machines = sorted({row.machine_id for row in result.rows})
    for machine in machines:
        rows = [row for row in result.rows if row.machine_id == machine]
        degraded = rows[0].degraded
        mean_rank = sum(row.rank for row in rows) / len(rows)
        rates = [r.failures_per_100_days for r in rows if r.failures_per_100_days is not None]
        mean_rate = sum(rates) / len(rates) if rates else float("nan")
        firsts = sum(1 for row in rows if row.rank == 1)
        pm_over = sum(row.pm_overdue for row in rows) / len(rows)
        alarms = sum(row.false_alarms for row in rows) / len(rows)
        lines.append(
            f"{machine:10} {'yes' if degraded else 'no':>9} {mean_rank:>10.2f} "
            f"{mean_rate:>10.2f} {firsts:>6} {pm_over:>8.2f} {alarms:>9.2f}"
        )
    return "\n".join(lines)


def main() -> int:
    plan = LINE_A_ONE_YEAR
    print(f"measured {datetime.now().astimezone().date().isoformat()}")
    print(
        f"plan {plan.name}, {SEEDS} seeds, {len(plan.machines)} machines, "
        f"{plan.span.days} days of history ending {plan.ends_at.date().isoformat()}\n"
    )

    result = measure(plan, seeds=SEEDS)
    degraded = len(result.degraded)

    print(_machine_table(result))
    print()
    print(
        f"the {degraded} degraded machines took the top {degraded} places in "
        f"{result.top_slots_correct} of {result.seeds} draws"
    )
    print(
        f"first place went to a degraded machine in {result.first_place_correct} of {result.seeds}"
    )
    print(
        f"mean rank {result.mean_rank(degraded=True):.2f} degraded against "
        f"{result.mean_rank(degraded=False):.2f} healthy, over {result.machines} machines"
    )
    print(
        f"mean failure rate {result.mean_rate(degraded=True):.2f} against "
        f"{result.mean_rate(degraded=False):.2f} per 100 days"
    )
    print(
        "\nNothing above measures the other half of a health reading. A history\n"
        "generator writes closed work orders and not signals, so there are no open\n"
        "Findings to rank and none were invented; prediction is measured against its\n"
        "own ground truth in docs/prediction-baseline.md (ADR-020, ADR-076 §6).\n"
        "\n"
        "Every parameter of the plan is invented. No plant history has been seen."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

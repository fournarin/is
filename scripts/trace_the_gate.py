"""The fifth requirement, round by round: urgent work first when the shift is
busy, scheduled maintenance released when it is quiet.

Run by hand:

    PYTHONPATH=. uv run python scripts/trace_the_gate.py

The comparison (`compare_policies.py`) runs on failures alone, so it cannot show
the half of the brief about releasing lower-priority work. This runs the shipped
3C (`dispatch()` behind the simulator) on the same morning shift with the PM
tasks `plant.yaml` declares for the line, twice: falling due at 06:00, in the
quiet stretch, and at 12:00, in the busy one. It writes what every round saw and
decided - the load ratio, the band, what it placed, what it held back and why.

Two things are checked on every seed of both, and the script exits non-zero if
either is false: no scheduled job is placed in a round that is not light, and no
condition job is held in a round that is light.

The PM tasks are priced from `fallback_minutes`, as the simulator prices
everything, and their downtime is not counted: the simulator does not model a
planned stop.

The shift runs with **one technician**. Since ADR-124 a stopped machine does not
fail again, and with the scenario's three people the "busy" stretch never leaves
the light band - the trace then shows a gate with nothing to hold, which is no
evidence for the half of the brief about holding work back.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from pdm.contracts import PMTask, PMTaskRef, SymptomCode
from pdm.dispatch.domain import Band, Round
from pdm.platform.config import Config, load_config
from pdm.sim import SimScenario, run
from pdm.sim.domain import TicketRecord
from pdm.sim.scenarios import LINE_A_ONE_SHIFT
from scripts.compare_policies import GateAndScore, with_roster

OUT = Path("docs/results/gate-trace.md")
SEEDS = range(20)
TRACED_SEED = 0
TECHNICIANS = 1
ARMS = (
    ("due at 06:00, the quiet stretch", timedelta(0)),
    ("due at 12:00, the busy stretch", timedelta(hours=6)),
)

_BAND_TH = {Band.LIGHT: "เบา", Band.NORMAL: "ปกติ", Band.HEAVY: "หนัก", Band.NO_CAPACITY: "ไม่มีกำลังคน"}


def _scenario(config: Config, due_after: timedelta) -> SimScenario:
    due = LINE_A_ONE_SHIFT.starts_at + due_after
    tasks = tuple(
        PMTask(
            pm_task_ref=PMTaskRef(task.pm_task_ref),
            machine_id=task.machine_id,
            symptom_code=SymptomCode(task.symptom_code),
            interval=timedelta(hours=task.interval_hours),
            due_at=due,
        )
        for task in config.plant.pm_tasks
        if config.line_of(task.machine_id).line_id == LINE_A_ONE_SHIFT.line_id
    )
    return with_roster(LINE_A_ONE_SHIFT, TECHNICIANS).model_copy(update={"maintenance": tasks})


@dataclass
class Arm:
    name: str
    violations: list[str] = field(default_factory=list)
    started: list[int] = field(default_factory=list)
    rounds: list[Round] = field(default_factory=list)
    tickets: tuple[TicketRecord, ...] = ()


def _is_pm(ref: str) -> bool:
    return ref.startswith("PM-")


def _play(config: Config, name: str, due_after: timedelta) -> Arm:
    scenario = _scenario(config, due_after)
    arm = Arm(name)
    for seed in SEEDS:
        policy = GateAndScore(config)
        result = run(scenario, policy=policy, config=config, seed=seed)
        for decided in policy.rounds:
            if decided.band is not Band.LIGHT and any(_is_pm(one.ref) for one in decided.placed):
                arm.violations.append(
                    f"seed {seed} {decided.at:%H:%M}: PM placed while {decided.band}"
                )
            if decided.band is Band.LIGHT and any(not _is_pm(one.ref) for one in decided.held):
                arm.violations.append(
                    f"seed {seed} {decided.at:%H:%M}: condition work held while light"
                )
        arm.started.append(
            sum(1 for record in result.tickets if _is_pm(record.ref) and record.started_at)
        )
        if seed == TRACED_SEED:
            arm.rounds, arm.tickets = policy.rounds, result.tickets
    return arm


def _section(arm: Arm, pm_count: int) -> list[str]:
    rows = []
    for decided in arm.rounds:
        ratio = "-" if decided.load_ratio is None else f"{decided.load_ratio:.0%}"
        rows.append(
            f"| {decided.at:%H:%M} | {ratio} | {_BAND_TH[decided.band]} | "
            f"{sum(not _is_pm(one.ref) for one in decided.placed)} | "
            f"{sum(_is_pm(one.ref) for one in decided.placed)} | "
            f"{sum(not _is_pm(one.ref) for one in decided.held)} | "
            f"{sum(_is_pm(one.ref) for one in decided.held)} |"
        )
    reasons = sorted({one.why for decided in arm.rounds for one in decided.held if _is_pm(one.ref)})
    return [
        f"## PM {arm.name}",
        "",
        f"- scheduled work placed in a round that was not light, seeds 0-{SEEDS[-1]}: "
        f"**{sum('PM placed' in v for v in arm.violations)}**",
        f"- condition work held in a round that was light: "
        f"**{sum('condition' in v for v in arm.violations)}**",
        f"- PM jobs started per run: {min(arm.started)} to {max(arm.started)} of {pm_count}",
        "",
        f"### Every round of seed {TRACED_SEED}",
        "",
        "| time | load | band | condition placed | PM placed | condition held | PM held |",
        "|---|---:|---|---:|---:|---:|---:|",
        *rows,
        "",
        f"### The PM jobs of seed {TRACED_SEED}",
        "",
        "| job | machine | due | started | finished |",
        "|---|---|---|---|---|",
        *(
            f"| {record.ref} | {record.machine_id} | {record.created_at:%H:%M} | "
            f"{'not started' if record.started_at is None else f'{record.started_at:%H:%M}'} | "
            f"{'-' if record.finished_at is None else f'{record.finished_at:%H:%M}'} |"
            for record in arm.tickets
            if _is_pm(record.ref)
        ),
        "",
        "### What a held PM job says, verbatim",
        "",
        *(f"- {reason}" for reason in reasons),
        *([] if reasons else ["- (none held)"]),
        "",
    ]


def main() -> int:
    config = load_config(Path("config"))
    pm_count = len(_scenario(config, timedelta(0)).maintenance)
    if not pm_count:
        print("no PM tasks on this line in plant.yaml; nothing to trace")
        return 1

    arms = [_play(config, name, due_after) for name, due_after in ARMS]
    load = config.policy.load
    lines = [
        "# The gate, round by round",
        "",
        "**Generated by `scripts/trace_the_gate.py`. Do not edit by hand.**",
        "",
        f"Scenario `{LINE_A_ONE_SHIFT.name}` (quiet 06:00-10:00, busy 10:00-14:00) with "
        f"{TECHNICIANS} technician{'s' if TECHNICIANS != 1 else ''} (ADR-124: with the "
        "scenario's three the busy stretch never leaves the light band) and "
        f"the {pm_count} PM tasks `plant.yaml` declares for its line, shipped 3C "
        f"(`dispatch()`). Light below {load.light_below:.0%}, heavy at "
        f"{load.heavy_at_or_above:.0%} or above. A round runs every five minutes and "
        "only when something is waiting; `placed` is what the round assigned, and "
        "the simulator starts each technician's first placement.",
        "",
    ]
    for arm in arms:
        lines += _section(arm, pm_count)
    OUT.write_text("\n".join(lines))

    violations = [v for arm in arms for v in arm.violations]
    print(f"{len(violations)} violations; trace -> {OUT}")
    for violation in violations[:20]:
        print(f"  {violation}")
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())

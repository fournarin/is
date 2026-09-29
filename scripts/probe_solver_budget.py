"""What CP-SAT reaches under the shipped 5-second limit, against larger budgets.

Run by hand (takes about 25 minutes):

    PYTHONPATH=. uv run python scripts/probe_solver_budget.py

For queues of 10, 50 and 200 orders, the same model is solved under a 5 s
wall-clock limit (as shipped), deterministic budgets of 1, 5 and 20, and a 60 s
wall-clock limit, with one worker and seed 0. It prints the status, the
objective, the best bound CP-SAT proved, and wall and deterministic time.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from ortools.sat.python import cp_model

from pdm.contracts import SkillId, Technician, UserId
from pdm.dispatch import solver as planner
from pdm.platform.config import load_config
from scripts.measure_round_time import NOW, SKILLS, _queue

BUDGETS = (
    ("wall 5s (shipped)", {"max_time_in_seconds": 5.0}),
    ("deterministic 1", {"max_deterministic_time": 1.0}),
    ("deterministic 5", {"max_deterministic_time": 5.0}),
    ("deterministic 20", {"max_deterministic_time": 20.0}),
    ("wall 60s", {"max_time_in_seconds": 60.0}),
)


def main() -> int:
    config = load_config(Path("config"))
    print("| orders | technicians | budget | status | objective | proved bound | wall s | det |")
    print("|---:|---:|---|---|---:|---:|---:|---:|")
    for count, people in ((10, 3), (50, 3), (50, 8), (200, 3)):
        technicians = [
            Technician(user=UserId(f"t{n}"), skills=frozenset(SkillId(s) for s in SKILLS))
            for n in range(people)
        ]
        shift = planner._shift(
            _queue(count),
            technicians=technicians,
            assignments=[(person.user, 480) for person in technicians],
            config=config,
            now=NOW,
            shift_id=None,
            on_date=None,
        )
        if shift.jobs is None:
            continue
        for label, parameters in BUDGETS:
            built = planner._build(
                shift.jobs, available=shift.available, left=shift.left, horizon=shift.horizon
            )
            solver = cp_model.CpSolver()
            solver.parameters.num_workers = 1
            solver.parameters.random_seed = 0
            for name, value in parameters.items():
                setattr(solver.parameters, name, value)
            started = time.perf_counter()
            status = solver.solve(built.model)
            wall = time.perf_counter() - started
            print(
                f"| {count} | {people} | {label} | {solver.status_name(status)} | "
                f"{solver.objective_value:.0f} | {solver.best_objective_bound:.0f} | "
                f"{wall:.1f} | {solver.deterministic_time:.2f} |"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())

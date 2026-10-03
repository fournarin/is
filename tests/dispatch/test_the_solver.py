"""Layer 3's other half: CP-SAT over what the gate admitted (ADR-054).

A constraint model is the place in this system where code can look right, run,
and be wrong in a way no test catches unless somebody already knows the answer.
So the tests that matter here are the ones with an answer worked out by hand
before the model was written:

  * `TestTheOptimum::test_the_plan_is_the_one_computed_by_hand` fixes both start
    times of a two-job shift from arithmetic in its own docstring. Any change to
    the objective that still runs will fail it.
  * `TestTheOptimum::test_greedy_takes_the_bigger_job_and_the_solver_the_faster`
    is the whole claim of the slice: 3C ranks by what a job costs and 3D ranks
    by what a job costs *per minute it holds somebody*, and on this shift they
    disagree. If it ever passes trivially, 3D has stopped being different from
    3C and the column in `docs/results/` is measuring one policy twice.
  * `TestTheFallback` holds the behaviour the issue named: no answer in time
    means 3C's answer, never an empty plan.

The rest are the constraints, each asserted against a shift that would violate
it if the constraint were missing rather than against a shift that happens to
satisfy it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

import pytest

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    FindingRef,
    MachineId,
    Severity,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.dispatch import Queued, Round, dispatch, schedule
from pdm.platform.config import load_config

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
CONFIG = load_config(Path("config"))

# From plant.yaml, and used for their geometry rather than their names. With a
# takt of one unit a minute: st-01 has twenty units of buffer and no bottleneck
# multiplier, so a repair there costs (minutes - 20); st-03 has no buffer and a
# multiplier of three, so it costs minutes x 3.
BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")

MORNING = ShiftId("morning")
MECHANICAL = SkillId("robot_mechanical")
ELECTRICAL = SkillId("electrical")

ANA = UserId("tech-ana")
BEN = UserId("tech-ben")


def _order(
    *,
    machine_id: MachineId = BUFFERED,
    severity: Severity = Severity.MEDIUM,
    minutes: int = 60,
    skill: SkillId | None = MECHANICAL,
    people: int = 1,
    status: WorkOrderStatus = WorkOrderStatus.QUEUED,
    assignees: tuple[UserId, ...] = (),
) -> WorkOrder:
    return WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=FindingRef(f"F-{machine_id}"),
        machine_id=machine_id,
        severity=severity,
        estimated_minutes=minutes,
        required_skill=skill,
        required_technicians=people,
        reason="because a test said so",
        status=status,
        assignees=tuple(
            Assignee(user=user, role=AssigneeRole.PRIMARY if index == 0 else AssigneeRole.HELPER)
            for index, user in enumerate(assignees)
        ),
    )


def _queued(ref: str, order: WorkOrder, *, age_minutes: int = 0) -> Queued:
    return Queued(ref=ref, order=order, created_at=NOW - timedelta(minutes=age_minutes))


def _people(
    *users: UserId, skills: frozenset[SkillId] = frozenset({MECHANICAL})
) -> list[Technician]:
    return [Technician(user=user, skills=skills) for user in users]


def _planned(
    queue: list[Queued],
    *,
    technicians: list[Technician],
    roster: list[tuple[UserId, int]],
    seconds: float | None = None,
) -> Round:
    return schedule(
        queue,
        technicians=technicians,
        assignments=roster,
        config=CONFIG,
        now=NOW,
        shift_id=MORNING,
        seconds=seconds,
    )


def _ranked(
    queue: list[Queued],
    *,
    technicians: list[Technician],
    roster: list[tuple[UserId, int]],
) -> Round:
    return dispatch(
        queue,
        technicians=technicians,
        assignments=roster,
        config=CONFIG,
        now=NOW,
        shift_id=MORNING,
    )


# ── the shift whose answer is known before the model runs ──────────────────
#
# One technician with 300 minutes. Two jobs, both medium severity, both raised
# at the same moment, so nothing but the downtime term separates them:
#
#   BIG   120 minutes at st-01  ->  (120 - 20) x 1 = 100 units,  0.833 per minute
#   FAST   30 minutes at st-03  ->   30 x 3        =  90 units,  3.000 per minute
#
# Objective is production lost to delay, so the cost of an ordering is the sum
# over jobs of (rate x the minute it starts):
#
#   FAST then BIG:  3.000 x 0  +  0.833 x 30  =  25.0     <- optimal
#   BIG then FAST:  0.833 x 0  +  3.000 x 120 = 360.0
#
# The 3C score sees the *totals*, where BIG is the larger number, so the two
# policies disagree - which is the point of having 3D at all.


def _the_known_shift() -> tuple[list[Queued], list[Technician], list[tuple[UserId, int]]]:
    queue = [
        _queued("WO-BIG", _order(machine_id=BUFFERED, minutes=120)),
        _queued("WO-FAST", _order(machine_id=BOTTLENECK, minutes=30)),
    ]
    return queue, _people(ANA), [(ANA, 300)]


class TestTheOptimum:
    def test_the_plan_is_the_one_computed_by_hand(self) -> None:
        """25.0 against 360.0, and the arithmetic is in the comment above."""
        queue, people, roster = self._shift()
        plan = _planned(queue, technicians=people, roster=roster)

        starts = {one.ref: one.starts_in_minutes for one in plan.placed}
        assert starts == {"WO-FAST": 0, "WO-BIG": 30}

    def test_greedy_takes_the_bigger_job_and_the_solver_the_faster(self) -> None:
        """The claim the slice exists to test, in one shift.

        3C ranks by what a job costs the line; 3D ranks by what it costs per
        minute it holds a technician. Where the two disagree, the second is the
        one that loses less production, and this asserts they disagree rather
        than assuming it.
        """
        queue, people, roster = self._shift()

        greedy = _ranked(queue, technicians=people, roster=roster)
        planned = _planned(queue, technicians=people, roster=roster)

        assert [one.ref for one in greedy.placed] == ["WO-BIG", "WO-FAST"]
        assert [one.ref for one in planned.placed] == ["WO-FAST", "WO-BIG"]

    def test_the_plan_says_when_and_the_score_still_says_why(self) -> None:
        """ADR-005 survives the change of policy: the reason on the ticket still
        opens the five terms, with the plan's part in front of it - in Thai and
        without a minute in it (ADR-093, ADR-126, ADR-128)."""
        queue, people, roster = self._shift()
        plan = _planned(queue, technicians=people, roster=roster)

        first = plan.placed[0]
        assert first.priority_reason.startswith("จัดตามแผนทั้งกะ · ")
        assert first.terms.downtime > 0
        assert first.facts.downtime_units > 0

    def test_dispatch_leaves_the_start_time_empty_and_means_it(self) -> None:
        """A ranked queue says who a job belongs to and nothing about when it
        begins. Zero there would be a promise greedy never made."""
        queue, people, roster = self._shift()
        greedy = _ranked(queue, technicians=people, roster=roster)
        assert all(one.starts_in_minutes is None for one in greedy.placed)

    @staticmethod
    def _shift() -> tuple[list[Queued], list[Technician], list[tuple[UserId, int]]]:
        return _the_known_shift()


class TestItIsReplayable:
    def test_the_same_shift_twice_gives_the_same_plan(self) -> None:
        """CP-SAT's portfolio is parallel and the first worker to finish wins, so
        this fails the moment `num_workers` or the seed stops being fixed - and
        it would fail by making every figure in `docs/results/` irreproducible."""
        queue, people, roster = _the_known_shift()
        once = _planned(queue, technicians=people, roster=roster)
        twice = _planned(queue, technicians=people, roster=roster)
        assert once == twice

    def test_the_queue_order_does_not_change_the_plan(self) -> None:
        """A round that answered differently because the database returned rows
        in another order would be irreproducible in a way nothing reports."""
        queue, people, roster = _the_known_shift()
        forwards = _planned(queue, technicians=people, roster=roster)
        backwards = _planned(list(reversed(queue)), technicians=people, roster=roster)
        assert [one.ref for one in forwards.placed] == [one.ref for one in backwards.placed]


class TestTheFallback:
    def test_a_solver_with_no_time_returns_the_ranked_queue(self) -> None:
        """The issue names this case: no answer in time means 3C's answer.

        A round that returned nothing would leave a shift with a queue nobody is
        working, which is strictly worse than a good-enough ranking.
        """
        queue, people, roster = _the_known_shift()
        starved = _planned(queue, technicians=people, roster=roster, seconds=1e-9)
        greedy = _ranked(queue, technicians=people, roster=roster)
        assert starved == greedy

    def test_the_fallback_is_not_what_a_normal_round_returns(self) -> None:
        """Otherwise the test above would pass against a solver that never ran."""
        queue, people, roster = _the_known_shift()
        planned = _planned(queue, technicians=people, roster=roster)
        greedy = _ranked(queue, technicians=people, roster=roster)
        assert planned != greedy

    def test_a_shift_with_nobody_on_it_still_says_so(self) -> None:
        """No capacity is not a solver problem, and the sentence that says which
        kind of nothing this is comes from the gate (ADR-045 §3)."""
        queue = [_queued("WO-1", _order())]
        plan = schedule(
            queue,
            technicians=[],
            assignments=[],
            config=CONFIG,
            now=NOW,
            shift_id=MORNING,
        )
        assert plan.band.value == "no_capacity"
        assert plan.placed == ()
        assert plan.held


class TestTheConstraints:
    def test_nobody_is_under_two_machines_at_once(self) -> None:
        """ADR-047. Three jobs that fit the shift's minutes but not the clock."""
        queue = [
            _queued("WO-1", _order(minutes=60)),
            _queued("WO-2", _order(minutes=60)),
            _queued("WO-3", _order(minutes=60)),
        ]
        plan = _planned(queue, technicians=_people(ANA), roster=[(ANA, 300)])

        spans = sorted(
            (one.starts_in_minutes or 0, (one.starts_in_minutes or 0) + 60) for one in plan.placed
        )
        for (_, ends), (begins, _) in pairwise(spans):
            assert ends <= begins, f"two jobs overlap: {spans}"

    def test_a_job_goes_to_somebody_who_holds_its_skill(self) -> None:
        queue = [
            _queued("WO-MECH", _order(skill=MECHANICAL, minutes=30)),
            _queued("WO-ELEC", _order(skill=ELECTRICAL, minutes=30)),
        ]
        people = [
            Technician(user=ANA, skills=frozenset({MECHANICAL})),
            Technician(user=BEN, skills=frozenset({ELECTRICAL})),
        ]
        plan = _planned(queue, technicians=people, roster=[(ANA, 300), (BEN, 300)])

        who = {one.ref: tuple(a.user for a in one.assignees) for one in plan.placed}
        assert who["WO-MECH"] == (ANA,)
        assert who["WO-ELEC"] == (BEN,)

    def test_a_job_nobody_holds_the_skill_for_is_not_placed(self) -> None:
        queue = [_queued("WO-ELEC", _order(skill=ELECTRICAL, minutes=30))]
        plan = _planned(
            queue,
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            roster=[(ANA, 300)],
        )
        assert plan.placed == ()

    def test_a_two_person_job_gets_two_people_or_nobody(self) -> None:
        """ADR-025: half a two-person job spends one shift achieving nothing."""
        queue = [_queued("WO-PAIR", _order(minutes=60, people=2))]

        alone = _planned(queue, technicians=_people(ANA), roster=[(ANA, 300)])
        assert alone.placed == ()

        together = _planned(queue, technicians=_people(ANA, BEN), roster=[(ANA, 300), (BEN, 300)])
        assert len(together.placed) == 1
        assert len(together.placed[0].assignees) == 2
        assert [one.role for one in together.placed[0].assignees] == [
            AssigneeRole.PRIMARY,
            AssigneeRole.HELPER,
        ]

    def test_nobody_is_given_minutes_the_shift_does_not_have(self) -> None:
        """The person-minute capacity, in the stronger form the model uses: a
        job must *finish* inside what its technician has left.

        High severity on purpose. 120 person-minutes against 90 available is a
        ratio of 133%, so the gate is in its heavy band and would hold medium
        work before the solver ever saw it - which is the gate doing its job and
        would make this a test of ADR-011 rather than of the capacity constraint.
        """
        queue = [
            _queued("WO-1", _order(minutes=60, severity=Severity.HIGH)),
            _queued("WO-2", _order(minutes=60, severity=Severity.HIGH)),
        ]
        plan = _planned(queue, technicians=_people(ANA), roster=[(ANA, 90)])

        assert len(plan.placed) == 1, "90 minutes cannot hold two hour-long jobs"
        assert len(plan.unassigned) == 1
        assert plan.placed[0].starts_in_minutes == 0

    def test_work_already_accepted_is_not_replanned(self) -> None:
        """ADR-045 §4. It consumes its assignee's capacity and is never moved."""
        queue = [
            _queued(
                "WO-MINE", _order(minutes=60, status=WorkOrderStatus.IN_PROGRESS, assignees=(ANA,))
            ),
            _queued("WO-NEW", _order(minutes=60)),
        ]
        plan = _planned(queue, technicians=_people(ANA), roster=[(ANA, 300)])

        assert "WO-MINE" not in {one.ref for one in plan.placed}
        assert "WO-NEW" in {one.ref for one in plan.placed}


class TestTheGateIsUntouched:
    def test_the_solver_never_sees_what_the_gate_held(self) -> None:
        """ADR-011 and the issue both say the gate is a separate stage. A heavy
        shift holds its medium work whichever policy ranks the rest."""
        queue = [
            _queued("WO-HIGH", _order(severity=Severity.HIGH, minutes=60)),
            _queued("WO-MED", _order(severity=Severity.MEDIUM, minutes=60)),
            _queued("WO-LOW", _order(severity=Severity.LOW, minutes=60)),
        ]
        # 180 person-minutes against 180 available is a ratio of 1.0: heavy.
        people, roster = _people(ANA), [(ANA, 180)]

        greedy = _ranked(queue, technicians=people, roster=roster)
        planned = _planned(queue, technicians=people, roster=roster)

        assert greedy.band.value == "heavy"
        assert planned.band == greedy.band
        assert {one.ref for one in planned.held} == {one.ref for one in greedy.held}
        assert {one.ref for one in planned.held} == {"WO-MED", "WO-LOW"}

    def test_the_load_numbers_are_the_gates_and_not_the_solvers(self) -> None:
        queue, people, roster = _the_known_shift()
        greedy = _ranked(queue, technicians=people, roster=roster)
        planned = _planned(queue, technicians=people, roster=roster)

        assert planned.load_ratio == greedy.load_ratio
        assert planned.capacity_minutes == greedy.capacity_minutes
        assert planned.committed_minutes == greedy.committed_minutes


class TestWhatItCosts:
    @pytest.mark.parametrize("size", [4, 8, 12])
    def test_a_round_this_size_finishes_well_inside_its_limit(self, size: int) -> None:
        """Not a benchmark - a guard. A model that stopped being solvable in the
        round's budget would silently become the fallback on every shift, and the
        comparison would report 3C's numbers under 3D's name."""
        queue = [_queued(f"WO-{index}", _order(minutes=30 + index * 5)) for index in range(size)]
        plan = _planned(
            queue,
            technicians=_people(ANA, BEN),
            roster=[(ANA, 480), (BEN, 480)],
            seconds=CONFIG.policy.dispatch.solver_seconds,
        )
        greedy = _ranked(queue, technicians=_people(ANA, BEN), roster=[(ANA, 480), (BEN, 480)])
        assert plan != greedy or all(one.starts_in_minutes is not None for one in plan.placed), (
            "the round fell back, so the model did not solve in its budget"
        )


class TestItStartsFromGreedy:
    """ADR-110: 3C's round is the solver's first solution, so 3D is never worse
    than greedy, even when the budget runs out almost at once."""

    @staticmethod
    def _objective(*, fixed: bool, budget: float) -> float:
        from ortools.sat.python import cp_model

        from pdm.dispatch.solver import _build, _shift, _start_from

        machines = (BUFFERED, MachineId("MC-004"), BOTTLENECK, MachineId("MC-018"))
        queue = [
            _queued(
                f"WO-{index:02d}",
                _order(
                    machine_id=machines[index % 4],
                    severity=Severity.HIGH,
                    minutes=30 + 15 * (index % 5),
                    skill=None,
                ),
                age_minutes=index,
            )
            for index in range(30)
        ]
        people = _people(ANA, BEN)
        shift = _shift(
            queue,
            technicians=people,
            assignments=[(ANA, 480), (BEN, 480)],
            config=CONFIG,
            now=NOW,
            shift_id=MORNING,
            on_date=None,
        )
        assert shift.jobs is not None
        built = _build(
            shift.jobs, available=shift.available, left=shift.left, horizon=shift.horizon
        )
        _start_from(built, shift.ranked)
        solver = cp_model.CpSolver()
        solver.parameters.num_workers = 1
        solver.parameters.random_seed = 0
        solver.parameters.max_deterministic_time = budget
        solver.parameters.fix_variables_to_their_hinted_value = fixed
        status = solver.solve(built.model)
        assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)
        return solver.objective_value

    def test_the_hint_is_a_complete_feasible_schedule(self) -> None:
        assert self._objective(fixed=True, budget=5.0) > 0

    def test_a_tiny_budget_is_still_no_worse_than_greedy(self) -> None:
        greedy = self._objective(fixed=True, budget=5.0)

        assert self._objective(fixed=False, budget=0.01) <= greedy

    def test_the_shipped_budget_improves_on_it_here(self) -> None:
        greedy = self._objective(fixed=True, budget=5.0)

        assert self._objective(fixed=False, budget=CONFIG.policy.dispatch.solver_budget) < greedy

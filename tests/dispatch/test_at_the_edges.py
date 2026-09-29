"""The dispatch round at its edges: nobody on shift, boundaries hit exactly,
a flood of work, a job bigger than anybody's shift.

Each test states an invariant that must hold whatever the inputs: nobody placed
twice, nobody given more minutes than they have, no division by zero, and the
same round for the same inputs.
"""

from __future__ import annotations

from collections import Counter

from pdm.contracts import MachineId, Severity, UserId, WorkOrderOrigin, WorkOrderStatus
from pdm.dispatch.domain import Band, Round
from pdm.dispatch.solver import schedule
from tests.dispatch.test_gate_and_score import (
    ANA,
    BEN,
    BOTTLENECK,
    BUFFERED,
    CONFIG,
    FAN,
    NOW,
    _order,
    _people,
    _queued,
    _roster,
    _round,
)

MACHINES = (BUFFERED, MachineId("MC-004"), BOTTLENECK, FAN)
SEVERITIES = (Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def _flood(count: int) -> list:  # type: ignore[type-arg]
    return [
        _queued(
            f"WO-{index:03d}",
            _order(
                machine_id=MACHINES[index % len(MACHINES)],
                severity=SEVERITIES[index % len(SEVERITIES)],
                minutes=30 + 15 * (index % 5),
            ),
            age_minutes=index,
        )
        for index in range(count)
    ]


def _respects_the_roster(result: Round, roster: list[tuple[UserId, int]], queue: list) -> None:  # type: ignore[type-arg]
    minutes_of = {item.ref: item.order.estimated_minutes for item in queue}
    refs = [placement.ref for placement in result.placed]
    assert len(refs) == len(set(refs)), "a job was placed twice"
    minutes: Counter[UserId] = Counter()
    for placement in result.placed:
        for assignee in placement.assignees:
            minutes[assignee.user] += minutes_of[placement.ref]
    for user, available in roster:
        assert minutes[user] <= available, f"{user} given {minutes[user]} of {available} minutes"


class TestNobodyToGiveItTo:
    def test_no_technicians_places_nothing_and_says_why(self) -> None:
        result = _round(_flood(5), technicians=[], roster=[])

        assert result.placed == ()
        assert result.load_ratio is None
        assert result.band is Band.NO_CAPACITY
        assert result.summary

    def test_a_technician_with_no_minutes_left_is_not_given_work(self) -> None:
        result = _round(_flood(3), technicians=_people(ANA), roster=_roster((ANA, 0)))

        assert result.placed == ()


class TestTheBoundaries:
    """Light is below 0.5 and heavy is 0.8 or above (policy.yaml), exactly."""

    @staticmethod
    def _at(ratio: float) -> Round:
        # Every open order counts towards the load, the waiting one included.
        committed = _queued(
            "WO-busy",
            _order(
                minutes=int(ratio * 100) - 10, assignees=(BEN,), status=WorkOrderStatus.ASSIGNED
            ),
        )
        waiting = _queued("WO-new", _order(severity=Severity.LOW, minutes=10))
        return _round(
            [committed, waiting],
            technicians=_people(ANA, BEN),
            roster=_roster((ANA, 50), (BEN, 50)),
        )

    def test_exactly_half_is_normal_not_light(self) -> None:
        result = self._at(0.5)

        assert result.load_ratio == 0.5
        assert result.band is Band.NORMAL

    def test_exactly_eighty_percent_is_heavy(self) -> None:
        result = self._at(0.8)

        assert result.load_ratio == 0.8
        assert result.band is Band.HEAVY
        assert "WO-new" in {held.ref for held in result.held}


class TestAFlood:
    def test_fifty_jobs_at_once_respect_every_technician_s_minutes(self) -> None:
        roster = _roster((ANA, 240), (BEN, 120))
        queue = _flood(50)
        result = _round(queue, technicians=_people(ANA, BEN), roster=roster)

        _respects_the_roster(result, roster, queue)
        assert result.placed

    def test_the_planned_round_respects_them_too(self) -> None:
        roster = _roster((ANA, 240), (BEN, 120))
        queue = _flood(50)
        result = schedule(
            queue,
            technicians=_people(ANA, BEN),
            assignments=roster,
            config=CONFIG,
            now=NOW,
            seconds=5.0,
        )

        _respects_the_roster(result, roster, queue)


class TestAJobBiggerThanTheShift:
    def test_it_is_not_placed_and_the_round_says_so(self) -> None:
        huge = _queued("WO-huge", _order(minutes=600, severity=Severity.CRITICAL))
        result = _round([huge], technicians=_people(ANA), roster=_roster((ANA, 480)))

        assert "WO-huge" not in {placement.ref for placement in result.placed}
        assert "WO-huge" in {one.ref for one in (*result.unassigned, *result.held)}


class TestTheSameRoundForTheSameInputs:
    def test_dispatch_is_a_function_of_its_inputs(self) -> None:
        roster = _roster((ANA, 240), (BEN, 240))
        first = _round(_flood(30), technicians=_people(ANA, BEN), roster=roster)
        second = _round(_flood(30), technicians=_people(ANA, BEN), roster=roster)

        assert first == second


class TestScheduledWorkAtTheEdge:
    """ADR-107. The ceiling on released PM work is checked before a job is added,
    so the job that crosses it is released. Pinned here, and named, because it
    lets one long PM job take a quiet shift into the heavy band. Changing it
    changes the policy the comparison measured, which is the owner's call."""

    def test_the_job_that_crosses_the_ceiling_is_released(self) -> None:
        pm = _queued(
            "WO-pm",
            _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=90, skill=None),
        )
        result = _round([pm], technicians=_people(ANA), roster=_roster((ANA, 100)))

        assert "WO-pm" in {placement.ref for placement in result.placed}

    def test_the_next_one_is_held_with_the_load_it_reached(self) -> None:
        first = _queued(
            "WO-pm1",
            _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=60, skill=None),
        )
        second = _queued(
            "WO-pm2",
            _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=20, skill=None),
            age_minutes=1,
        )
        result = _round([first, second], technicians=_people(ANA), roster=_roster((ANA, 100)))

        (held,) = [one for one in result.held if one.ref in {"WO-pm1", "WO-pm2"}]
        assert "ถึง 60%" in held.why or "ถึง 20%" in held.why

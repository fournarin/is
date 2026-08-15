"""Layer 3's first half: the gate, the score, and the promise of replayability.

No database, and that is the point of the slice rather than a convenience. Slice
7 compares three policies over hundreds of scenarios in CI and Loop 6 replays
past decisions against different weights; both need this function to give the
same answer twice, which is invariant 10 and the reason `dispatch()` takes its
world as arguments.

Three tests here would each pass against a plausible wrong implementation, and
they are the ones worth reading:

  * `TestTheDowntimeTerm::test_a_bottleneck_outranks_a_buffered_station` fails
    the moment downtime becomes a per-line constant, which is what ADR-021 was
    written against and what a technician would spot on the first shift.
  * `TestTheGate::test_a_maintenance_backlog_does_not_make_a_shift_look_busy`
    fails if queued PM work counts as demand - the load numbers all still move,
    they just move the wrong way.
  * `TestLoadRatio::test_a_two_person_job_costs_the_shift_twice` fails if either
    side of the ratio is wall-clock minutes, which nothing else would report.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    FindingKind,
    FindingRef,
    MachineId,
    PMTaskRef,
    Severity,
    SkillId,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.dispatch import Band, Queued, Round, dispatch, load_ratio
from pdm.platform.config import load_config

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
CONFIG = load_config(Path("config"))

# From plant.yaml, and chosen for what they are rather than for their names:
# st-01 has twenty units of buffer, st-03 is the bottleneck with none.
BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")
FAN = MachineId("MC-018")

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
    origin: WorkOrderOrigin = WorkOrderOrigin.CONDITION,
    status: WorkOrderStatus = WorkOrderStatus.QUEUED,
    kind: FindingKind | None = None,
    eta: datetime | None = None,
    assignees: tuple[UserId, ...] = (),
) -> WorkOrder:
    condition = origin is WorkOrderOrigin.CONDITION
    return WorkOrder(
        origin=origin,
        # The contract refuses a condition order with no Finding behind it and a
        # scheduled one with no PM task, which is ADR-010 holding at the type
        # level rather than in a caller.
        finding_ref=FindingRef(f"F-{machine_id}") if condition else None,
        pm_task_ref=None if condition else PMTaskRef(f"PM-{machine_id}"),
        machine_id=machine_id,
        severity=severity,
        finding_kind=kind,
        eta=eta,
        eta_confidence=timedelta(hours=1) if eta else None,
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


def _roster(*pairs: tuple[UserId, int]) -> list[tuple[UserId, int]]:
    return list(pairs)


def _round(
    queue: list[Queued], *, technicians: list[Technician], roster: list[tuple[UserId, int]]
) -> Round:
    return dispatch(queue, technicians=technicians, assignments=roster, config=CONFIG, now=NOW)


class TestLoadRatio:
    def test_a_two_person_job_costs_the_shift_twice(self) -> None:
        """design.md 13.2: person-minutes on both sides. Counting a two-person
        hour as sixty minutes makes every shift containing one read emptier than
        it is, and the gate then releases more work than there are people."""
        queue = [_queued("WO-1", _order(minutes=60, people=2))]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 240), (BEN, 240))
        )

        assert result.committed_minutes == 120
        assert result.load_ratio == pytest.approx(120 / 480)

    def test_no_capacity_is_not_a_ratio_of_zero(self) -> None:
        """An empty roster read as zero load would release the whole queue to
        nobody; read as infinite load it would be right by accident."""
        queue = [_queued("WO-1", _order())]

        result = _round(queue, technicians=[], roster=_roster())

        assert result.load_ratio is None
        assert result.band is Band.NO_CAPACITY
        assert [held.ref for held in result.held] == ["WO-1"]
        assert result.placed == ()

    def test_the_helper_agrees_with_the_round(self) -> None:
        assert load_ratio(240, 480) == 0.5
        assert load_ratio(1, 0) is None


class TestTheGate:
    """ADR-011's three bands, which is the behaviour the advisor described most
    concretely: heavy means the important work first, light means release the
    secondary work."""

    def test_a_heavy_shift_releases_only_high_and_critical(self) -> None:
        taken = _order(minutes=200, status=WorkOrderStatus.ASSIGNED, assignees=(ANA,))
        queue = [
            _queued("WO-taken", taken),
            _queued("WO-low", _order(severity=Severity.LOW, minutes=30)),
            _queued("WO-high", _order(severity=Severity.HIGH, minutes=30)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 120), (BEN, 120))
        )

        assert result.band is Band.HEAVY
        assert [placed.ref for placed in result.placed] == ["WO-high"]
        assert [held.ref for held in result.held] == ["WO-low"]
        assert "108%" in result.held[0].why

    def test_a_normal_shift_holds_maintenance_but_releases_the_rest(self) -> None:
        queue = [
            _queued("WO-cond-1", _order(minutes=120)),
            _queued("WO-cond-2", _order(minutes=120)),
            _queued("WO-pm", _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 200), (BEN, 200))
        )

        assert result.band is Band.NORMAL
        assert {placed.ref for placed in result.placed} == {"WO-cond-1", "WO-cond-2"}
        assert [held.ref for held in result.held] == ["WO-pm"]
        assert "quiet shift" in result.held[0].why

    def test_a_quiet_shift_pulls_maintenance_forward(self) -> None:
        """The advisor's own words: when the load is light, let the secondary
        work through. Without `origin`, there would be nothing to release."""
        queue = [
            _queued("WO-cond", _order(minutes=60)),
            _queued("WO-pm", _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        assert result.band is Band.LIGHT
        assert {placed.ref for placed in result.placed} == {"WO-cond", "WO-pm"}
        assert result.held == ()

    def test_the_top_up_stops_at_the_light_boundary(self) -> None:
        """A quiet shift handed its entire maintenance backlog is a heavy shift
        one round later, and the work released last is the work most likely to be
        abandoned at handover."""
        queue = [_queued("WO-cond", _order(minutes=60))] + [
            _queued(
                f"WO-pm-{index}",
                _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=60),
                age_minutes=index,
            )
            for index in range(8)
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        released_pm = [placed.ref for placed in result.placed if placed.ref.startswith("WO-pm")]
        assert 0 < len(released_pm) < 8
        # 60 committed of 600 capacity, and the boundary is 50%: four PM jobs of
        # an hour take it to 300/600 and the fifth would cross.
        assert len(released_pm) == 4
        assert "as far as maintenance work is pulled forward" in result.held[0].why

    def test_a_maintenance_backlog_does_not_make_a_shift_look_busy(self) -> None:
        """The inversion this would have caused is the reason ADR-045 §2 exists:
        queued PM work counted as demand makes the shift read full, and the gate
        then holds back the condition work that actually has to happen."""
        backlog = [
            _queued(
                f"WO-pm-{index}",
                _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=120),
            )
            for index in range(6)
        ]
        queue = [_queued("WO-cond", _order(severity=Severity.LOW, minutes=30)), *backlog]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 240), (BEN, 240))
        )

        assert result.band is Band.LIGHT
        assert "WO-cond" in {placed.ref for placed in result.placed}


class TestTheDowntimeTerm:
    """ADR-021: the term that makes this a scheduler for a vehicle assembly line
    rather than for a generic factory."""

    def test_a_bottleneck_outranks_a_buffered_station(self) -> None:
        """Identical jobs, different stations. If this passes with downtime as a
        per-line constant, the test is wrong: st-01 has twenty units of buffer
        and st-03 is the bottleneck with none."""
        queue = [
            _queued("WO-buffered", _order(machine_id=BUFFERED, minutes=30)),
            _queued("WO-bottleneck", _order(machine_id=BOTTLENECK, minutes=30)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        assert [placed.ref for placed in result.placed] == ["WO-bottleneck", "WO-buffered"]
        by_ref = {placed.ref: placed.terms for placed in result.placed}
        # Thirty minutes at st-03 stops the line for all thirty and triples it:
        # ninety units. At st-01 the buffer absorbs twenty of the thirty, so ten
        # units are lost - cheaper by nine times, not free.
        assert by_ref["WO-bottleneck"].downtime == 1.0
        assert by_ref["WO-buffered"].downtime == pytest.approx(10 / 90)

    def test_a_repair_shorter_than_the_buffer_costs_the_line_nothing(self) -> None:
        """Twenty units at sixty seconds buys twenty minutes, so a fifteen-minute
        repair at st-01 never reaches the line at all."""
        queue = [
            _queued("WO-short", _order(machine_id=BUFFERED, minutes=15)),
            _queued("WO-long", _order(machine_id=BUFFERED, minutes=120)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        by_ref = {placed.ref: placed.terms for placed in result.placed}
        assert by_ref["WO-short"].downtime == 0.0
        assert by_ref["WO-long"].downtime == 1.0


class TestTheScore:
    def test_severity_is_normalised_against_critical(self) -> None:
        queue = [
            _queued("WO-low", _order(severity=Severity.LOW)),
            _queued("WO-critical", _order(severity=Severity.CRITICAL)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        by_ref = {placed.ref: placed.terms for placed in result.placed}
        assert by_ref["WO-low"].severity == 0.0
        assert by_ref["WO-critical"].severity == 1.0

    def test_an_order_naming_no_skill_scores_between_matched_and_unmatched(self) -> None:
        """ADR-041 leaves fallback-priced work without a skill on purpose. Scored
        as unmatchable it would sink to the bottom of every queue, which is
        exactly the long-tail work ADR-011 wants released on a quiet shift."""
        queue = [
            _queued("WO-matched", _order(skill=MECHANICAL)),
            _queued("WO-none", _order(skill=None)),
            _queued("WO-unmatched", _order(skill=ELECTRICAL)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        by_ref = {placed.ref: placed.terms for placed in result.placed}
        assert by_ref["WO-matched"].skill_match == 1.0
        assert by_ref["WO-none"].skill_match == 0.5
        # The unmatched one is not placed at all: nobody on this shift holds the
        # skill it names, so the middle value is reachable only for the order
        # that names none.
        assert "WO-unmatched" in {item.ref for item in result.unassigned}

    def test_only_a_prediction_earns_the_eta_term(self) -> None:
        """`policy.yaml` says the weight applies to predicted work only. A
        detection loses nothing: what makes it urgent is already in severity and
        downtime, and giving it the maximum here would count that twice."""
        queue = [
            _queued("WO-detected", _order(kind=FindingKind.DETECTED)),
            _queued(
                "WO-soon",
                _order(kind=FindingKind.PREDICTED, eta=NOW + timedelta(hours=2)),
            ),
            _queued(
                "WO-later",
                _order(kind=FindingKind.PREDICTED, eta=NOW + timedelta(hours=20)),
            ),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 400), (BEN, 400))
        )

        by_ref = {placed.ref: placed.terms for placed in result.placed}
        assert by_ref["WO-detected"].eta_urgency == 0.0
        assert by_ref["WO-soon"].eta_urgency > by_ref["WO-later"].eta_urgency

    def test_waiting_is_relative_to_the_longest_wait_in_the_round(self) -> None:
        queue = [
            _queued("WO-old", _order(), age_minutes=180),
            _queued("WO-new", _order(), age_minutes=0),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        by_ref = {placed.ref: placed.terms for placed in result.placed}
        assert by_ref["WO-old"].waiting == 1.0
        assert by_ref["WO-new"].waiting == 0.0

    def test_every_placement_explains_itself(self) -> None:
        """ADR-005. A system that cannot say why this job comes first gets
        overruled and then abandoned."""
        queue = [_queued("WO-1", _order(machine_id=BOTTLENECK, severity=Severity.CRITICAL))]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        assert "severity is critical" in result.placed[0].priority_reason
        assert result.summary.startswith("the shift is at")


class TestAssignment:
    def test_the_skill_decides_who_gets_it(self) -> None:
        queue = [_queued("WO-1", _order(skill=ELECTRICAL))]
        people = [
            Technician(user=ANA, skills=frozenset({MECHANICAL})),
            Technician(user=BEN, skills=frozenset({ELECTRICAL})),
        ]

        result = _round(queue, technicians=people, roster=_roster((ANA, 300), (BEN, 300)))

        assert [assignee.user for assignee in result.placed[0].assignees] == [BEN]

    def test_a_two_person_job_with_one_person_free_is_not_half_assigned(self) -> None:
        """ADR-025. Half a two-person job cannot be started, and assigning half
        of it spends one person's shift to achieve nothing."""
        queue = [_queued("WO-1", _order(people=2, minutes=60))]

        result = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 300)))

        assert result.placed == ()
        assert [item.ref for item in result.unassigned] == ["WO-1"]
        assert "needs 2 technician(s)" in result.unassigned[0].why

    def test_a_two_person_job_takes_a_primary_and_a_helper(self) -> None:
        queue = [_queued("WO-1", _order(people=2, minutes=60))]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        roles = [assignee.role for assignee in result.placed[0].assignees]
        assert roles == [AssigneeRole.PRIMARY, AssigneeRole.HELPER]

    def test_the_only_person_with_the_skill_is_already_on_a_long_job(self) -> None:
        """A round does not re-plan work somebody has taken (design.md 6.2), but
        it is not free either: a technician three hours into a three-hour job has
        three hours fewer to give, and the shift can still read as normal because
        somebody else is idle - somebody who cannot do this work."""
        busy = _order(minutes=190, status=WorkOrderStatus.IN_PROGRESS, assignees=(ANA,))
        queue = [_queued("WO-busy", busy), _queued("WO-new", _order(minutes=60))]
        people = [
            Technician(user=ANA, skills=frozenset({MECHANICAL})),
            Technician(user=BEN, skills=frozenset({ELECTRICAL})),
        ]

        result = _round(queue, technicians=people, roster=_roster((ANA, 200), (BEN, 200)))

        assert result.band is Band.NORMAL
        assert [item.ref for item in result.unassigned] == ["WO-new"]
        assert "60 free minutes; 0 available" in result.unassigned[0].why

    def test_an_order_somebody_has_accepted_is_never_re_placed(self) -> None:
        queue = [
            _queued("WO-taken", _order(status=WorkOrderStatus.ASSIGNED, assignees=(ANA,))),
            _queued("WO-queued", _order()),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        assert [placed.ref for placed in result.placed] == ["WO-queued"]

    def test_nobody_free_is_reported_rather_than_dropped(self) -> None:
        """ "Nobody with electrical has time left this shift" is a fact a
        supervisor can act on within the shift; a ticket that simply did not
        appear is not."""
        queue = [_queued("WO-1", _order(skill=ELECTRICAL))]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        assert result.placed == ()
        assert "electrical" in result.unassigned[0].why


class TestInvariantTen:
    """`dispatch()` gives the same answer for the same inputs, and touches no
    database. Both halves are load-bearing for slice 7 and Loop 6."""

    def _mixed_queue(self) -> list[Queued]:
        return [
            _queued("WO-a", _order(machine_id=BOTTLENECK, severity=Severity.HIGH), age_minutes=40),
            _queued("WO-b", _order(machine_id=BUFFERED, severity=Severity.HIGH), age_minutes=40),
            _queued("WO-c", _order(machine_id=FAN, skill=None, severity=Severity.LOW)),
            _queued("WO-d", _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW)),
            _queued(
                "WO-e",
                _order(kind=FindingKind.PREDICTED, eta=NOW + timedelta(hours=3)),
                age_minutes=10,
            ),
        ]

    def test_the_same_inputs_give_the_same_round(self) -> None:
        first = _round(
            self._mixed_queue(),
            technicians=_people(ANA, BEN),
            roster=_roster((ANA, 300), (BEN, 300)),
        )
        second = _round(
            self._mixed_queue(),
            technicians=_people(ANA, BEN),
            roster=_roster((ANA, 300), (BEN, 300)),
        )

        assert first.model_dump() == second.model_dump()

    def test_equal_scores_are_broken_by_age_then_reference(self) -> None:
        """Two identical low-severity jobs on one station are common, and leaving
        their order to the sort's input would make the round unreplayable."""
        same = _order(severity=Severity.LOW)
        queue = [
            _queued("WO-z", same, age_minutes=10),
            _queued("WO-a", same, age_minutes=10),
            _queued("WO-older", same, age_minutes=90),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        # The oldest wins on the waiting term; the two identical ones fall back
        # to the reference.
        assert [placed.ref for placed in result.placed] == ["WO-older", "WO-a", "WO-z"]

    def test_the_order_of_the_input_queue_does_not_change_the_answer(self) -> None:
        queue = self._mixed_queue()
        forwards = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )
        backwards = _round(
            list(reversed(queue)),
            technicians=_people(BEN, ANA),
            roster=_roster((BEN, 300), (ANA, 300)),
        )

        assert [placed.ref for placed in forwards.placed] == [
            placed.ref for placed in backwards.placed
        ]

    def test_an_empty_queue_is_a_round_that_says_so(self) -> None:
        result = _round([], technicians=_people(ANA), roster=_roster((ANA, 300)))

        assert result.placed == ()
        assert result.load_ratio == 0.0
        assert result.band is Band.LIGHT

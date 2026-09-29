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

from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    FindingKind,
    FindingRef,
    MachineId,
    PMTaskRef,
    Severity,
    ShiftDefinition,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    shift_at,
)
from pdm.dispatch import Band, Queued, Round, dispatch, load_ratio
from pdm.dispatch.domain import _skill_match
from pdm.platform.config import load_config

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
CONFIG = load_config(Path("config"))

# From plant.yaml, and chosen for what they are rather than for their names:
# st-01 has twenty units of buffer, st-03 is the bottleneck with none.
BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")
FAN = MachineId("MC-018")

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


def _queued(ref: str, order: WorkOrder, *, age_minutes: int = 0, released: bool = False) -> Queued:
    return Queued(
        ref=ref,
        order=order,
        created_at=NOW - timedelta(minutes=age_minutes),
        released=released,
    )


def _people(
    *users: UserId, skills: frozenset[SkillId] = frozenset({MECHANICAL})
) -> list[Technician]:
    return [Technician(user=user, skills=skills) for user in users]


def _roster(*pairs: tuple[UserId, int]) -> list[tuple[UserId, int]]:
    return list(pairs)


def _round(
    queue: list[Queued],
    *,
    technicians: list[Technician],
    roster: list[tuple[UserId, int]],
    shift_id: ShiftId | None = MORNING,
) -> Round:
    """A round on the morning shift unless a test is about not having one.

    `shift_id=None` is not "unspecified": it is `shift_at` finding no shift at
    this hour, which the round reports differently from an empty roster
    (ADR-045 §3).
    """
    return dispatch(
        queue,
        technicians=technicians,
        assignments=roster,
        config=CONFIG,
        now=NOW,
        shift_id=shift_id,
    )


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


class TestNoCapacitySaysWhichKind:
    """ADR-045 §3: a round with no capacity says which of the ways it was.

    The behaviour is identical in each - nothing is admitted - so the sentence
    is the entire output of the round, and the three are acted on by different
    people. Told "nobody is rostered" about an hour the plant does not run, a
    supervisor goes looking for a roster that was never missing.
    """

    def test_an_hour_no_shift_covers_does_not_blame_the_roster(self) -> None:
        """`shift_id` is None because `shift_at` found no shift, which is a tick
        asking at an hour the plant does not run - not an unfilled roster."""
        result = _round(
            [_queued("WO-1", _order())], technicians=[], roster=_roster(), shift_id=None
        )

        assert result.band is Band.NO_CAPACITY
        assert result.load_ratio is None
        assert "ตอนนี้ไม่มีกะทำงาน" in result.summary
        assert "ตอนนี้ไม่มีกะทำงาน" in result.held[0].why
        assert "rostered" not in result.held[0].why

    def test_a_shift_with_an_empty_roster_names_the_shift(self) -> None:
        result = _round(
            [_queued("WO-1", _order())], technicians=[], roster=_roster(), shift_id=MORNING
        )

        assert result.band is Band.NO_CAPACITY
        assert "ยังไม่มีช่างลงชื่อในกะ morning" in result.held[0].why
        assert "ยังไม่มีช่างลงชื่อในกะ morning" in result.summary

    def test_people_rostered_with_no_minutes_left_are_not_reported_as_absent(self) -> None:
        """The case the two-way wording states falsely: they are on the line, and
        the answer is more people or less work rather than a roster to fill."""
        result = _round(
            [_queued("WO-1", _order())],
            technicians=_people(ANA),
            roster=_roster((ANA, 0)),
            shift_id=MORNING,
        )

        assert result.band is Band.NO_CAPACITY
        assert "มีงานเต็มเวลาแล้ว" in result.held[0].why
        assert "nobody is rostered" not in result.held[0].why

    def test_the_three_do_not_read_alike(self) -> None:
        """The point of the section, as one assertion: a reader can tell them
        apart. They were one sentence before, and the round said the same thing
        about three different situations."""
        queue = [_queued("WO-1", _order())]
        said = {
            _round(queue, technicians=[], roster=_roster(), shift_id=None).summary,
            _round(queue, technicians=[], roster=_roster(), shift_id=MORNING).summary,
            _round(
                queue,
                technicians=_people(ANA),
                roster=_roster((ANA, 0)),
                shift_id=MORNING,
            ).summary,
        }

        assert len(said) == 3

    def test_every_waiting_order_is_still_reported_rather_than_dropped(self) -> None:
        """No capacity is not a reason for work to disappear: a supervisor
        reading this round sees the whole queue that nobody can be given."""
        queue = [_queued(f"WO-{index}", _order()) for index in range(1, 4)]

        result = _round(queue, technicians=[], roster=_roster(), shift_id=None)

        assert sorted(held.ref for held in result.held) == ["WO-1", "WO-2", "WO-3"]
        assert result.placed == ()
        assert "มีงานรออยู่ 3 ใบ" in result.summary


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
        assert "รอกะที่งานเบา" in result.held[0].why

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
        assert "เพดานของงานบำรุงรักษาตามแผน" in result.held[0].why

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


class TestAReleaseOverridesTheGate:
    """ADR-059: what a shift lead pressing "release" does to a round.

    The gate is a default, not a verdict - ADR-011 kept it separate precisely so
    that the sentence it writes could be shown to a person, and showing somebody
    a decision they cannot overrule is how a scheduler gets worked around instead
    of argued with. What a release must not do is buy anything else: it does not
    change the score, it does not conjure a technician, and it does not stop the
    minutes it spends from counting.
    """

    def test_a_released_ticket_passes_a_heavy_gate(self) -> None:
        """The same shift as `test_a_heavy_shift_releases_only_high_and_critical`,
        with the supervisor having said yes to the low-severity job."""
        taken = _order(minutes=200, status=WorkOrderStatus.ASSIGNED, assignees=(ANA,))
        queue = [
            _queued("WO-taken", taken),
            _queued("WO-low", _order(severity=Severity.LOW, minutes=30), released=True),
            _queued("WO-high", _order(severity=Severity.HIGH, minutes=30)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 120), (BEN, 120))
        )

        assert result.band is Band.HEAVY
        assert {placed.ref for placed in result.placed} == {"WO-low", "WO-high"}
        assert result.held == ()

    def test_a_release_does_not_conjure_a_technician(self) -> None:
        """Releasing work says the gate should not hold it. It does not say
        anybody is free to do it, and an order nobody can take comes back
        unassigned with the same sentence as everybody else's (ADR-025)."""
        queue = [
            _queued(
                "WO-electrical",
                _order(severity=Severity.LOW, minutes=30, skill=ELECTRICAL),
                released=True,
            )
        ]

        result = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 240)))

        assert result.placed == ()
        assert [one.ref for one in result.unassigned] == ["WO-electrical"]
        assert "ช่างไฟฟ้า" in result.unassigned[0].why

    def test_released_condition_work_is_not_counted_twice(self) -> None:
        """The failure this test exists for is silent and would look like the
        top-up being conservative.

        Queued condition work is already demand and is in `load_ratio`; queued PM
        work is the reserve and is not (ADR-045 §2). A release that added its
        order's minutes to the running ratio whatever its origin would spend the
        condition job's hour twice, and the shift would top up one PM job fewer
        than it has room for - every round, for ever, with every number still
        adding up.
        """
        queue = [_queued("WO-cond", _order(minutes=60), released=True)] + [
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

        # 60 committed of 600, boundary 50%: four PM hours reach 300/600 and the
        # fifth would cross - the same four the gate releases when nothing has
        # been released by hand.
        released_pm = [placed.ref for placed in result.placed if placed.ref.startswith("WO-pm")]
        assert len(released_pm) == 4

    def test_released_maintenance_still_spends_the_shift(self) -> None:
        """The other side of the same rule, and the one a supervisor would
        notice.

        PM work becomes demand when it is released, whoever released it. Priced
        in, the release changes *which* maintenance this shift does - the job the
        supervisor chose displaces the one the top-up would have added. Not
        priced in, it would buy the shift a fifth hour of maintenance nobody
        decided to spend, and the boundary a supervisor is shown would be a
        boundary the system does not keep.
        """
        queue = [_queued("WO-cond", _order(minutes=60))] + [
            _queued(
                f"WO-pm-{index}",
                _order(origin=WorkOrderOrigin.SCHEDULED, severity=Severity.LOW, minutes=60),
                age_minutes=index,
                released=index == 0,
            )
            for index in range(8)
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 300), (BEN, 300))
        )

        released_pm = {placed.ref for placed in result.placed if placed.ref.startswith("WO-pm")}
        # Four PM hours is what 600 minutes of capacity leaves under the 50%
        # boundary, with or without a supervisor. WO-pm-0 is the newest and would
        # never have been the round's own choice; it is here because somebody
        # said so, and WO-pm-4 - which the round would have taken - is not.
        assert "WO-pm-0" in released_pm
        assert len(released_pm) == 4
        assert "WO-pm-4" in {held.ref for held in result.held}

    def test_no_capacity_is_not_something_a_release_can_answer(self) -> None:
        """An hour the plant does not run is not the gate holding work back, and
        releasing into it would place nobody on anything (ADR-045 §3). The round
        says so rather than pretending the release did something."""
        queue = [_queued("WO-1", _order(), released=True)]

        result = _round(queue, technicians=[], roster=_roster(), shift_id=None)

        assert result.band is Band.NO_CAPACITY
        assert [held.ref for held in result.held] == ["WO-1"]
        assert result.placed == ()


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

        assert "ความรุนแรงระดับวิกฤต" in result.placed[0].priority_reason
        assert result.summary.startswith("กะนี้ใช้กำลังคนไป")

    def test_scheduled_work_does_not_claim_waiting_stops_the_line(self) -> None:
        """ADR-104. A PM job's machine is running while it waits; the downtime
        figure is what doing it costs, and the sentence says so."""
        queue = [
            _queued(
                "WO-pm",
                _order(machine_id=BOTTLENECK, origin=WorkOrderOrigin.SCHEDULED, skill=None),
            )
        ]

        result = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 300)))

        (placed,) = result.placed
        assert "ถ้างานนี้รอ" not in placed.priority_reason
        assert "ต้องหยุดเครื่อง" in placed.priority_reason


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
        assert "2 คน" in result.unassigned[0].why

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
        assert "ที่มีเวลาว่าง 60 นาที · ตอนนี้มีว่าง 0 คน" in result.unassigned[0].why

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
        assert "ช่างไฟฟ้า" in result.unassigned[0].why


class TestAnOrderThatOutlivedTheLayout:
    """ADR-048. A work order carries the machine it was created against, and the
    layout is edited when the line is rearranged (ADR-027). The two drift, and
    the drift must not take the round down with it."""

    STALE = MachineId("MC-999")  # in no line in plant.yaml, and never was

    def test_one_stale_order_does_not_take_the_whole_round_with_it(self) -> None:
        """The failure this fixes: `station_of` raised, the round returned
        nothing, and three machines that are still on the line went unscheduled
        because of one that is not."""
        queue = [
            _queued("WO-1", _order(machine_id=self.STALE)),
            _queued("WO-2", _order(machine_id=BOTTLENECK)),
            _queued("WO-3", _order(machine_id=BUFFERED)),
        ]

        result = _round(
            queue, technicians=_people(ANA, BEN), roster=_roster((ANA, 480), (BEN, 480))
        )

        assert {placement.ref for placement in result.placed} >= {"WO-2", "WO-3"}

    def test_the_work_is_still_released_rather_than_parked(self) -> None:
        """The machine is real and somebody has to go to it. A stale line in a
        YAML file is a reason to say so, not a reason to withhold the job -
        parking real work until somebody edits config is how a system like this
        gets overruled and then abandoned."""
        queue = [_queued("WO-1", _order(machine_id=self.STALE))]

        result = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 480)))

        assert [placement.ref for placement in result.placed] == ["WO-1"]
        assert result.held == ()

    def test_the_line_cost_is_not_claimed_and_the_ticket_says_which_machine(self) -> None:
        queue = [_queued("WO-1", _order(machine_id=self.STALE))]

        placement = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 480))).placed[0]

        assert placement.terms.downtime == 0.0
        assert placement.terms.downtime_is_unknown
        assert "MC-999" in placement.priority_reason

    def test_a_repair_shorter_than_the_buffer_is_not_the_same_as_an_unknown_one(self) -> None:
        """Both score zero on downtime and they mean opposite things: one is a
        line that genuinely will not feel this, the other is a line we cannot
        speak for. A single number could not tell a supervisor which."""
        queue = [_queued("WO-1", _order(machine_id=BUFFERED, minutes=10))]

        placement = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 480))).placed[0]

        assert placement.terms.downtime == 0.0
        assert not placement.terms.downtime_is_unknown
        assert "MC-001" not in placement.priority_reason

    def test_the_stale_machine_does_not_flatten_the_others(self) -> None:
        """Normalisation divides by the largest in the round (ADR-045 §1), so
        an unknown machine has to enter that list as a zero rather than be left
        out - dropping it would shift every other order's term."""
        queue = [
            _queued("WO-1", _order(machine_id=self.STALE)),
            _queued("WO-2", _order(machine_id=BOTTLENECK)),
        ]
        without = [_queued("WO-2", _order(machine_id=BOTTLENECK))]

        with_stale = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 480)))
        alone = _round(without, technicians=_people(ANA), roster=_roster((ANA, 480)))

        bottleneck = next(p for p in with_stale.placed if p.ref == "WO-2")
        assert bottleneck.terms.downtime == alone.placed[0].terms.downtime == 1.0

    def test_the_round_tells_the_supervisor_the_layout_has_drifted(self) -> None:
        """The half of this that keeps the config error loud. The work flows,
        and every round says the file needs looking at until somebody does."""
        queue = [_queued("WO-1", _order(machine_id=self.STALE))]

        result = _round(queue, technicians=_people(ANA), roster=_roster((ANA, 480)))

        assert "1 ใบระบุเครื่องที่ไม่มีในผังสายการผลิต" in result.summary


class TestWhatADR049Settles:
    """The three places ADR-045 and its implementation did not obviously agree.

    Each of these pins a decision rather than a mechanism, which is why they are
    worth having: without them the next reader finds the same three questions
    and has to answer them again, possibly differently.
    """

    def test_the_skill_term_asks_the_shift_not_the_clock(self) -> None:
        """ADR-049 §1. ADR-045 §1's table says "free" and means rostered.

        The signature is the decision: no capacity reaches this function, so the
        term cannot move as people finish jobs. That is what stops the queue
        re-ranking itself under a technician already walking to a machine.
        """
        needs_mechanical = _order(skill=MECHANICAL)
        ana = Technician(user=ANA, skills=frozenset({MECHANICAL}))

        assert _skill_match(needs_mechanical, [ana]) == 1.0
        assert _skill_match(needs_mechanical, []) == 0.0

    def test_the_only_holder_being_booked_is_reported_not_scored_away(self) -> None:
        """The consequence at round level, and the reason the term does not need
        to know about minutes: "nobody with this skill has time left" arrives as
        a fact a supervisor can act on within the shift, rather than as a job
        that quietly sank down the list.
        """
        # Ana holds the skill and her whole shift is already spent; Ben is free
        # and holds a different one.
        booked = Queued(
            ref="WO-BIG",
            order=_order(minutes=480, assignees=(ANA,)).model_copy(
                update={"status": WorkOrderStatus.IN_PROGRESS}
            ),
            created_at=NOW,
        )
        crew = [
            Technician(user=ANA, skills=frozenset({MECHANICAL})),
            Technician(user=BEN, skills=frozenset({ELECTRICAL})),
        ]

        result = _round(
            [booked, _queued("WO-1", _order(skill=MECHANICAL))],
            technicians=crew,
            roster=_roster((ANA, 480), (BEN, 480)),
        )

        assert result.band is Band.NORMAL
        assert [withheld.ref for withheld in result.unassigned] == ["WO-1"]
        assert "ช่างกลหุ่นยนต์" in result.unassigned[0].why
        assert result.held == ()

    def test_a_term_too_small_to_mention_is_still_in_the_number(self) -> None:
        """ADR-049 §2. The threshold decides which clauses are worth a sentence
        and nothing else: the score is the weighted sum of every term, computed
        before `_reason` is called, and the terms are returned in full beside it.
        """
        weights = CONFIG.policy.weights
        result = _round(
            [
                _queued("WO-1", _order(), age_minutes=60),
                _queued("WO-2", _order(), age_minutes=1),
            ],
            technicians=_people(ANA, BEN),
            roster=_roster((ANA, 480), (BEN, 480)),
        )
        barely_waited = next(p for p in result.placed if p.ref == "WO-2")
        terms = barely_waited.terms

        # A minute against an hour: real, and far too small to be worth a clause.
        assert 0 < weights.waiting * terms.waiting < 0.05
        assert "waiting" not in barely_waited.priority_reason
        # And yet the number it was ranked by counted it.
        assert barely_waited.priority_score == pytest.approx(
            weights.severity * terms.severity
            + weights.downtime * terms.downtime
            + weights.skill_match * terms.skill_match
            + weights.waiting * terms.waiting
            + weights.eta_urgency * terms.eta_urgency
        )

    def test_a_shift_is_its_wall_clock_hours_across_a_daylight_saving_change(self) -> None:
        """ADR-049 §3. Seven real hours in spring, nine in autumn, and both are
        what the plant worked. This is the assertion that stops somebody
        "fixing" it into a fixed eight."""
        new_york = ZoneInfo("America/New_York")
        night = (
            ShiftDefinition(shift_id=ShiftId("night"), starts_at=time(22, 0), ends_at=time(6, 0)),
        )

        spring = shift_at(night, datetime(2026, 3, 8, 4, 0, tzinfo=UTC), new_york)
        autumn = shift_at(night, datetime(2026, 11, 1, 4, 0, tzinfo=UTC), new_york)

        assert spring is not None and autumn is not None
        assert spring.ends_at - spring.starts_at == timedelta(hours=7)
        assert autumn.ends_at - autumn.starts_at == timedelta(hours=9)
        # Local wall clock is identical in both: people arrive at ten and leave
        # at six, which is what a shift is.
        for window in (spring, autumn):
            assert window.starts_at.astimezone(new_york).hour == 22
            assert window.ends_at.astimezone(new_york).hour == 6

    def test_a_boundary_in_the_hour_that_does_not_exist_takes_the_later_offset(self) -> None:
        """The one case ADR-045 §7 left undefined. 02:30 does not happen on the
        morning the clocks go forward, and the answer is the hour the plant
        would actually be standing there."""
        new_york = ZoneInfo("America/New_York")
        skipped = (
            ShiftDefinition(shift_id=ShiftId("odd"), starts_at=time(2, 30), ends_at=time(10, 30)),
        )

        window = shift_at(skipped, datetime(2026, 3, 8, 9, 0, tzinfo=UTC), new_york)

        assert window is not None
        assert window.starts_at.astimezone(new_york).strftime("%H:%M") == "03:30"


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

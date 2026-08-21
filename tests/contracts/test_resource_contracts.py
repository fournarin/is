"""Rules the resource contracts refuse to break (ADR-027).

The two that matter most are the unit of shift capacity and the PM symptom
prefix. Both are places where a wrong answer produces no error at all, just a
scheduler that quietly does the wrong thing.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from pdm.contracts import (
    PM_SYMPTOM_PREFIX,
    Line,
    LineId,
    MachineId,
    PMTask,
    PMTaskRef,
    ShiftAssignment,
    ShiftDefinition,
    ShiftId,
    SkillId,
    Station,
    StationId,
    SymptomCode,
    Technician,
    UserId,
    shift_at,
    shift_capacity_minutes,
)

LINE_A = Line(line_id=LineId("line-a"), takt_seconds=60.0)
TODAY = date(2026, 3, 3)
MORNING = ShiftId("morning")
AFTERNOON = ShiftId("afternoon")
NIGHT = ShiftId("night")

# The plant is in Bangkok, seven hours ahead of UTC and with no daylight saving,
# which is what makes the difference between the two readings visible in every
# assertion below rather than in one shift a year.
BANGKOK = ZoneInfo("Asia/Bangkok")

# The three shifts in plant.yaml, written out rather than loaded: a contract test
# that reads config would pass or fail on the config rather than on the rule.
SHIFTS = (
    ShiftDefinition(shift_id=MORNING, starts_at=time(6, 0), ends_at=time(14, 0)),
    ShiftDefinition(shift_id=AFTERNOON, starts_at=time(14, 0), ends_at=time(22, 0)),
    ShiftDefinition(shift_id=NIGHT, starts_at=time(22, 0), ends_at=time(6, 0)),
)


def _bangkok(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    """A local wall-clock moment in the plant, as the UTC instant it really is."""
    return datetime(year, month, day, hour, minute, tzinfo=BANGKOK).astimezone(UTC)


def _covering(moment: datetime) -> tuple[ShiftId, date] | None:
    window = shift_at(SHIFTS, moment, BANGKOK)
    return None if window is None else (window.shift_id, window.on_date)


class TestStationsAndBuffers:
    """ADR-021: two identical faults are not equally urgent."""

    def test_a_thick_buffer_buys_the_technician_time(self) -> None:
        station = Station(
            station_id=StationId("st-1"),
            line_id=LINE_A.line_id,
            seq=1,
            buffer_units=20,
            machine_ids=(MachineId("MC-001"),),
        )
        assert station.buffer_minutes(LINE_A) == 20.0

    def test_a_bottleneck_buys_none(self) -> None:
        """Stops, and the line stops with it. Scoring these two alike produces an
        ordering technicians can see is wrong."""
        station = Station(
            station_id=StationId("st-4"),
            line_id=LINE_A.line_id,
            seq=4,
            buffer_units=0,
            bottleneck_multiplier=3.0,
        )
        assert station.buffer_minutes(LINE_A) == 0.0
        assert station.bottleneck_multiplier > 1.0

    def test_a_station_refuses_to_be_measured_against_another_line(self) -> None:
        station = Station(station_id=StationId("st-1"), line_id=LineId("line-b"), seq=1)
        with pytest.raises(ValueError, match="not on line"):
            station.buffer_minutes(LINE_A)


class TestShiftCapacityIsPersonMinutes:
    """design.md 13.2: both sides of load_ratio must use the same unit.

    If capacity counted wall-clock minutes while the workload side multiplied by
    required_technicians, the gate would be wrong on every shift containing a
    two-person job, and nothing would report it.
    """

    def test_capacity_is_the_sum_across_people(self) -> None:
        assignments = (
            ShiftAssignment(
                shift_id=MORNING, on_date=TODAY, technician=UserId("a"), available_minutes=480
            ),
            ShiftAssignment(
                shift_id=MORNING, on_date=TODAY, technician=UserId("b"), available_minutes=480
            ),
        )
        assert shift_capacity_minutes(assignments, MORNING, TODAY) == 960

    def test_partial_availability_is_respected(self) -> None:
        """Leave, training and late starts are capacity the gate must not
        over-commit."""
        assignments = (
            ShiftAssignment(
                shift_id=MORNING, on_date=TODAY, technician=UserId("a"), available_minutes=480
            ),
            ShiftAssignment(
                shift_id=MORNING, on_date=TODAY, technician=UserId("b"), available_minutes=240
            ),
        )
        assert shift_capacity_minutes(assignments, MORNING, TODAY) == 720

    def test_other_shifts_and_other_days_are_excluded(self) -> None:
        assignments = (
            ShiftAssignment(
                shift_id=MORNING, on_date=TODAY, technician=UserId("a"), available_minutes=480
            ),
            ShiftAssignment(
                shift_id=ShiftId("night"),
                on_date=TODAY,
                technician=UserId("c"),
                available_minutes=480,
            ),
            ShiftAssignment(
                shift_id=MORNING,
                on_date=date(2026, 3, 4),
                technician=UserId("d"),
                available_minutes=480,
            ),
        )
        assert shift_capacity_minutes(assignments, MORNING, TODAY) == 480

    def test_a_shift_with_nobody_on_it_has_no_capacity(self) -> None:
        assert shift_capacity_minutes((), MORNING, TODAY) == 0


class TestShiftDefinitions:
    def test_a_day_shift_does_not_cross_midnight(self) -> None:
        shift = ShiftDefinition(shift_id=MORNING, starts_at=time(6, 0), ends_at=time(14, 0))
        assert not shift.crosses_midnight
        assert shift.length == timedelta(hours=8)

    def test_the_night_shift_crosses_midnight(self) -> None:
        """The reason every timestamp in this system is timezone-aware UTC: a
        naive datetime gives the wrong answer for exactly this one shift and the
        right answer for the other two (ADR-028)."""
        shift = ShiftDefinition(
            shift_id=ShiftId("night"), starts_at=time(22, 0), ends_at=time(6, 0)
        )
        assert shift.crosses_midnight
        assert shift.length == timedelta(hours=8)


class TestShiftAt:
    """Which shift covers a moment, and whose roster that is (ADR-045 section 7).

    Shift boundaries are local wall-clock times - `06:00` is the hour people
    arrive - and every moment compared against them is UTC (ADR-028). Getting
    that conversion wrong is not a crash: it reads the wrong roster for one
    shift in three and the right one for the others, which is the failure
    ADR-028 was written about.
    """

    def test_a_moment_is_read_in_the_plants_own_zone_and_not_in_utc(self) -> None:
        """Half past midnight UTC is half past seven in the morning in Bangkok.

        This is the test that fails against the implementation somebody would
        write without thinking about it. Compared as UTC, `00:30` falls inside
        the night shift and files under the day before: wrong shift, wrong
        roster, wrong day, and nothing reports it.
        """
        window = shift_at(SHIFTS, datetime(2026, 3, 3, 0, 30, tzinfo=UTC), BANGKOK)

        assert window is not None
        assert window.shift_id == MORNING
        assert window.on_date == date(2026, 3, 3)

    def test_the_night_shift_before_midnight_is_filed_under_that_day(self) -> None:
        window = shift_at(SHIFTS, _bangkok(2026, 3, 3, 23, 30), BANGKOK)

        assert window is not None
        assert window.shift_id == NIGHT
        assert window.on_date == date(2026, 3, 3)

    def test_the_night_shift_after_midnight_is_filed_under_the_day_it_started(self) -> None:
        """Tuesday at one in the morning is Monday night's shift.

        A roster is written against the day the shift began, so filing this
        under Tuesday would look up people who are not there and count the
        capacity of a shift that has not started (ADR-027).
        """
        window = shift_at(SHIFTS, _bangkok(2026, 3, 4, 1, 30), BANGKOK)

        assert window is not None
        assert window.shift_id == NIGHT
        assert window.on_date == date(2026, 3, 3)

    def test_a_boundary_belongs_to_the_shift_it_starts(self) -> None:
        """Half-open, or the handover minute belongs to two shifts at once and
        its work is counted against both rosters."""
        assert _covering(_bangkok(2026, 3, 3, 6, 0)) == (MORNING, date(2026, 3, 3))
        assert _covering(_bangkok(2026, 3, 3, 13, 59)) == (MORNING, date(2026, 3, 3))
        assert _covering(_bangkok(2026, 3, 3, 14, 0)) == (AFTERNOON, date(2026, 3, 3))

    def test_an_hour_no_shift_covers_is_not_the_nearest_shift(self) -> None:
        """A plant that runs one shift a day has sixteen hours with nobody in
        it. `None` is the answer the caller has to handle - `dispatch()` reads
        it as no capacity rather than scheduling against an absent roster."""
        one_shift = (ShiftDefinition(shift_id=MORNING, starts_at=time(6, 0), ends_at=time(14, 0)),)

        assert shift_at(one_shift, _bangkok(2026, 3, 3, 10, 0), BANGKOK) is not None
        assert shift_at(one_shift, _bangkok(2026, 3, 3, 20, 0), BANGKOK) is None
        assert shift_at(one_shift, _bangkok(2026, 3, 4, 2, 0), BANGKOK) is None

    def test_the_window_it_returns_is_absolute_utc(self) -> None:
        """Local times are what a shift *is*; UTC is what the rest of the system
        compares against. The window carries both facts without confusing them."""
        window = shift_at(SHIFTS, _bangkok(2026, 3, 3, 7, 0), BANGKOK)

        assert window is not None
        # 06:00 in Bangkok is 23:00 UTC the evening before.
        assert window.starts_at == datetime(2026, 3, 2, 23, 0, tzinfo=UTC)
        assert window.ends_at == datetime(2026, 3, 3, 7, 0, tzinfo=UTC)
        assert window.ends_at - window.starts_at == timedelta(hours=8)

    def test_a_window_contains_its_start_and_not_its_end(self) -> None:
        window = shift_at(SHIFTS, _bangkok(2026, 3, 3, 7, 0), BANGKOK)

        assert window is not None
        assert window.contains(window.starts_at)
        assert not window.contains(window.ends_at)
        assert not window.contains(window.starts_at - timedelta(microseconds=1))

    def test_every_hour_of_a_day_lands_on_exactly_one_shift(self) -> None:
        """Three eight-hour shifts cover the day with no gap and no overlap. A
        gap loses work; an overlap prices it against two rosters."""
        covered = [_covering(_bangkok(2026, 3, 3, hour, 0)) for hour in range(24)]
        named = [entry for entry in covered if entry is not None]

        assert len(named) == 24
        assert len({shift for shift, _ in named}) == 3


class TestSkillsComeFromOneList:
    """ADR-027: two vocabularies would fail to match in silence."""

    def test_a_technician_matches_a_skill_they_hold(self) -> None:
        tech = Technician(user=UserId("tech-a"), skills=frozenset({SkillId("robot_mechanical")}))
        assert tech.can_perform(SkillId("robot_mechanical"))

    def test_a_technician_does_not_match_one_they_do_not(self) -> None:
        tech = Technician(user=UserId("tech-a"), skills=frozenset({SkillId("electrical")}))
        assert not tech.can_perform(SkillId("robot_mechanical"))


class TestPMTasksUseTheOrdinaryLookupPath:
    """ADR-027: layer 2 never learns the concept of scheduled maintenance."""

    def _task(self, symptom_code: str) -> PMTask:
        return PMTask(
            pm_task_ref=PMTaskRef("pm-1"),
            machine_id=MachineId("MC-012"),
            symptom_code=SymptomCode(symptom_code),
            interval=timedelta(days=30),
            due_at=datetime(2026, 3, 3, tzinfo=UTC),
        )

    def test_a_pm_symptom_code_is_accepted(self) -> None:
        assert self._task("PM-belt-inspection").symptom_code.startswith(PM_SYMPTOM_PREFIX)

    def test_a_non_pm_symptom_code_is_rejected(self) -> None:
        """Without the prefix, PM work would need a second lookup path in layer
        2, and a second path means a second set of tests and a second way to be
        wrong."""
        with pytest.raises(ValidationError, match="must start with"):
            self._task("SYM-014")

    def test_a_task_is_due_at_or_after_its_due_date(self) -> None:
        task = self._task("PM-belt-inspection")
        assert not task.is_due(datetime(2026, 3, 2, tzinfo=UTC))
        assert task.is_due(datetime(2026, 3, 3, tzinfo=UTC))
        assert task.is_due(datetime(2026, 3, 4, tzinfo=UTC))

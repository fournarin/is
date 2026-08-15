"""The four contracts that describe resources and places (ADR-027, design.md 13).

Layer 3 is the core of this project and every one of these is something it needs.
They are split by how often they change, not by what they are about:

  config    Line, Station, ShiftDef - change when the plant is rearranged,
            which is a yearly event.
  database  Technician, ShiftAssignment, PMTask - change during a shift.

Station being config rather than a table does not contradict ADR-016, which
refused component entities. That refusal was about a taxonomy with no owner;
the station layout has a clear one in production engineering and already exists
on paper.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts.ids import (
    LineId,
    MachineId,
    PMTaskRef,
    ShiftId,
    SkillId,
    StationId,
    SymptomCode,
    UserId,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# PM work reuses the ordinary symptom code path with a reserved prefix, so
# layer 2 keys playbooks by (symptom_code, machine_model) exactly as it does for
# everything else and never learns the concept of scheduled maintenance. One
# lookup path, one set of tests (ADR-027).
PM_SYMPTOM_PREFIX = "PM-"


class Line(BaseModel):
    """A production line."""

    model_config = _FROZEN

    line_id: LineId
    # Seconds between units leaving the line. Turns downtime into lost units,
    # which is the number the w2 term is built from (ADR-021).
    takt_seconds: float = Field(gt=0)


class Station(BaseModel):
    """One position on a line, and the machines standing at it.

    The buffer is why two identical faults are not equally urgent. A station with
    twenty units queued ahead of it buys the technician tens of minutes; a
    bottleneck with none stops the line the moment it stops. Treating them alike
    produces an ordering technicians can see is wrong, which costs the system
    their trust (ADR-021).
    """

    model_config = _FROZEN

    station_id: StationId
    line_id: LineId
    # Position along the line, ascending.
    seq: int = Field(ge=0)
    buffer_units: int = Field(default=0, ge=0)
    bottleneck_multiplier: float = Field(default=1.0, gt=0)
    # The mapping that lets a Finding holding only a machine_id be scored at
    # station level. Every machine a rule can name must appear here or config
    # fails to load (invariant 13).
    machine_ids: tuple[MachineId, ...] = ()

    def buffer_minutes(self, line: Line) -> float:
        """How long this station can be down before the line feels it."""
        if line.line_id != self.line_id:
            raise ValueError(f"station {self.station_id} is not on line {line.line_id}")
        return self.buffer_units * line.takt_seconds / 60.0


class ShiftDefinition(BaseModel):
    """When a shift runs. Changes about once a year, so it lives in config.

    Who is on it today changes daily and lives in ShiftAssignment. Keeping them
    together would drag the stable half into the database with the volatile one.
    """

    model_config = _FROZEN

    shift_id: ShiftId
    starts_at: time
    ends_at: time

    @property
    def crosses_midnight(self) -> bool:
        """True for the night shift, which is why every timestamp in this system
        is timezone-aware UTC (ADR-028)."""
        return self.ends_at <= self.starts_at

    @property
    def length(self) -> timedelta:
        start = timedelta(hours=self.starts_at.hour, minutes=self.starts_at.minute)
        end = timedelta(hours=self.ends_at.hour, minutes=self.ends_at.minute)
        if self.crosses_midnight:
            end += timedelta(days=1)
        return end - start


class Technician(BaseModel):
    """Somebody who can be assigned work.

    `skills` draws from the same config list as Playbook.required_skill. Two
    vocabularies would fail to match in silence: work would keep being assigned,
    just to the wrong people, with nothing to show for it (ADR-027).
    """

    model_config = _FROZEN

    user: UserId
    skills: frozenset[SkillId] = frozenset()
    active: bool = True

    def can_perform(self, required: SkillId) -> bool:
        return required in self.skills


class ShiftAssignment(BaseModel):
    """One technician on one shift on one day, and how long they are available.

    `available_minutes` rather than the shift length: people take leave, attend
    training and arrive late, and capacity that ignores that is capacity the
    gate will over-commit.
    """

    model_config = _FROZEN

    shift_id: ShiftId
    on_date: date
    technician: UserId
    available_minutes: int = Field(gt=0)


class PMTask(BaseModel):
    """Scheduled maintenance, the main source of work for a quiet shift.

    `symptom_code` carries the PM- prefix so this reaches layer 2 through the
    ordinary lookup. Without a second source of work, "release lower-priority
    jobs when the shift is light" - the behaviour the advisor described most
    concretely - has nothing to release (ADR-010).
    """

    model_config = _FROZEN

    pm_task_ref: PMTaskRef
    machine_id: MachineId
    symptom_code: SymptomCode
    interval: timedelta
    due_at: datetime
    last_done_at: datetime | None = None

    @model_validator(mode="after")
    def _uses_a_pm_symptom_code(self) -> PMTask:
        if not self.symptom_code.startswith(PM_SYMPTOM_PREFIX):
            raise ValueError(
                f"a PM task's symptom_code must start with {PM_SYMPTOM_PREFIX!r} "
                f"so layer 2 can serve it through the normal path (ADR-027); "
                f"got {self.symptom_code!r}"
            )
        return self

    def is_due(self, now: datetime) -> bool:
        return now >= self.due_at


class ShiftWindow(BaseModel):
    """A shift on a particular day, resolved to absolute moments.

    `on_date` is the **local date the shift started on**, which is what a roster
    is written against: the night shift running into Tuesday morning is Monday
    night's shift, and its assignments are filed under Monday.
    """

    model_config = _FROZEN

    shift_id: ShiftId
    on_date: date
    starts_at: datetime
    ends_at: datetime

    def contains(self, moment: datetime) -> bool:
        return self.starts_at <= moment < self.ends_at


def shift_at(
    shifts: Iterable[ShiftDefinition], moment: datetime, zone: tzinfo
) -> ShiftWindow | None:
    """Which shift covers this moment, and the date its roster is filed under.

    `moment` is UTC (everything in this system is); the shift's boundaries are
    local wall-clock times in the plant's own zone, because that is what they
    are - the hour people arrive. Converting here rather than at either end is
    what keeps the two facts from being confused (ADR-028, ADR-045 §7).

    None where no shift covers the moment. A plant that runs sixteen hours a day
    has eight hours with no shift, and "no shift" is an answer the caller has to
    handle rather than a case to paper over with the nearest one.
    """
    local = moment.astimezone(zone)
    for shift in shifts:
        # Two candidate days: a shift that crosses midnight and covers 01:00
        # started yesterday. Checked in order, so the answer for a moment inside
        # two overlapping shifts is the earlier-starting one - overlapping shifts
        # are a config error rather than something to resolve here.
        for days_back in (0, 1):
            starts_local = datetime.combine(
                local.date() - timedelta(days=days_back), shift.starts_at, tzinfo=zone
            )
            window = ShiftWindow(
                shift_id=shift.shift_id,
                on_date=starts_local.date(),
                starts_at=starts_local.astimezone(UTC),
                ends_at=(starts_local + shift.length).astimezone(UTC),
            )
            if window.contains(moment):
                return window
    return None


def shift_capacity_minutes(
    assignments: tuple[ShiftAssignment, ...],
    shift_id: ShiftId,
    on_date: date,
) -> int:
    """Person-minutes available for one shift.

    The unit matters and is easy to get wrong. The other side of load_ratio sums
    estimated_minutes multiplied by required_technicians (ADR-025), so both sides
    are person-minutes. If one side counted wall-clock minutes instead, the gate
    would be wrong on every shift with a two-person job in it and nothing would
    report the error (ADR-027, design.md 13.2).
    """
    return sum(
        assignment.available_minutes
        for assignment in assignments
        if assignment.shift_id == shift_id and assignment.on_date == on_date
    )

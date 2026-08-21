"""What a run is made of: the shift, the roster, and where the failures come from.

**The failures are generated, and every property of one except its timing is
read out of configuration.** A failure picks one of the rules `rules.yaml`
declares for that machine's model, and takes that rule's severity, component and
symptom code; its duration is the same `fallback_minutes` figure the work module
would price the ticket at. So the simulator has no vocabulary of its own to drift
out of step with the system it is measuring, and nothing here needed a number
invented for it.

What *is* invented is the rate. `mean_hours_between_failures` stands in for a
mean time between failures nobody has measured, and it is the one figure in this
package with none of the three provenances `policy.yaml` demands. It is declared
per window rather than hidden in a default so that it is visible at the point
where somebody has to defend it, and slice 7.3 is expected to report across
several values of it rather than one - which is the same argument ADR-021 makes
about the assumed buffer map.

Arrivals are Poisson: exponential gaps, drawn from a generator seeded per
(window, machine). Seeding per machine is the property `SyntheticSource` has for
the same reason (ADR-032) - adding a machine to a scenario leaves every other
machine's failures where they were, so two measurements stay comparable.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts import (
    ComponentLabel,
    LineId,
    MachineId,
    RuleId,
    Severity,
    ShiftAssignment,
    ShiftId,
    SymptomCode,
    Technician,
    shift_capacity_minutes,
)
from pdm.platform.config import Config
from pdm.sim.domain import ProductionLine

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ArrivalWindow(BaseModel):
    """A stretch of the run during which machines fail at a given rate.

    Windows are how one scenario reaches both bands of ADR-011: a quiet stretch
    the gate should be releasing secondary work in, and a busy one it should be
    holding work back in. A run that only ever sat in one band could not show
    that the gate does anything.
    """

    model_config = _FROZEN

    name: str = Field(min_length=1)
    starts_after: timedelta
    lasts: timedelta
    # The assumption. See this module's docstring: no measurement stands behind
    # it, and the report must say so wherever a figure derived from it appears.
    mean_hours_between_failures: float = Field(gt=0)
    # Empty means every machine on the line.
    machines: tuple[MachineId, ...] = ()

    @model_validator(mode="after")
    def _the_window_is_a_real_stretch_of_time(self) -> ArrivalWindow:
        if self.starts_after < timedelta(0):
            raise ValueError(f"window {self.name!r} starts before the run does")
        if self.lasts <= timedelta(0):
            raise ValueError(f"window {self.name!r} lasts no time at all")
        return self

    @property
    def ends_after(self) -> timedelta:
        return self.starts_after + self.lasts

    @property
    def minutes(self) -> float:
        return self.lasts.total_seconds() / 60.0


class SimScenario(BaseModel):
    """One run: a line, a shift, the people on it, and the arrivals.

    Scenarios are code rather than configuration, for the reason ADR-032 gives
    for the signal scenarios: they change per experiment, not when the plant is
    rearranged. `plant.yaml` describes the factory; this describes a question
    being asked of it.
    """

    model_config = _FROZEN

    name: str = Field(min_length=1)
    line_id: LineId
    starts_at: datetime
    duration: timedelta
    # How often dispatch runs. Five minutes is the cadence design.md 6.2 gives
    # the dispatch round; it is a parameter here because 7.3 may want to show
    # what a slower one costs.
    round_interval: timedelta

    shift_id: ShiftId
    technicians: tuple[Technician, ...] = ()
    assignments: tuple[ShiftAssignment, ...] = ()

    windows: tuple[ArrivalWindow, ...] = ()

    @model_validator(mode="after")
    def _time_is_timezone_aware_and_moves_forward(self) -> SimScenario:
        if self.starts_at.tzinfo is None:
            raise ValueError(
                "a scenario needs a timezone-aware start time. The night shift "
                "crosses midnight, so a naive datetime is wrong for exactly one "
                "of the three shifts and right for the other two (ADR-028)"
            )
        if self.duration <= timedelta(0):
            raise ValueError("a scenario must last some time")
        if self.round_interval <= timedelta(0):
            raise ValueError("the dispatch round must have a positive interval")
        return self

    @model_validator(mode="after")
    def _windows_fit_inside_the_run(self) -> SimScenario:
        """A window generating failures past the end produces work that never
        appears in the log against capacity that is never offered."""
        seen: set[str] = set()
        for window in self.windows:
            if window.name in seen:
                raise ValueError(f"two windows are called {window.name!r}")
            seen.add(window.name)
            if window.ends_after > self.duration:
                raise ValueError(
                    f"window {window.name!r} ends at {window.ends_after} but the run "
                    f"stops at {self.duration}"
                )
        return self

    @model_validator(mode="after")
    def _the_roster_and_the_assignments_describe_the_same_people(self) -> SimScenario:
        """Capacity is summed from the assignments and availability is checked
        against the roster. A name in one and not the other silently changes
        `load_ratio` on one side only."""
        roster = {technician.user for technician in self.technicians}
        for assignment in self.assignments:
            if assignment.technician not in roster:
                raise ValueError(
                    f"{assignment.technician} is assigned to the shift but is not on "
                    f"the roster of scenario {self.name!r}"
                )
            if assignment.shift_id != self.shift_id:
                raise ValueError(
                    f"{assignment.technician} is assigned to shift "
                    f"{assignment.shift_id}, but this scenario runs {self.shift_id}"
                )
            if assignment.on_date != self.on_date:
                raise ValueError(
                    f"{assignment.technician} is assigned on {assignment.on_date}, "
                    f"but this scenario runs on {self.on_date}"
                )
        return self

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + self.duration

    @property
    def on_date(self) -> date:
        return self.starts_at.date()

    @property
    def capacity_minutes(self) -> int:
        """Person-minutes for the shift, through the same function layer 3 uses
        (ADR-027). Both sides of `load_ratio` have to be in this unit or the
        gate is wrong on every shift with a two-person job in it."""
        return shift_capacity_minutes(self.assignments, self.shift_id, self.on_date)

    @property
    def active_technicians(self) -> tuple[Technician, ...]:
        return tuple(technician for technician in self.technicians if technician.active)


class Failure(BaseModel):
    """A machine stopping, and the ticket it is about to become.

    Everything except `at` is read from configuration: the rule that would have
    caught it, and the duration `policy.yaml` prices that severity at. The
    engine hands the same number to the work module as the estimate and keeps it
    as the truth, so the simulator models no estimate error at all. It could -
    but the spread would be a number with nothing behind it, and every figure
    derived from it would inherit that (ADR-006 is about the real feedback loop;
    this is not it).
    """

    model_config = _FROZEN

    machine_id: MachineId
    at: datetime
    window: str
    rule_id: RuleId
    component: ComponentLabel
    symptom_code: SymptomCode
    severity: Severity
    repair_minutes: int = Field(gt=0)


def failures_for(scenario: SimScenario, config: Config, *, seed: int = 0) -> tuple[Failure, ...]:
    """Every failure a scenario produces under one seed, in time order.

    Separate from `run()` so that slice 7.3 can put the identical failure set in
    front of three policies and know the difference it measures is the policy.
    Running each of them with the same (scenario, seed) already guarantees that;
    being able to see the set is what makes it checkable.
    """
    line = ProductionLine.from_config(config, scenario.line_id)
    failures: list[Failure] = []

    for window in scenario.windows:
        machines = window.machines or line.machine_ids
        for machine_id in sorted(machines):
            line.station_of(machine_id)  # a scenario naming a machine off the line is an error
            failures.extend(_failures_on(machine_id, window, scenario, config, seed=seed))

    return tuple(sorted(failures, key=lambda failure: (failure.at, failure.machine_id)))


def _failures_on(
    machine_id: MachineId,
    window: ArrivalWindow,
    scenario: SimScenario,
    config: Config,
    *,
    seed: int,
) -> list[Failure]:
    model = config.model_of(machine_id)
    # Sorted, because rng.choice over an unordered sequence would make the run
    # depend on the order rules happen to sit in the file.
    rules = sorted(
        (rule for rule in config.rules.rules if rule.machine_model == model),
        key=lambda rule: rule.rule_id,
    )
    if not rules:
        raise ValueError(
            f"machine {machine_id} is a {model}, which no rule in rules.yaml watches, "
            f"so a failure on it could never have become a ticket"
        )

    # A string seed is hashed with sha512 by CPython rather than the
    # process-salted hash used for dict keys, so this is stable across runs and
    # machines (the same reasoning as SyntheticSource).
    rng = random.Random(f"{seed}:{window.name}:{machine_id}")
    rate = 1.0 / window.mean_hours_between_failures

    failures: list[Failure] = []
    elapsed = timedelta(0)
    while True:
        elapsed += timedelta(hours=rng.expovariate(rate))
        if elapsed >= window.lasts:
            return failures
        rule = rules[rng.randrange(len(rules))]
        failures.append(
            Failure(
                machine_id=machine_id,
                at=scenario.starts_at + window.starts_after + elapsed,
                window=window.name,
                rule_id=rule.rule_id,
                component=rule.component,
                symptom_code=rule.symptom_code,
                severity=rule.severity,
                repair_minutes=config.policy.fallback_minutes[model][rule.severity],
            )
        )


def offered_load(
    scenario: SimScenario, window: ArrivalWindow, failures: tuple[Failure, ...]
) -> float:
    """Work arriving in a window over the person-minutes available during it.

    The same ratio ADR-011's gate switches on, computed over a stretch of the run
    rather than a whole shift, so a scenario can be checked against the two
    boundaries in `policy.yaml` instead of being described as busy in a comment.

    Capacity assumes everybody on the roster is present for the whole window.
    That is the optimistic reading, which is the safe one here: it understates
    the load, so a window this calls heavy is heavy under any weaker assumption.
    """
    minutes = sum(failure.repair_minutes for failure in failures if failure.window == window.name)
    capacity = len(scenario.active_technicians) * window.minutes
    if capacity <= 0:
        raise ValueError(
            f"scenario {scenario.name!r} has nobody on shift, so it has no load to speak of"
        )
    return minutes / capacity

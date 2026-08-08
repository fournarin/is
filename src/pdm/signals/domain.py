"""Degradation with a known answer: the port, the curves, and the generator.

Everything here is pure. `SyntheticSource` computes; it performs no I/O and it
never reads a clock. `ReplaySource` and `LiveSource` both touch the world outside
the process and will live in repo.py when they arrive (ADR-030).

What makes this module unusual is that it is not a test fixture. ADR-020 made it
the instrument every prediction accuracy figure in the report is produced by, so
each of its guarantees is a premise of a claim that will be defended in a viva.
They are recorded in ADR-032; the four that shape this file are:

  ground truth is the noise-free curve   noise moves the samples, never the
                                         answer they are scored against
  scenarios are code                     they change per experiment, not when
                                         the plant is rearranged
  no Clock here                          Signal.timestamp is *source* time, from
                                         the scenario's own timeline (ADR-028)
  one profile cannot be predicted        Step exists so that the limitation
                                         ADR-020 requires the report to state
                                         has a test behind it, not a sentence

The four curves are also a claim about what degradation looks like, and nothing
confirms that claim until real data arrives. A predictor tuned until it fits them
perfectly may be a predictor tuned to fit our own assumption.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts import MachineId, Signal

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# The same vocabulary rules.yaml uses. Both are strict: a rule reading "below
# 1.0" must not fire on an interlock sitting at exactly 1.0, which is the whole
# of its healthy state.
Comparison = Literal["above", "below"]


@runtime_checkable
class SignalSource(Protocol):
    """Where signals come from: synthetic, a replay file, or OPC UA (ADR-002).

    The rest of the system talks to this and never learns which is behind it.
    Two things are promised by every implementation:

      * source time never goes backwards between consecutive signals, because
        the rule engine's `for_seconds` debounce measures duration by comparing
        timestamps and cannot do that on an unordered stream;
      * a signal is emitted only once.

    Ground truth is deliberately *not* part of this port. Only the synthetic
    source has any, so measuring ETA error means holding a `SyntheticSource`
    rather than a `SignalSource` (ADR-032).
    """

    def stream(self) -> Iterator[Signal]:
        """Signals in non-decreasing source-time order."""
        ...


# ── the curves ─────────────────────────────────────────────────────────────


def _hours(elapsed: timedelta) -> float:
    return elapsed.total_seconds() / 3600.0


class _Profile(BaseModel):
    """One noise-free degradation curve, and the answer it can be asked.

    `time_until` is the reason this class exists. Reading the crossing time off
    the generated samples instead would make the target depend on the noise: the
    first sample to exceed a threshold is a draw from the noise distribution, so
    an ETA "error" measured against it would carry a term describing the random
    number stream rather than the predictor. Taken from the curve, the target is
    fixed and noise shows up where it belongs, in the spread of the predictions
    (ADR-032).
    """

    model_config = _FROZEN

    baseline: float
    # The value at which the component is considered failed. Optional: for a
    # step failure the jump *is* the failure and there is nothing further to
    # reach.
    failure_value: float | None = None

    @property
    def direction(self) -> int:
        """+1 rising, -1 falling, 0 flat. Every curve here is monotone."""
        raise NotImplementedError

    def value_at(self, elapsed: timedelta) -> float:
        """The true value this many hours into the scenario, before noise."""
        raise NotImplementedError

    def time_until(self, value: float, comparison: Comparison) -> timedelta | None:
        """When the curve first satisfies `above value` / `below value`.

        None means never: either the curve moves the other way, or it moves the
        right way and stops short. Both are legitimate scenarios - a healthy
        machine and a machine that degrades without reaching its threshold - and
        both must be distinguishable from "crosses at hour zero".
        """
        raise NotImplementedError

    @property
    def fails_after(self) -> timedelta | None:
        if self.failure_value is None or self.direction == 0:
            return None
        return self.time_until(self.failure_value, "above" if self.direction > 0 else "below")

    def _satisfied(self, value: float, threshold: float, comparison: Comparison) -> bool:
        return value > threshold if comparison == "above" else value < threshold

    def _wanted_direction(self, comparison: Comparison) -> int:
        return 1 if comparison == "above" else -1

    @model_validator(mode="after")
    def _the_failure_lies_ahead(self) -> _Profile:
        """A declared failure must happen, and must not have happened already.

        ADR-032 makes the failure time the ground truth. A curve that never
        arrives at its failure value has no answer to be scored against, and one
        that starts beyond it describes a scenario beginning with the machine
        already broken - so every prediction would be measured against hour
        zero. Both produce a run that looks entirely normal.
        """
        if self.failure_value is None:
            return self
        fails_after = self.fails_after
        if fails_after is None:
            raise ValueError(
                f"this curve never reaches its failure_value {self.failure_value}, "
                f"so it has no true failure time to measure against (ADR-032)"
            )
        if fails_after == timedelta(0):
            raise ValueError(
                f"this curve starts at or beyond its failure_value {self.failure_value}, "
                f"so the scenario would begin with the machine already failed"
            )
        return self


class Steady(_Profile):
    """A healthy machine. Proves the detector raises nothing on one.

    Without a scenario that never crosses anything, "no false alarms" is a claim
    with no test behind it.
    """

    kind: Literal["steady"] = "steady"

    @property
    def direction(self) -> int:
        return 0

    def value_at(self, elapsed: timedelta) -> float:
        return self.baseline

    def time_until(self, value: float, comparison: Comparison) -> timedelta | None:
        if self._satisfied(self.baseline, value, comparison):
            return timedelta(0)
        return None


class LinearDrift(_Profile):
    """The motor that heats gradually until it fails - ADR-002's own example.

    The case trend extrapolation should get right, and therefore the one that
    says whether the mechanism works at all before any of the harder shapes are
    worth discussing.
    """

    kind: Literal["linear"] = "linear"
    # Units of the metric per hour. Negative for a signal that decays, such as
    # a cooling fan losing speed.
    per_hour: float

    @model_validator(mode="after")
    def _drift_actually_drifts(self) -> LinearDrift:
        if self.per_hour == 0:
            raise ValueError("a linear drift of zero is a Steady profile; use that instead")
        return self

    @property
    def direction(self) -> int:
        return 1 if self.per_hour > 0 else -1

    def value_at(self, elapsed: timedelta) -> float:
        return self.baseline + self.per_hour * _hours(elapsed)

    def time_until(self, value: float, comparison: Comparison) -> timedelta | None:
        if self._satisfied(self.baseline, value, comparison):
            return timedelta(0)
        if self.direction != self._wanted_direction(comparison):
            return None
        return timedelta(hours=(value - self.baseline) / self.per_hour)


class Exponential(_Profile):
    """Degradation that accelerates - a bearing going from worn to failing.

    This is where a straight-line fit predicts **late**, and lateness grows with
    distance. It is the profile that makes ADR-020's requirement to report error
    per forecast horizon mean something: on a linear curve one figure would do,
    and the report would overstate what the method can do.
    """

    kind: Literal["exponential"] = "exponential"
    # Sign gives the direction, size gives how sharply it takes off.
    amplitude: float
    tau_hours: float = Field(gt=0)

    @model_validator(mode="after")
    def _the_curve_goes_somewhere(self) -> Exponential:
        if self.amplitude == 0:
            raise ValueError("an amplitude of zero is a Steady profile; use that instead")
        return self

    @property
    def direction(self) -> int:
        return 1 if self.amplitude > 0 else -1

    def value_at(self, elapsed: timedelta) -> float:
        return self.baseline + self.amplitude * math.expm1(_hours(elapsed) / self.tau_hours)

    def time_until(self, value: float, comparison: Comparison) -> timedelta | None:
        if self._satisfied(self.baseline, value, comparison):
            return timedelta(0)
        if self.direction != self._wanted_direction(comparison):
            return None
        return timedelta(
            hours=self.tau_hours * math.log1p((value - self.baseline) / self.amplitude)
        )


class Step(_Profile):
    """A failure with no leading trend. Nothing here can predict it.

    ADR-020 says the report must state that trend extrapolation cannot catch
    sudden failures rather than leave an impression that everything is
    predictable. Kept as a profile, that sentence is a scenario the predictor is
    run against and measured on, which is a much harder thing to quietly drop
    than a paragraph.
    """

    kind: Literal["step"] = "step"
    delta: float
    after: timedelta = Field(gt=timedelta(0))

    @model_validator(mode="after")
    def _the_step_is_a_step(self) -> Step:
        if self.delta == 0:
            raise ValueError("a step of zero changes nothing; use a Steady profile")
        return self

    @property
    def direction(self) -> int:
        return 1 if self.delta > 0 else -1

    def value_at(self, elapsed: timedelta) -> float:
        return self.baseline if elapsed < self.after else self.baseline + self.delta

    def time_until(self, value: float, comparison: Comparison) -> timedelta | None:
        if self._satisfied(self.baseline, value, comparison):
            return timedelta(0)
        if self.direction != self._wanted_direction(comparison):
            return None
        # The curve attains nothing between the two levels, so a threshold in
        # the gap is never crossed however large the jump looks.
        if self._satisfied(self.baseline + self.delta, value, comparison):
            return self.after
        return None


Profile = Annotated[Steady | LinearDrift | Exponential | Step, Field(discriminator="kind")]


# ── scenarios ──────────────────────────────────────────────────────────────


class Spike(BaseModel):
    """A one-sample excursion: the reason every rule carries `for_seconds`.

    It lasts exactly one sample, so any rule with a debounce longer than the
    sampling interval must ignore it. Without spikes in the generated data that
    debounce cannot be tested on synthetic data at all, and "one noisy reading
    is not a work order" would be an untested promise (ADR-032).
    """

    model_config = _FROZEN

    probability: float = Field(gt=0, le=1)
    # Added to the affected sample. Sign says which way the sensor jumps.
    magnitude: float

    @model_validator(mode="after")
    def _a_spike_moves_the_reading(self) -> Spike:
        if self.magnitude == 0:
            raise ValueError("a spike of zero magnitude is not a spike")
        return self


class Channel(BaseModel):
    """One metric on one machine: what a single sensor tag produces."""

    model_config = _FROZEN

    machine_id: MachineId
    metric_name: str
    unit: str
    profile: Profile

    # Measurement noise, in the units of the metric. Zero is legitimate: a
    # binary interlock signal has no gaussian error.
    noise_sigma: float = Field(default=0.0, ge=0.0)
    spike: Spike | None = None


class Scenario(BaseModel):
    """A stretch of plant history that never happened, with a known ending.

    One sampling interval for the whole scenario. Real tags are read at
    different rates, but nothing in the system needs that yet and a knob with no
    consumer is the pattern lessons_carried.md 4.4 warns about; per-channel rates
    are a change this model can absorb when something asks for them.
    """

    model_config = _FROZEN

    name: str = Field(min_length=1)
    starts_at: datetime
    sample_interval: timedelta = Field(gt=timedelta(0))
    duration: timedelta = Field(gt=timedelta(0))
    channels: tuple[Channel, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _starts_at_is_timezone_aware(self) -> Scenario:
        """Same reasoning as SimulatedClock (ADR-028).

        The night shift crosses midnight, so a naive timestamp gives the wrong
        answer for exactly one shift in three and the right answer for the rest,
        which is the hardest kind of mistake to find.
        """
        if self.starts_at.tzinfo is None:
            raise ValueError("a scenario needs a timezone-aware start time (ADR-028)")
        return self

    @model_validator(mode="after")
    def _the_window_divides_into_whole_samples(self) -> Scenario:
        """Otherwise the last part of the window is never sampled.

        A scenario asked for twelve hours would quietly deliver eleven hours
        fifty-nine, and a crossing timed to land in that gap would produce a run
        where the failure never appears in the data and the ground truth says it
        did.
        """
        if self.duration % self.sample_interval:
            raise ValueError(
                f"duration {self.duration} is not a whole number of "
                f"{self.sample_interval} sampling intervals, so the end of the "
                f"window would never be sampled"
            )
        return self

    @model_validator(mode="after")
    def _one_curve_per_sensor_tag(self) -> Scenario:
        """Two channels on the same tag would interleave two contradictory
        realities into one stream, and the ground truth for that tag would be
        whichever curve was asked."""
        seen: set[tuple[str, str]] = set()
        for channel in self.channels:
            tag = (channel.machine_id, channel.metric_name)
            if tag in seen:
                raise ValueError(f"{channel.machine_id} {channel.metric_name} has two channels")
            seen.add(tag)
        return self

    @property
    def ends_at(self) -> datetime:
        return self.starts_at + self.duration

    @property
    def sample_count(self) -> int:
        """Samples per channel, counting the one at the start."""
        return int(self.duration / self.sample_interval) + 1

    def channel(self, machine_id: MachineId, metric_name: str) -> Channel:
        for channel in self.channels:
            if channel.machine_id == machine_id and channel.metric_name == metric_name:
                return channel
        raise KeyError(f"scenario {self.name!r} has no channel for {machine_id} {metric_name}")


class GroundTruth(BaseModel):
    """What actually happened, taken from the curve rather than the samples.

    `crosses_at` is what a perfect predictor would answer; the error of a real
    one is measured against it. `fails_at` is when the component is finished,
    and is None where the curve declares no failure value - including the step
    failure, where the jump is the event and there is nothing beyond it.

    Both may fall outside the scenario window. A scenario whose crossing lands
    after it ends produces data no rule can fire on, which is worth being able
    to check rather than discover as an empty result.
    """

    model_config = _FROZEN

    machine_id: MachineId
    metric_name: str
    threshold: float
    comparison: Comparison
    crosses_at: datetime | None
    fails_at: datetime | None


class SyntheticSource:
    """Generates a scenario's signals, and can be asked what the answer was.

    Deterministic: the same (scenario, seed) yields the same stream byte for
    byte, however many times it is streamed. Noise is drawn from a generator
    seeded per channel, so adding a machine to a scenario leaves every other
    machine's data untouched and a measurement taken last week stays comparable
    to one taken today.

    It takes no Clock. Timestamps come from the scenario's own timeline, which
    is source time; the Clock supplies decision time and the two are kept apart
    (ADR-028). A source that read the clock would produce different data for the
    same scenario under a compressed demo run, and reproducibility from
    (config + seed) would be gone.
    """

    def __init__(self, scenario: Scenario, seed: int = 0) -> None:
        self._scenario = scenario
        self._seed = seed

    @property
    def scenario(self) -> Scenario:
        return self._scenario

    @property
    def seed(self) -> int:
        return self._seed

    def stream(self) -> Iterator[Signal]:
        """Every channel at every tick, in source-time order.

        Channels sharing a timestamp are emitted in declaration order, which is
        arbitrary but fixed - an arbitrary order that changed between runs would
        break determinism without changing a single value.
        """
        scenario = self._scenario
        generators = [self._generator_for(channel) for channel in scenario.channels]

        for index in range(scenario.sample_count):
            elapsed = scenario.sample_interval * index
            timestamp = scenario.starts_at + elapsed
            for channel, rng in zip(scenario.channels, generators, strict=True):
                yield Signal(
                    timestamp=timestamp,
                    machine_id=channel.machine_id,
                    metric_name=channel.metric_name,
                    value=self._sample(channel, elapsed, rng),
                    unit=channel.unit,
                )

    def ground_truth(
        self,
        machine_id: MachineId,
        metric_name: str,
        *,
        threshold: float,
        comparison: Comparison,
    ) -> GroundTruth:
        """The true crossing and failure times for one tag against one rule."""
        channel = self._scenario.channel(machine_id, metric_name)
        crosses_after = channel.profile.time_until(threshold, comparison)
        fails_after = channel.profile.fails_after
        starts_at = self._scenario.starts_at
        return GroundTruth(
            machine_id=machine_id,
            metric_name=metric_name,
            threshold=threshold,
            comparison=comparison,
            crosses_at=None if crosses_after is None else starts_at + crosses_after,
            fails_at=None if fails_after is None else starts_at + fails_after,
        )

    def _generator_for(self, channel: Channel) -> random.Random:
        # A string seed is hashed with sha512 by CPython rather than the
        # process-salted hash used for dict keys, so this is stable across runs
        # and machines. Anything derived from hash() would not be.
        return random.Random(f"{self._seed}:{channel.machine_id}:{channel.metric_name}")

    def _sample(self, channel: Channel, elapsed: timedelta, rng: random.Random) -> float:
        """One reading: the true value, plus what the sensor adds to it.

        The draws happen in the same order for every sample regardless of the
        values involved, which is what keeps the stream reproducible.
        """
        value = channel.profile.value_at(elapsed)
        if channel.noise_sigma > 0:
            value += rng.gauss(0.0, channel.noise_sigma)
        if channel.spike is not None and rng.random() < channel.spike.probability:
            value += channel.spike.magnitude
        return value


# ── the scenario the demo and the tests run on ─────────────────────────────

# Twelve hours of line A, at one sample a minute. Every machine and metric named
# here exists in config/plant.yaml and is watched by a rule in config/rules.yaml
# - a test enforces that, because a channel no rule reads generates data that
# looks fine and triggers nothing.
#
# The four cases together are the argument that layer 1 works without the plant:
# one crossing predicted well, one predicted late, one not predictable at all,
# and one machine that is simply healthy.
LINE_A_TWELVE_HOURS = Scenario(
    name="line-a-twelve-hours",
    starts_at=datetime.fromisoformat("2026-03-03T06:00:00+00:00"),
    sample_interval=timedelta(minutes=1),
    duration=timedelta(hours=12),
    channels=(
        # ADR-002's motor. Crosses its 85 °C threshold at 07:40 of elapsed time
        # and is finished at hour 11. The spike is a single reading at 87 °C,
        # which the rule's 120-second debounce must throw away.
        Channel(
            machine_id=MachineId("MC-001"),
            metric_name="motor_temp_c",
            unit="degC",
            profile=LinearDrift(baseline=62.0, per_hour=3.0, failure_value=95.0),
            noise_sigma=0.4,
            spike=Spike(probability=0.01, magnitude=25.0),
        ),
        # Accelerating wear: crosses 12.5 A at about hour 4.6 having spent the
        # first two hours looking almost flat. A straight line fitted early
        # predicts this one late, which is the number ADR-020 wants per horizon.
        Channel(
            machine_id=MachineId("MC-004"),
            metric_name="servo_current_a",
            unit="A",
            profile=Exponential(baseline=8.0, amplitude=0.5, tau_hours=2.0, failure_value=15.0),
            noise_sigma=0.15,
        ),
        # The safety interlock at the bottleneck station, open at hour 9 with
        # nothing whatsoever leading up to it. No noise: the signal is 1 or 0.
        # No failure value: the jump is the failure.
        Channel(
            machine_id=MachineId("MC-012"),
            metric_name="interlock_closed",
            unit="bool",
            profile=Step(baseline=1.0, delta=-1.0, after=timedelta(hours=9)),
        ),
        # A falling signal, so that both comparison directions are exercised:
        # the fan reaches 1200 rpm at hour 7.5 and 1100 rpm at hour 10.
        Channel(
            machine_id=MachineId("MC-018"),
            metric_name="fan_rpm",
            unit="rpm",
            profile=LinearDrift(baseline=1500.0, per_hour=-40.0, failure_value=1100.0),
            noise_sigma=12.0,
        ),
        # Healthy for the whole twelve hours, spikes included. Nothing on this
        # machine may reach a technician.
        Channel(
            machine_id=MachineId("MC-018"),
            metric_name="cycle_time_s",
            unit="s",
            profile=Steady(baseline=58.0),
            noise_sigma=0.8,
            spike=Spike(probability=0.02, magnitude=6.0),
        ),
    ),
)

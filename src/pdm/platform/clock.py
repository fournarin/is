"""The single time port for the whole system (ADR-028).

Nothing outside this module may read the operating system clock. Every component
that needs the current time receives a Clock, and the check in
scripts/check_no_wall_clock.py fails CI if that rule is broken anywhere else.

Two axes of time exist in this system and must not be confused:

  source time    Signal.timestamp, the moment a value was measured at the plant
                 or produced by a generator. It arrives with the data.
  decision time  Everything this port returns: detected_at, started_at, the
                 dispatch tick. It is when the *system* acted.

They will not agree once a live signal source is connected, so they are kept
apart from the beginning rather than reconciled later.

Why this exists at all: SyntheticSource has to model degradation that takes
hours or days (ADR-002), while a demo has to show the result in minutes
(ADR-007). Those two requirements are only compatible if time is something the
system is given rather than something it reads from its environment. The same
property is what lets feedback Loop 3 measure ETA error on one timeline, and
what lets the scheduler be replayed against the past in Loop 6.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Reads decision time and waits.

    sleep() is part of the port, not a convenience. The dispatch tick waits five
    minutes between rounds (design.md 3); if it called time.sleep directly, a
    simulated run of one shift would take one shift. Under SimulatedClock the
    same call returns immediately and simply moves the clock forward.
    """

    def now(self) -> datetime:
        """Current decision time. Always timezone-aware and always UTC."""
        ...

    def sleep(self, seconds: float) -> None:
        """Wait for the given duration in whatever way this clock defines it."""
        ...


class SystemClock:
    """Real time. The only implementation used in production."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError(f"cannot sleep for a negative duration: {seconds}")
        time.sleep(seconds)


class ScaledClock:
    """Real time, running fast. What a compressed demo runs on (ADR-044 §4).

    A twelve-hour degradation has to be watchable in one sitting (ADR-007) and
    the system has to keep sleeping, claiming and heartbeating in real seconds
    while it happens - which `SimulatedClock` cannot do, because its `sleep`
    returns instantly and the worker would spin.

    **Compressing time is this port's job, and nothing else's.** The first
    version of the trigger loop put a speed factor on the signal feed instead,
    handing signals over faster while decision time ran at one second per second.
    Every window in the system is measured on decision time - the cooldown, the
    ETA a ticket shows, the expiry sweep - so at 60x a ticket said "in about six
    hours" for something six minutes away, and a prediction could never reach its
    own expiry. Moving the factor here leaves one axis and one knob: source time
    and decision time advance together, exactly as they do in the plant.

    Elapsed time comes from a monotonic counter rather than from repeated calls
    to the wall clock, so an NTP step does not move a demo's whole timeline.
    """

    def __init__(self, speed: float, *, origin: datetime | None = None) -> None:
        if speed <= 0:
            raise ValueError(f"a clock's speed must be positive, not {speed}")
        if origin is not None and origin.tzinfo is None:
            raise ValueError("ScaledClock needs a timezone-aware origin (ADR-028)")
        self._speed = speed
        self._origin = (origin or datetime.now(UTC)).astimezone(UTC)  # allow: wall-clock
        self._started = time.monotonic()

    @property
    def speed(self) -> float:
        return self._speed

    def now(self) -> datetime:
        return self._origin + timedelta(seconds=(time.monotonic() - self._started) * self._speed)

    def sleep(self, seconds: float) -> None:
        """Wait `seconds` of *this* clock's time, which is less real time.

        So a worker asked to poll every ten seconds polls every ten scaled
        seconds. The queue, the reaper and the trigger tick all keep the timings
        `policy.yaml` gives them, measured on the timeline the run is on.
        """
        if seconds < 0:
            raise ValueError(f"cannot sleep for a negative duration: {seconds}")
        time.sleep(seconds / self._speed)


class SimulatedClock:
    """Time that only moves when something asks it to.

    Used by the simulator, by tests and by compressed demo runs. It is
    event-driven rather than a multiple of real time: a scenario covering
    thirty hours costs the same microseconds as one covering thirty seconds,
    which is what makes hundreds of scenarios per CI run affordable
    (design.md 7).

    Time never moves backwards. Finding cooldowns, ETA expiry and elapsed wait
    time (the w4 term in the score) all assume a monotonic timeline, and a clock
    that could rewind would corrupt them in ways no test would notice.
    """

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError(
                "SimulatedClock needs a timezone-aware start time. "
                "The plant runs three shifts and the night shift crosses midnight, "
                "so naive datetimes give wrong shift capacity for exactly one "
                "shift and correct answers for the rest, which is the hardest "
                "kind of bug to find (ADR-028)."
            )
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def sleep(self, seconds: float) -> None:
        self.advance(timedelta(seconds=seconds))

    def advance(self, delta: timedelta) -> datetime:
        """Move forward by delta and return the new time."""
        if delta < timedelta(0):
            raise ValueError(f"time cannot move backwards: {delta}")
        self._now += delta
        return self._now

    def advance_to(self, moment: datetime) -> datetime:
        """Move forward to an absolute moment and return it."""
        if moment.tzinfo is None:
            raise ValueError("advance_to needs a timezone-aware datetime")
        target = moment.astimezone(UTC)
        if target < self._now:
            raise ValueError(f"time cannot move backwards: {self._now} -> {target}")
        self._now = target
        return self._now

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

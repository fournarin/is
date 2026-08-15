"""Where the two time axes meet: source time in, decision time out (ADR-044 §4).

A `SignalSource` yields a scenario as fast as it is iterated - twelve hours of
line A in a few milliseconds. A loop that consumed that would not be a loop; it
would raise every Finding of the run in one instant, stamped with one decision
time, and the behaviour being demonstrated would be gone. The scenario's timeline
is also somebody else's: it starts in March, and the process reading it does not.

This module holds the mapping between the two, and it is the only place in the
system where they touch:

    source_due = source_origin + (now - decision_origin) x speed

**A signal's timestamp is never modified.** It is what the debounce measures
duration with, and what `SyntheticSource.ground_truth()` is anchored to
(ADR-032); restamping it as "now" would produce a run whose ETA error could not
be compared against any figure in `docs/prediction-baseline.md`. What this
changes is *when* a signal is handed over, never what it says.

Pure, and holds no Clock: `due()` is given the decision time, like every other
function in the system that needs one (ADR-028).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta

from pdm.contracts import Signal
from pdm.signals.domain import SignalSource


class Feed:
    """One source, paced against decision time.

    `speed` is what makes ADR-007's demo and ADR-002's twelve-hour degradation
    compatible: at 60x a shift's worth of wear is watchable in twelve minutes,
    and a `SimulatedClock` compresses it further with no change here. At 1.0 the
    scenario runs at plant speed, which is what a replay of a real day wants.

    The origin is fixed at construction rather than at the first call, so that a
    process which starts and then waits does not silently rewind its own
    timeline.
    """

    __slots__ = ("_ahead", "_decision_origin", "_done", "_iterator", "_source_origin", "_speed")

    def __init__(
        self,
        source: SignalSource,
        *,
        decision_origin: datetime,
        speed: float = 1.0,
    ) -> None:
        if speed <= 0:
            raise ValueError(f"a feed's speed must be positive, not {speed}")
        if decision_origin.tzinfo is None:
            raise ValueError("a feed needs a timezone-aware origin (ADR-028)")
        self._iterator: Iterator[Signal] = iter(source.stream())
        self._decision_origin = decision_origin
        self._speed = speed
        # One signal of lookahead: read to learn where the source's timeline
        # begins, then held until it is due. Read lazily, because constructing a
        # feed must not start a generator that may open a file or a connection.
        self._ahead: Signal | None = None
        self._source_origin: datetime | None = None
        self._done = False

    @property
    def exhausted(self) -> bool:
        """The source has ended and everything it produced has been handed over.

        Nothing restarts it. Replaying a run that already happened would re-raise
        findings for failures the same data already showed (ADR-044 §4).
        """
        return self._done and self._ahead is None

    def due(self, now: datetime) -> list[Signal]:
        """Every signal whose source time has arrived by `now`, in stream order.

        A clock that has not moved yields nothing, because everything up to the
        previous horizon has already been handed over - so no guard against a
        repeated or rewound `now` is needed, and none is written.

        **A long stall produces one large batch**, not a truncated one. On a
        replay the data still has to pass through, and a live source has no
        backlog to hand over in the first place; capping it would be a constant
        with no source and a stream with a silent hole in it.
        """
        if self._peek() is None:
            return []
        assert self._source_origin is not None

        elapsed = timedelta(seconds=(now - self._decision_origin).total_seconds() * self._speed)
        horizon = self._source_origin + elapsed

        batch: list[Signal] = []
        while True:
            head = self._peek()
            if head is None or head.timestamp > horizon:
                return batch
            batch.append(head)
            self._ahead = None

    def _peek(self) -> Signal | None:
        if self._ahead is None and not self._done:
            self._ahead = next(self._iterator, None)
            if self._ahead is None:
                self._done = True
            elif self._source_origin is None:
                self._source_origin = self._ahead.timestamp
        return self._ahead

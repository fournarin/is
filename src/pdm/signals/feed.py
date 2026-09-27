"""Where the two time axes meet: source time in, decision time out (ADR-044 §4).

A `SignalSource` yields a scenario as fast as it is iterated - twelve hours of
line A in a few milliseconds. A loop that consumed that would not be a loop; it
would raise every Finding of the run in one instant, stamped with one decision
time, and the behaviour being demonstrated would be gone. The scenario's timeline
is also somebody else's: it starts in March, and the process reading it does not.

This module holds the mapping between the two, and it is the only place in the
system where they touch:

    source_due = source_origin + (now - decision_origin)

One second of decision time buys one second of scenario, and **compression is
the Clock's job** (`ScaledClock`). This was a `speed` factor here first, which
put the two axes at different rates: every window in the system is measured on
decision time - the cooldown, the ETA on a ticket, the expiry sweep - so at 60x
a ticket read "in about six hours" for something six minutes away, and a
prediction could never reach its own expiry. One knob, in the port built for it.

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

    The origin is fixed at construction rather than at the first call, so that a
    process which starts and then waits does not silently rewind its own
    timeline. How fast that timeline moves is the clock's business: under a
    `ScaledClock` at 60x, a shift's worth of wear arrives in twelve minutes and
    nothing here changes.
    """

    __slots__ = (
        "_ahead",
        "_decision_origin",
        "_done",
        "_head_start",
        "_iterator",
        "_source_origin",
    )

    def __init__(
        self,
        source: SignalSource,
        *,
        decision_origin: datetime,
        head_start: timedelta = timedelta(0),
    ) -> None:
        if decision_origin.tzinfo is None:
            raise ValueError("a feed needs a timezone-aware origin (ADR-028)")
        self._iterator: Iterator[Signal] = iter(source.stream())
        self._decision_origin = decision_origin
        # How far into the source the feed begins (ADR-094). The readings before
        # it are handed over on the first call, as one batch, so the trend is
        # there to be read; what follows arrives at the clock's own pace.
        if head_start < timedelta(0):
            raise ValueError("a head start cannot be negative")
        self._head_start = head_start
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

        horizon = self._source_origin + self._head_start + (now - self._decision_origin)

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

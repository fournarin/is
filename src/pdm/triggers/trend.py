"""Fitting a line to a signal and asking when it meets the threshold (ADR-043).

Pure, and deliberately small: an ordinary least squares fit, its residual
standard error, and the crossing time that follows. Six lines of algebra rather
than a dependency, because ADR-008 asks for a record before a dependency and
this would not earn one.

**The interval is the part that matters.** It reaches a technician as "expected
in about six hours, give or take two", and somebody decides whether to stop the
line tonight on the width of that window. It is one standard error of the fit
propagated to the crossing - stated as that, and not as a claim about how often
the event lands inside it (ADR-043 section 3).

What this cannot do is written into ADR-020 and ADR-032 and worth repeating
where the code is: a curve with no leading trend - the interlock that jumps from
closed to open - is invisible here, and no amount of fitting changes that.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from itertools import pairwise

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import MachineId, Signal

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# One reading, as the fit sees it: hours since the window's first sample, and a
# value. Hours rather than seconds so a slope reads as "degrees per hour", which
# is the unit a rule's threshold is discussed in.
Sample = tuple[float, float]

# What a window is keyed by: the same channel a Signal names.
ChannelKey = tuple[MachineId, str]


class Fit(BaseModel):
    """A line through the window, with how well it fits.

    `slope_error` is the standard error of the slope, not a confidence interval.
    Everything downstream that widens it into one has to say so.
    """

    model_config = _FROZEN

    intercept: float
    slope_per_hour: float
    slope_error: float = Field(ge=0.0)
    samples: int = Field(ge=2)
    span: timedelta

    @property
    def is_flat(self) -> bool:
        """A slope of exactly zero cannot reach anything it is not already at."""
        return self.slope_per_hour == 0.0


class Crossing(BaseModel):
    """When the fitted line meets the threshold, and how uncertain that is.

    `earliest` and `latest` come from the slope's own standard error, so the
    width is a property of the data rather than a fraction of the horizon
    somebody chose (ADR-043 section 3).
    """

    model_config = _FROZEN

    at: datetime
    earliest: datetime
    latest: datetime
    fit: Fit
    # How often this channel is read. The interval is never reported as
    # narrower than this: a perfectly clean line has a slope error of zero and
    # would otherwise say "give or take 0 minutes", which is a claim to know the
    # future to the second from data sampled once a minute. Derived from the
    # readings rather than configured, so no constant was invented for it.
    resolution: timedelta = timedelta(0)

    @property
    def interval(self) -> timedelta:
        """Half the width, which is what "give or take" means on a screen."""
        from_fit = max(self.at - self.earliest, self.latest - self.at)
        return max(from_fit, self.resolution)


class Window:
    """The recent samples of one channel. Mutable, held by the loop.

    Bounded by time rather than by count: `window_minutes` from `policy.yaml` is
    a statement about how much history the trend should reflect, and a sample
    count would mean something different for a channel read every ten seconds
    than for one read every minute.

    Forgotten on restart, like the debounce, and for the same reason (ADR-042
    section 1): the alternative is writing every sample of every channel to a
    table to save one window of history.
    """

    __slots__ = ("_by_channel", "_span")

    def __init__(self, span: timedelta) -> None:
        self._span = span
        self._by_channel: dict[ChannelKey, deque[tuple[datetime, float]]] = {}

    def add(self, signal: Signal) -> list[tuple[datetime, float]]:
        """Record a reading and return the window it now belongs to.

        A sample older than the newest by more than the span is dropped, so a
        stream that stops and restarts hours later fits a line through the new
        data rather than through a gap.
        """
        key: ChannelKey = (signal.machine_id, signal.metric_name)
        readings = self._by_channel.setdefault(key, deque())

        # Source time can repeat but never goes backwards (ADR-002's promise); a
        # sample that predates the window's newest is treated as a new stream
        # rather than reordered, because reordering here would silently repair
        # data the caller should be told about.
        if readings and signal.timestamp < readings[-1][0]:
            readings.clear()

        readings.append((signal.timestamp, signal.value))
        cutoff = signal.timestamp - self._span
        while readings and readings[0][0] < cutoff:
            readings.popleft()
        return list(readings)

    def clear(self, machine_id: MachineId, metric_name: str) -> None:
        self._by_channel.pop((machine_id, metric_name), None)


def fit(readings: Sequence[tuple[datetime, float]]) -> Fit | None:
    """Least squares through the window, or None if there is nothing to fit.

    None where fewer than two samples exist, or where every sample shares a
    timestamp - a vertical line has no slope, and the caller asking "when will
    this reach the threshold" has no answer rather than an infinite one.
    """
    if len(readings) < 2:
        return None

    origin = readings[0][0]
    points: list[Sample] = [
        ((timestamp - origin).total_seconds() / 3600.0, value) for timestamp, value in readings
    ]
    count = len(points)
    mean_x = sum(x for x, _ in points) / count
    mean_y = sum(y for _, y in points) / count

    variance_x = sum((x - mean_x) ** 2 for x, _ in points)
    if variance_x == 0.0:
        return None

    covariance = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope = covariance / variance_x
    intercept = mean_y - slope * mean_x

    # Residual standard error, and from it the standard error of the slope. With
    # two points the residuals are zero by construction and the error is zero,
    # which is honest: two points determine a line exactly, and the caller's
    # `min_samples` is what decides whether two is enough to believe.
    residuals = sum((y - (intercept + slope * x)) ** 2 for x, y in points)
    degrees_of_freedom = count - 2
    if degrees_of_freedom <= 0:
        slope_error = 0.0
    else:
        slope_error = math.sqrt((residuals / degrees_of_freedom) / variance_x)

    return Fit(
        intercept=intercept,
        slope_per_hour=slope,
        slope_error=slope_error,
        samples=count,
        span=readings[-1][0] - readings[0][0],
    )


def _resolution(readings: Sequence[tuple[datetime, float]]) -> timedelta:
    """The typical gap between readings: how finely this channel is observed.

    The median rather than the mean, so one gap in a stream that stopped and
    restarted does not widen every interval afterwards.
    """
    if len(readings) < 2:
        return timedelta(0)
    gaps = sorted(later[0] - earlier[0] for earlier, later in pairwise(readings))
    return gaps[len(gaps) // 2]


def _hours_to(value: float, threshold: float, slope: float) -> float | None:
    """When a line at `value` moving at `slope` reaches `threshold`.

    None where it never does: a slope of zero, or one pointing away.
    """
    if slope == 0.0:
        return None
    hours = (threshold - value) / slope
    return hours if hours > 0 else None


def crossing(
    readings: Sequence[tuple[datetime, float]],
    *,
    threshold: float,
    comparison: str,
    now: datetime,
    horizon: timedelta,
    min_samples: int,
) -> Crossing | None:
    """When this channel is expected to breach, if that can be said at all.

    Returns None - the common case, and not a failure - when any of ADR-043's
    three conditions is unmet: too few samples, a slope pointing the wrong way, a
    value already past the threshold (that is a detection, and both firing would
    be two work orders for one fault), or an interval that does not fit inside
    the horizon.

    **The interval is the gate.** A slope indistinguishable from noise produces
    an interval wider than any horizon, so it fails the same test that rejects a
    forecast too far out - and no significance multiplier had to be invented to
    say so (ADR-043 section 2).
    """
    if len(readings) < min_samples:
        return None

    line = fit(readings)
    if line is None or line.is_flat:
        return None

    latest_at, latest_value = readings[-1]

    # Already past it: that is the detection rule's business, and a prediction of
    # something that has happened is not a prediction.
    if (comparison == "above" and latest_value > threshold) or (
        comparison == "below" and latest_value < threshold
    ):
        return None

    # The slope has to point at the threshold.
    if (comparison == "above" and line.slope_per_hour <= 0) or (
        comparison == "below" and line.slope_per_hour >= 0
    ):
        return None

    # From the fitted line at the last reading, not from the reading itself
    # (ADR-043 section 3). The fit is what was believed about the channel; the
    # last sample is one draw from the noise around it, and letting it set the
    # ETA moves the answer by half an hour while the interval - computed from the
    # slope - stays a few minutes wide. A number that precise and that unstable
    # is worse than a wider one.
    fitted_now = line.intercept + line.slope_per_hour * (
        (latest_at - readings[0][0]).total_seconds() / 3600.0
    )
    if (comparison == "above" and fitted_now > threshold) or (
        comparison == "below" and fitted_now < threshold
    ):
        return None

    hours = _hours_to(fitted_now, threshold, line.slope_per_hour)
    if hours is None:
        return None

    # The two ends of the interval: the fastest and slowest the slope's own
    # standard error allows. A steeper slope arrives sooner, a shallower one
    # later - and a shallower one that changes sign never arrives at all, which
    # is what `None` from `_hours_to` means here.
    steeper = line.slope_per_hour + math.copysign(line.slope_error, line.slope_per_hour)
    shallower = line.slope_per_hour - math.copysign(line.slope_error, line.slope_per_hour)
    soonest = _hours_to(fitted_now, threshold, steeper)
    latest = _hours_to(fitted_now, threshold, shallower)
    if soonest is None or latest is None:
        return None

    # Bounded in hours, before anything becomes a datetime. A channel drifting at
    # a billionth of a degree an hour has a crossing a hundred thousand years out,
    # and `timedelta(hours=that)` raises OverflowError - which would abort the
    # whole batch, on the most boring possible input.
    horizon_hours = horizon.total_seconds() / 3600.0
    if latest > horizon_hours or hours > horizon_hours:
        return None

    at = latest_at + timedelta(hours=hours)
    earliest_at = latest_at + timedelta(hours=soonest)
    latest_end = latest_at + timedelta(hours=latest)

    return Crossing(
        at=at, earliest=earliest_at, latest=latest_end, fit=line, resolution=_resolution(readings)
    )


def describe(crossing_found: Crossing, *, metric_name: str, threshold: float) -> str:
    """The sentence a technician reads, with the interval never dropped.

    "In about six hours" reads as more trustworthy than "in about six hours, give
    or take two", and the second one is the truth (ui.md 2.2, ADR-020).
    """
    hours = crossing_found.interval.total_seconds() / 3600.0
    give_or_take = (
        f"{int(crossing_found.interval.total_seconds() // 60)} minutes"
        if hours < 1.5
        else f"{hours:.1f} hours"
    )
    return (
        f"{metric_name} is trending at {crossing_found.fit.slope_per_hour:+.2f} per hour and is "
        f"expected to reach {threshold} at {crossing_found.at:%Y-%m-%d %H:%M} UTC, give or take "
        f"{give_or_take}, fitted over {crossing_found.fit.samples} readings"
    )


def evidence_for(
    crossing_found: Crossing, *, threshold: float, comparison: str
) -> dict[str, object]:
    """What the prediction was made from, kept with it.

    The slope and its error rather than the readings themselves: the window is
    gone by the time anybody reads this, and the two numbers are what the
    forecast was, while the readings are only where it came from.
    """
    return {
        "slope_per_hour": crossing_found.fit.slope_per_hour,
        "slope_error": crossing_found.fit.slope_error,
        "samples": crossing_found.fit.samples,
        "fitted_over_seconds": int(crossing_found.fit.span.total_seconds()),
        "threshold": threshold,
        "comparison": comparison,
        "earliest": crossing_found.earliest.isoformat(),
        "latest": crossing_found.latest.isoformat(),
    }


def windows_of(signals: Iterable[Signal], span: timedelta) -> Window:
    """A window pre-filled from a stream. For measurement scripts and tests."""
    window = Window(span)
    for signal in signals:
        window.add(signal)
    return window

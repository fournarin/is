"""Measure ETA error against the curve that generated the data (ADR-020, ADR-043).

Run by hand:

    PYTHONPATH=. uv run python scripts/measure_prediction.py

No database and no model, so this one *could* run in CI - and does not, for the
same reason the others do not: it is a measurement whose output belongs in a
document with a date on it, and a number that changes silently on every commit is
a number nobody trusts.

**What is measured.** For every channel of the demo scenario, the trend is fitted
at every sample and asked when the rule's threshold will be crossed. Each answer
is compared against `SyntheticSource.ground_truth()`, which is the crossing of
the noise-free curve (ADR-032 §1) - so the error measured is the predictor's and
not the generator's random number stream.

**Reported per horizon**, because accuracy falls with distance and one figure
hides that (ADR-020). The buckets are how far ahead the prediction was made, not
how far ahead it turned out to be.

**Across seeds, magnitudes and a baseline.** The signed mean lets early and
late cancel, so each bucket also reports the mean absolute error and the 90th
percentile of |error|, pooled over `SEEDS`. The baseline is a straight line
through the first and last reading in the same window, with no fit and no
interval gate, asked at the same moments the trend answered - so the two
columns are paired and differ only in the method.

**Write the output into `docs/prediction-baseline.md` when it changes.**
"""

from __future__ import annotations

import math
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path

from pdm.contracts import MachineId
from pdm.platform.config import load_config
from pdm.platform.config.schema import RuleConfig
from pdm.signals import LINE_A_TWELVE_HOURS, Scenario, SyntheticSource
from pdm.signals.domain import Comparison
from pdm.triggers.trend import Window, crossing

# Horizon buckets, in hours. Chosen to straddle the scenario's own timescale
# rather than to make a table look tidy: the demo is twelve hours long and the
# rules' crossings land between two and ten hours in.
BUCKETS: tuple[tuple[str, timedelta, timedelta], ...] = (
    ("0-1h", timedelta(0), timedelta(hours=1)),
    ("1-3h", timedelta(hours=1), timedelta(hours=3)),
    ("3-6h", timedelta(hours=3), timedelta(hours=6)),
    ("6-12h", timedelta(hours=6), timedelta(hours=12)),
    ("12h+", timedelta(hours=12), timedelta(days=365)),
)


def _bucket(ahead: timedelta) -> str:
    for name, low, high in BUCKETS:
        if low <= ahead < high:
            return name
    return BUCKETS[-1][0]


SEEDS: tuple[int, ...] = (20260813, *range(20))


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def _two_point_eta(readings: Sequence[tuple[datetime, float]], threshold: float) -> datetime | None:
    """The baseline: a line through the window's first and last reading."""
    (first_at, first), (last_at, last) = readings[0], readings[-1]
    hours = (last_at - first_at).total_seconds() / 3600.0
    if hours <= 0 or last == first:
        return None
    ahead = (threshold - last) / ((last - first) / hours)
    return last_at + timedelta(hours=ahead) if ahead >= 0 else None


Measured = dict[str, list[tuple[float, float, str, str]]]


def measure(scenario: Scenario, seed: int) -> Measured:
    """Every prediction the mechanism would have made, with its signed error.

    Signed, and never absolute-valued before the mean: on an accelerating curve a
    straight line predicts **late**, and taking magnitudes first would hide the
    direction that tells a reader which shapes this method is wrong about.
    """
    config = load_config(Path("config"))
    policy = config.policy.triggers.trend
    source = SyntheticSource(scenario, seed=seed)

    by_bucket: Measured = defaultdict(list)
    windows = Window(timedelta(minutes=policy.window_minutes))
    horizon = timedelta(hours=policy.max_horizon_hours)

    rules_by_channel: dict[tuple[MachineId, str], list[RuleConfig]] = defaultdict(list)
    for rule in config.rules.rules:
        for channel in scenario.channels:
            if channel.metric_name == rule.metric_name and rule.machine_model == config.model_of(
                channel.machine_id
            ):
                rules_by_channel[(channel.machine_id, channel.metric_name)].append(rule)

    truths: dict[tuple[MachineId, str, str], datetime | None] = {}

    for signal in source.stream():
        readings = windows.add(signal)
        for rule in rules_by_channel.get((signal.machine_id, signal.metric_name), []):
            found = crossing(
                readings,
                threshold=rule.threshold,
                comparison=rule.comparison,
                now=signal.timestamp,
                horizon=horizon,
                min_samples=policy.min_samples,
            )
            if found is None:
                continue

            key = (signal.machine_id, signal.metric_name, rule.rule_id)
            if key not in truths:
                # The comparison is a string in config and a Literal here: the
                # config schema already restricts it to the same two words, so
                # this is a cast rather than a check.
                comparison: Comparison = "above" if rule.comparison == "above" else "below"
                truth = source.ground_truth(
                    signal.machine_id,
                    signal.metric_name,
                    threshold=rule.threshold,
                    comparison=comparison,
                )
                truths[key] = truth.crosses_at
            crosses_at = truths[key]
            if crosses_at is None:
                # The curve never crosses: every prediction here is a false
                # alarm, and counted as one rather than as an error of unknown
                # size.
                by_bucket["never crosses"].append(
                    (math.nan, math.nan, str(signal.machine_id), str(rule.rule_id))
                )
                continue

            ahead = found.at - signal.timestamp
            error = _minutes(found.at - crosses_at)
            baseline_at = _two_point_eta(readings, rule.threshold)
            baseline = math.nan if baseline_at is None else _minutes(baseline_at - crosses_at)
            by_bucket[_bucket(ahead)].append(
                (error, baseline, str(signal.machine_id), str(rule.rule_id))
            )

    return by_bucket


def _p90(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(0.9 * len(ordered)) - 1)]


def main() -> int:
    print(f"measured {datetime.now().astimezone().date().isoformat()}")
    print(f"scenario {LINE_A_TWELVE_HOURS.name}, seeds {SEEDS[0]} and 0-{len(SEEDS) - 2}\n")

    by_bucket: Measured = defaultdict(list)
    for seed in SEEDS:
        for name, rows in measure(LINE_A_TWELVE_HOURS, seed=seed).items():
            by_bucket[name] += rows

    header = (
        f"{'horizon':8} {'n':>6} {'mean':>8} {'MAE':>7} {'P90|e|':>7} {'worst':>8}"
        f"   {'base n':>6} {'base MAE':>8} {'base P90':>8}"
    )
    print(header)
    print("-" * len(header))

    for name, _, _ in BUCKETS:
        rows = by_bucket.get(name, [])
        if not rows:
            print(f"{name:8} {0:>6}")
            continue
        errors = [error for error, _, _, _ in rows]
        magnitudes = [abs(error) for error in errors]
        worst = max(errors, key=abs)
        base = [abs(b) for _, b, _, _ in rows if not math.isnan(b)]
        base_text = (
            f"{len(base):>6} {sum(base) / len(base):>7.1f}m {_p90(base):>7.1f}m"
            if base
            else f"{0:>6}"
        )
        print(
            f"{name:8} {len(rows):>6} {sum(errors) / len(errors):>7.1f}m "
            f"{sum(magnitudes) / len(magnitudes):>6.1f}m {_p90(magnitudes):>6.1f}m "
            f"{worst:>7.1f}m   {base_text}"
        )

    false_alarms = by_bucket.get("never crosses", [])
    print(f"\npredictions on channels that never cross: {len(false_alarms)}")
    for channel in sorted({f"{machine}/{rule}" for _, _, machine, rule in false_alarms}):
        print(f"  {channel}")

    print(
        "\nmean is signed (positive late, negative early) so the direction shows\n"
        "(ADR-020); MAE and P90 are of |error|, so early and late do not cancel.\n"
        "base: a line through the window's first and last reading, asked at the\n"
        "same moments; n differs where it points away from the threshold."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

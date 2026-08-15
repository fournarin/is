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

**Write the output into `docs/prediction-baseline.md` when it changes.**
"""

from __future__ import annotations

import sys
from collections import defaultdict
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


def _minutes(delta: timedelta) -> float:
    return delta.total_seconds() / 60.0


def measure(scenario: Scenario, seed: int) -> dict[str, list[tuple[float, str, str]]]:
    """Every prediction the mechanism would have made, with its signed error.

    Signed, and never absolute-valued before the mean: on an accelerating curve a
    straight line predicts **late**, and taking magnitudes first would hide the
    direction that tells a reader which shapes this method is wrong about.
    """
    config = load_config(Path("config"))
    policy = config.policy.triggers.trend
    source = SyntheticSource(scenario, seed=seed)

    by_bucket: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
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
                    (float("nan"), str(signal.machine_id), str(rule.rule_id))
                )
                continue

            ahead = found.at - signal.timestamp
            error = _minutes(found.at - crosses_at)
            by_bucket[_bucket(ahead)].append((error, str(signal.machine_id), str(rule.rule_id)))

    return by_bucket


def main() -> int:
    print(f"measured {datetime.now().astimezone().date().isoformat()}")
    print(f"scenario {LINE_A_TWELVE_HOURS.name}, seed 20260813\n")

    by_bucket = measure(LINE_A_TWELVE_HOURS, seed=20260813)

    header = f"{'horizon':12} {'n':>5} {'mean err':>10} {'median':>9} {'worst':>9}  channels"
    print(header)
    print("-" * len(header))

    for name, _, _ in BUCKETS:
        rows = by_bucket.get(name, [])
        if not rows:
            print(f"{name:12} {0:>5}          -         -         -")
            continue
        errors = sorted(error for error, _, _ in rows)
        mean = sum(errors) / len(errors)
        median = errors[len(errors) // 2]
        worst = max(errors, key=abs)
        channels = sorted({f"{machine}/{rule}" for _, machine, rule in rows})
        print(
            f"{name:12} {len(rows):>5} {mean:>9.1f}m {median:>8.1f}m {worst:>8.1f}m  "
            f"{', '.join(channels)}"
        )

    false_alarms = by_bucket.get("never crosses", [])
    print(f"\npredictions on channels that never cross: {len(false_alarms)}")
    if false_alarms:
        for channel in sorted({f"{machine}/{rule}" for _, machine, rule in false_alarms}):
            print(f"  {channel}")

    print(
        "\nError is signed: positive is late, negative is early. Taking magnitudes\n"
        "first would hide the direction, which is the thing that says which shapes\n"
        "of degradation this method is wrong about (ADR-020)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

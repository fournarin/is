"""Fitting a line and asking when it meets the threshold (ADR-043).

Two kinds of test here. The first kind uses hand-built readings where the answer
is known by arithmetic - a line rising two degrees an hour from 80 reaches 85 in
two and a half hours, and if the code says otherwise the code is wrong. The
second kind uses `SyntheticSource`, whose ground truth comes from the noise-free
curve (ADR-032), so a prediction can be compared against what was actually going
to happen rather than against another guess.

The rejections matter as much as the predictions. A mechanism that answers
every question produces a forecast for the interlock that jumps from closed to
open, and that forecast would be a fabrication with a confidence interval on it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pdm.contracts import MachineId
from pdm.signals import LINE_A_TWELVE_HOURS, SyntheticSource
from pdm.triggers.trend import Window, crossing, describe, fit

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-001")
HORIZON = timedelta(hours=24)


def _readings(
    values: list[float], *, every: timedelta = timedelta(minutes=10), start: datetime = NOW
) -> list[tuple[datetime, float]]:
    return [(start + every * index, value) for index, value in enumerate(values)]


def _rising(
    *,
    per_hour: float,
    start_value: float,
    count: int = 13,
    every: timedelta = timedelta(minutes=10),
) -> list[tuple[datetime, float]]:
    """A clean line. Ten-minute samples over two hours by default."""
    step = per_hour * (every.total_seconds() / 3600.0)
    return _readings([start_value + step * index for index in range(count)], every=every)


class TestTheFitItself:
    def test_a_clean_line_recovers_its_slope(self) -> None:
        line = fit(_rising(per_hour=2.0, start_value=80.0))

        assert line is not None
        assert line.slope_per_hour == pytest.approx(2.0)
        assert line.intercept == pytest.approx(80.0)

    def test_a_clean_line_has_no_uncertainty_in_its_slope(self) -> None:
        """Which is true, and is why the interval cannot be the only gate: a
        perfectly straight line says nothing about whether the machine will keep
        behaving like one."""
        line = fit(_rising(per_hour=2.0, start_value=80.0))

        assert line is not None
        assert line.slope_error == pytest.approx(0.0, abs=1e-9)

    def test_scatter_widens_the_standard_error(self) -> None:
        clean = fit(_rising(per_hour=2.0, start_value=80.0))
        noisy = fit(
            _readings([80.0, 81.0, 80.5, 82.5, 81.0, 84.0, 82.0, 85.5, 83.0, 87.0, 84.0, 88.5])
        )

        assert clean is not None and noisy is not None
        assert noisy.slope_error > clean.slope_error

    def test_one_reading_is_not_a_trend(self) -> None:
        assert fit(_readings([80.0])) is None

    def test_readings_that_all_share_a_timestamp_have_no_slope(self) -> None:
        """A vertical line has no answer to "when will it reach 85", and an
        infinite one would be worse than none."""
        assert fit([(NOW, 80.0), (NOW, 81.0), (NOW, 82.0)]) is None


class TestWhenTheCrossingIsReported:
    def test_a_rising_line_predicts_the_arithmetic_answer(self) -> None:
        """80 degrees rising at 2 per hour reaches 85 in two and a half hours,
        measured from the last reading rather than the first."""
        readings = _rising(per_hour=2.0, start_value=80.0)

        found = crossing(
            readings,
            threshold=85.0,
            comparison="above",
            now=readings[-1][0],
            horizon=HORIZON,
            min_samples=10,
        )

        assert found is not None
        assert found.at == readings[-1][0] + timedelta(hours=0.5)

    def test_a_falling_line_predicts_a_below_threshold(self) -> None:
        readings = _rising(per_hour=-50.0, start_value=1400.0)

        found = crossing(
            readings,
            threshold=1200.0,
            comparison="below",
            now=readings[-1][0],
            horizon=HORIZON,
            min_samples=10,
        )

        assert found is not None
        assert found.at > readings[-1][0]

    def test_the_interval_is_carried_and_never_zero_width_on_real_data(self) -> None:
        readings = _readings([80.0, 80.9, 81.4, 82.6, 83.0, 84.2, 84.6, 85.9, 86.2, 87.4, 88.1])

        found = crossing(
            readings,
            threshold=92.0,
            comparison="above",
            now=readings[-1][0],
            horizon=HORIZON,
            min_samples=10,
        )

        assert found is not None
        assert found.interval > timedelta(0)
        assert found.earliest < found.at < found.latest


class TestWhatIsRefused:
    """Each of these would be a fabrication with a confidence interval on it."""

    def test_a_value_already_past_the_threshold_is_a_detection_not_a_forecast(self) -> None:
        """Both firing would be two work orders for one fault."""
        readings = _rising(per_hour=2.0, start_value=90.0)

        assert (
            crossing(
                readings,
                threshold=85.0,
                comparison="above",
                now=readings[-1][0],
                horizon=HORIZON,
                min_samples=10,
            )
            is None
        )

    def test_a_slope_pointing_away_predicts_nothing(self) -> None:
        readings = _rising(per_hour=-2.0, start_value=80.0)

        assert (
            crossing(
                readings,
                threshold=85.0,
                comparison="above",
                now=readings[-1][0],
                horizon=HORIZON,
                min_samples=10,
            )
            is None
        )

    def test_a_flat_line_predicts_nothing(self) -> None:
        readings = _rising(per_hour=0.0, start_value=80.0)

        assert (
            crossing(
                readings,
                threshold=85.0,
                comparison="above",
                now=readings[-1][0],
                horizon=HORIZON,
                min_samples=10,
            )
            is None
        )

    def test_too_few_samples_predicts_nothing(self) -> None:
        readings = _rising(per_hour=2.0, start_value=80.0, count=4)

        assert (
            crossing(
                readings,
                threshold=85.0,
                comparison="above",
                now=readings[-1][0],
                horizon=HORIZON,
                min_samples=10,
            )
            is None
        )

    def test_a_crossing_beyond_the_horizon_is_not_reported(self) -> None:
        """Accuracy falls with distance (ADR-020), and a forecast the report has
        to qualify into meaninglessness is not worth issuing."""
        readings = _rising(per_hour=0.05, start_value=80.0)

        assert (
            crossing(
                readings,
                threshold=85.0,
                comparison="above",
                now=readings[-1][0],
                horizon=timedelta(hours=24),
                min_samples=10,
            )
            is None
        )

    def test_noise_wide_enough_to_reach_past_the_horizon_is_refused(self) -> None:
        """The gate ADR-043 chose instead of a significance multiplier.

        These readings rise on average, and scatter so widely that the slope's
        own standard error puts the late end of the crossing outside the horizon.
        No constant was invented to reject it: the horizon is the one from
        policy.yaml, and it is doing both jobs.
        """
        readings = _readings([80.0, 84.0, 80.5, 85.0, 80.2, 86.0, 80.4, 86.5, 81.0, 87.0])

        found = crossing(
            readings,
            threshold=140.0,
            comparison="above",
            now=readings[-1][0],
            horizon=timedelta(hours=6),
            min_samples=10,
        )

        assert found is None


class TestAgainstTheGroundTruthOfTheSyntheticSource:
    """ADR-020's whole argument: the generator knows the answer (ADR-032)."""

    def test_the_linear_motor_is_predicted_close_to_its_true_crossing(self) -> None:
        """The profile ADR-002 named, and the one the mechanism has to get right
        before any harder shape is worth discussing."""
        source = SyntheticSource(LINE_A_TWELVE_HOURS, seed=20260813)
        truth = source.ground_truth(MOTOR, "motor_temp_c", threshold=85.0, comparison="above")
        assert truth.crosses_at is not None

        window = Window(timedelta(hours=2))
        readings: list[tuple[datetime, float]] = []
        at: datetime | None = None
        for signal in source.stream():
            if signal.machine_id != MOTOR or signal.metric_name != "motor_temp_c":
                continue
            if signal.timestamp >= truth.crosses_at - timedelta(hours=4):
                break
            readings = window.add(signal)
            at = signal.timestamp

        assert at is not None
        found = crossing(
            readings,
            threshold=85.0,
            comparison="above",
            now=at,
            horizon=timedelta(hours=24),
            min_samples=10,
        )

        assert found is not None
        error = abs(found.at - truth.crosses_at)
        # Four hours ahead of the event, on a linear curve with noise. The
        # measured figure is in docs/prediction-baseline.md; this only asserts
        # the mechanism is in the right hour, which is what would break loudly if
        # the fit or the window were wrong.
        assert error < timedelta(hours=1)

    def test_the_interlock_that_jumps_is_never_predicted(self) -> None:
        """ADR-032 built one profile to be unpredictable on purpose.

        A mechanism that produced a forecast here would be fabricating one, and
        ADR-020's last consequence - that the report must say trend
        extrapolation cannot catch a sudden failure - would be false.
        """
        source = SyntheticSource(LINE_A_TWELVE_HOURS, seed=20260813)
        interlock = MachineId("MC-012")
        window = Window(timedelta(hours=2))

        predictions = []
        for signal in source.stream():
            if signal.machine_id != interlock or signal.metric_name != "interlock_closed":
                continue
            readings = window.add(signal)
            found = crossing(
                readings,
                threshold=1.0,
                comparison="below",
                now=signal.timestamp,
                horizon=timedelta(hours=24),
                min_samples=10,
            )
            if found is not None:
                predictions.append(found)

        assert predictions == []


class TestTheSentenceAPersonReads:
    def test_the_interval_is_in_it(self) -> None:
        readings = _readings([80.0, 80.9, 81.4, 82.6, 83.0, 84.2, 84.6, 85.9, 86.2, 87.4, 88.1])
        found = crossing(
            readings,
            threshold=92.0,
            comparison="above",
            now=readings[-1][0],
            horizon=HORIZON,
            min_samples=10,
        )
        assert found is not None

        sentence = describe(found, metric_name="motor_temp_c", threshold=92.0)

        assert "give or take" in sentence
        assert "expected to reach 92.0" in sentence
        assert "readings" in sentence

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
from pdm.triggers.trend import Window, crossing, describe, fit, without_spikes

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


class TestWhatTheCodeReviewFound:
    """Four in the fit. Two of them only appear on data that looks boring."""

    def test_a_channel_drifting_by_a_billionth_does_not_crash_the_batch(self) -> None:
        """A crossing a hundred thousand years out is `timedelta` overflow, and
        an uncaught OverflowError here aborts every other signal in the batch -
        on the most boring possible input."""
        readings = _readings([80.0 + 1e-9 * index for index in range(20)])

        found = crossing(
            readings,
            threshold=85.0,
            comparison="above",
            now=readings[-1][0],
            horizon=timedelta(hours=24),
            min_samples=10,
        )

        assert found is None

    def test_the_eta_comes_from_the_fitted_line_not_the_last_reading(self) -> None:
        """ADR-043 section 3 says `(threshold - intercept)/slope`, and the
        intercept was being computed and ignored.

        One noisy final sample moved the ETA by half an hour while the interval -
        computed from the slope - stayed a few minutes wide. A number that
        precise and that unstable is worse than a wider one.
        """
        clean = _rising(per_hour=2.0, start_value=80.0, count=13)
        jumpy = [*clean[:-1], (clean[-1][0], clean[-1][1] + 2.0)]

        steady = crossing(
            clean,
            threshold=90.0,
            comparison="above",
            now=clean[-1][0],
            horizon=timedelta(hours=24),
            min_samples=10,
        )
        wobbled = crossing(
            jumpy,
            threshold=90.0,
            comparison="above",
            now=jumpy[-1][0],
            horizon=timedelta(hours=24),
            min_samples=10,
        )

        assert steady is not None and wobbled is not None

        # The last sample still rotates the fit, which is correct - it is data.
        # What it must not do is move the answer by its whole size, which is what
        # extrapolating from the raw reading did. Compared here against exactly
        # that calculation rather than against a number chosen to pass.
        from_raw_sample = jumpy[-1][0] + timedelta(
            hours=(90.0 - jumpy[-1][1]) / wobbled.fit.slope_per_hour
        )
        assert abs(wobbled.at - steady.at) < abs(from_raw_sample - steady.at)

    def test_a_perfectly_clean_line_still_reports_an_interval(self) -> None:
        """ "Give or take 0 minutes" is a claim to know the future to the second
        from data sampled every ten minutes. The floor is the sampling
        resolution, derived from the readings rather than configured."""
        readings = _rising(per_hour=2.0, start_value=80.0, count=13)

        found = crossing(
            readings,
            threshold=90.0,
            comparison="above",
            now=readings[-1][0],
            horizon=timedelta(hours=24),
            min_samples=10,
        )

        assert found is not None
        assert found.fit.slope_error == pytest.approx(0.0, abs=1e-9)
        assert found.interval >= timedelta(minutes=10)

    def test_a_stream_that_stopped_and_restarted_does_not_widen_every_interval(self) -> None:
        """The resolution is the median gap, not the mean: one hole in the
        stream would otherwise make every later forecast look vaguer than the
        data supports."""
        readings = [
            *_rising(per_hour=2.0, start_value=80.0, count=6),
            (NOW + timedelta(hours=6), 81.0),
            *[
                (NOW + timedelta(hours=6, minutes=10 * index), 81.0 + 0.33 * index)
                for index in range(1, 8)
            ],
        ]

        found = crossing(
            readings,
            threshold=90.0,
            comparison="above",
            now=readings[-1][0],
            horizon=timedelta(hours=48),
            min_samples=10,
        )

        if found is not None:
            assert found.resolution == timedelta(minutes=10)


class TestAReadingThatIsNotANumber:
    """A sensor sending `nan` or a value large enough to overflow a square is
    ordinary, and it used to take the whole trigger batch with it.

    `fit` raised out of `Fit`'s own validation - `slope_error` came back as
    `nan` and the model refuses a negative-or-nan standard error - so one bad
    reading on one channel aborted the tick that was processing every channel.
    The failure mode `crossing`'s own comment worries about, arriving through
    the door beside the one that was locked.

    None is the honest answer and the one the signature already carried: `fit`
    returns None for "no line can be fitted through this", and a line whose
    slope is not a number is exactly that.
    """

    def test_a_nan_reading_yields_no_line(self) -> None:
        readings = [
            (NOW, 1.0),
            (NOW + timedelta(minutes=1), float("nan")),
            (NOW + timedelta(minutes=2), 3.0),
        ]
        assert fit(readings) is None

    def test_an_infinite_reading_yields_no_line(self) -> None:
        readings = [
            (NOW, 1.0),
            (NOW + timedelta(minutes=1), float("inf")),
            (NOW + timedelta(minutes=2), 3.0),
        ]
        assert fit(readings) is None

    def test_a_value_whose_square_overflows_yields_no_line(self) -> None:
        """1e308 is finite and its square is not. The sums inside the fit are
        where that stops being an arithmetic curiosity."""
        readings = [
            (NOW, 1.0),
            (NOW + timedelta(minutes=1), 2.0),
            (NOW + timedelta(minutes=2), -1e308),
        ]
        assert fit(readings) is None

    def test_crossing_returns_none_rather_than_raising(self) -> None:
        """The property that matters to the batch: whatever arrives, the caller
        gets an answer rather than an exception."""
        readings = [(NOW + timedelta(minutes=i), float("nan")) for i in range(20)]
        assert (
            crossing(
                readings,
                threshold=80.0,
                comparison="above",
                now=NOW,
                horizon=timedelta(hours=24),
                min_samples=10,
            )
            is None
        )

    def test_one_bad_reading_does_not_hide_a_good_channel(self) -> None:
        """The cost of the fix, stated: a window containing one `nan` yields no
        forecast at all rather than a forecast from the rest. That is the
        conservative direction - a missing prediction is a prediction nobody
        acts on - but it is a choice and not a free one."""
        clean = [(NOW + timedelta(minutes=i), 50.0 + i) for i in range(20)]
        assert fit(clean) is not None

        spoiled = list(clean)
        spoiled[7] = (spoiled[7][0], float("nan"))
        assert fit(spoiled) is None


class TestThePrintedInterval:
    """ADR-106: what a ticket prints is the wider of the slope's interval and the
    error forecasts this far ahead have actually had."""

    BANDS = ((1.0, 0.4), (3.0, 0.3), (8760.0, 0.6))

    def test_no_bands_prints_the_fitted_interval(self) -> None:
        from pdm.triggers.domain import printed_interval

        fitted = timedelta(minutes=6)
        assert printed_interval(fitted, timedelta(hours=2), ()) == fitted

    def test_the_band_for_the_lead_time_widens_it(self) -> None:
        from pdm.triggers.domain import printed_interval

        assert printed_interval(timedelta(minutes=6), timedelta(hours=2), self.BANDS) == timedelta(
            minutes=36
        )
        assert printed_interval(
            timedelta(minutes=6), timedelta(minutes=30), self.BANDS
        ) == timedelta(minutes=12)

    def test_it_never_narrows_the_fitted_interval(self) -> None:
        from pdm.triggers.domain import printed_interval

        wide = timedelta(hours=3)
        assert printed_interval(wide, timedelta(hours=2), self.BANDS) == wide

    def test_the_last_band_holds_beyond_its_bound(self) -> None:
        from pdm.triggers.domain import printed_interval

        assert printed_interval(timedelta(0), timedelta(hours=10000), self.BANDS) == timedelta(
            hours=6000
        )


class TestASpikeDoesNotSteerTheForecast:
    """ADR-125. The examiner found the report's worked example forecasting
    4.5 hours early: three +25 degree glitches pulled a 3.0 degree-per-hour
    drift to 7.35. Detection already ignored spikes; the fit did not."""

    def _with_glitches(self) -> list[tuple[datetime, float]]:
        clean = _rising(per_hour=3.0, start_value=64.0, count=49, every=timedelta(minutes=1))
        glitched = list(clean)
        for index in (40, 44, 47):
            moment, value = glitched[index]
            glitched[index] = (moment, value + 25.0)
        return glitched

    def test_isolated_spikes_are_removed_and_the_drift_is_kept(self) -> None:
        readings = self._with_glitches()

        kept = without_spikes(readings)

        assert len(kept) == len(readings) - 3
        line = fit(kept)
        assert line is not None
        assert line.slope_per_hour == pytest.approx(3.0, abs=0.01)

    def test_a_clean_drift_loses_nothing(self) -> None:
        readings = _rising(per_hour=3.0, start_value=64.0, count=49, every=timedelta(minutes=1))

        assert without_spikes(readings) == readings

    def test_the_forecast_is_the_drifts_not_the_glitches(self) -> None:
        readings = self._with_glitches()
        last = readings[-1][0]

        forecast = crossing(
            readings,
            threshold=85.0,
            comparison="above",
            now=last,
            horizon=HORIZON,
            min_samples=10,
        )

        assert forecast is not None
        # 64 + 3 * (48/60) = 66.4 now; 85 is (85 - 66.4) / 3 = 6.2 hours away.
        assert (forecast.at - last) == pytest.approx(timedelta(hours=6.2), abs=timedelta(minutes=5))


class TestAForecastCarriesItsReading:
    def test_the_finding_keeps_the_reading_the_fit_ends_on(self) -> None:
        """ADR-134: the ticket says "78 now, 85 is the line, rising 2 an hour".
        The slope alone cannot say where the machine is now, and nothing else
        keeps the reading once the window has moved on."""
        from pathlib import Path

        from pdm.contracts import MachineModel, Signal
        from pdm.platform.config import load_config
        from pdm.triggers.domain import forecast
        from pdm.triggers.trend import Window

        rules = load_config(Path("config")).rules.rules
        windows = Window(timedelta(hours=3))
        decisions = []
        for at, value in _rising(per_hour=2.0, start_value=76.0):
            signal = Signal(
                timestamp=at,
                machine_id=MachineId("MC-012"),
                metric_name="motor_temp_c",
                value=value,
                unit="degC",
            )
            decisions = forecast(
                signal,
                rules,
                machine_model=MachineModel("R-2000iC"),
                now=at,
                windows=windows,
                horizon=HORIZON,
                min_samples=10,
            )

        finding = next(one.finding for one in decisions if one.finding is not None)
        assert finding.evidence["value"] == 80.0
        assert finding.evidence["unit"] == "degC"
        assert finding.evidence["metric_name"] == "motor_temp_c"
        assert finding.evidence["threshold"] == 85.0
        assert finding.evidence["slope_per_hour"] == pytest.approx(2.0)

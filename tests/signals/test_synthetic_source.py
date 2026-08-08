"""The generator every prediction figure in the report will be produced by.

These tests are not about a data source behaving reasonably. ADR-020 measures
ETA error against this module's ground truth, so a fault here does not produce a
failure - it produces a number, which is worse. The cases that matter most are
therefore the ones checking that the answer is independent of the noise, that
the same seed gives the same data forever, and that the profile ADR-020 says
cannot be predicted genuinely cannot be.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from pdm.contracts import MachineId, Signal
from pdm.platform.config import load_config
from pdm.signals import (
    LINE_A_TWELVE_HOURS,
    Channel,
    Exponential,
    LinearDrift,
    Scenario,
    SignalSource,
    Spike,
    Steady,
    Step,
    SyntheticSource,
)

REPO_CONFIG = Path("config")

START = datetime(2026, 3, 3, 6, 0, tzinfo=UTC)

MOTOR = MachineId("MC-001")
SERVO = MachineId("MC-004")
INTERLOCK = MachineId("MC-012")
FAN = MachineId("MC-018")

# The thresholds the demo scenario is aimed at, copied from config/rules.yaml.
# A test below proves they still agree with the file.
MOTOR_TEMP_LIMIT = 85.0
SERVO_CURRENT_LIMIT = 12.5
FAN_RPM_FLOOR = 1200.0
CYCLE_TIME_LIMIT = 62.0


def _scenario(*channels: Channel, duration: timedelta = timedelta(hours=2)) -> Scenario:
    return Scenario(
        name="test",
        starts_at=START,
        sample_interval=timedelta(minutes=1),
        duration=duration,
        channels=channels,
    )


def _channel(
    profile: Steady | LinearDrift | Exponential | Step,
    noise_sigma: float = 0.0,
    spike: Spike | None = None,
) -> Channel:
    return Channel(
        machine_id=MOTOR,
        metric_name="motor_temp_c",
        unit="degC",
        profile=profile,
        noise_sigma=noise_sigma,
        spike=spike,
    )


def _values(signals: list[Signal], machine_id: MachineId, metric_name: str) -> list[float]:
    return [
        signal.value
        for signal in signals
        if signal.machine_id == machine_id and signal.metric_name == metric_name
    ]


def _longest_run(values: list[float], predicate: Callable[[float], bool]) -> int:
    """Longest stretch of consecutive samples satisfying the predicate.

    This is what a rule's `for_seconds` debounce actually measures, expressed in
    samples.
    """
    longest = current = 0
    for value in values:
        current = current + 1 if predicate(value) else 0
        longest = max(longest, current)
    return longest


class TestThePort:
    def test_the_synthetic_source_satisfies_the_port(self) -> None:
        assert isinstance(SyntheticSource(LINE_A_TWELVE_HOURS), SignalSource)

    def test_source_time_never_goes_backwards(self) -> None:
        """The rule engine measures `for_seconds` by comparing timestamps and
        cannot do that on an unordered stream."""
        timestamps = [signal.timestamp for signal in SyntheticSource(LINE_A_TWELVE_HOURS).stream()]
        assert timestamps == sorted(timestamps)

    def test_every_timestamp_is_timezone_aware(self) -> None:
        assert all(
            signal.timestamp.tzinfo is not None
            for signal in SyntheticSource(LINE_A_TWELVE_HOURS).stream()
        )

    def test_the_scenario_window_is_covered_exactly(self) -> None:
        scenario = LINE_A_TWELVE_HOURS
        signals = list(SyntheticSource(scenario).stream())

        assert scenario.sample_count == 12 * 60 + 1
        assert len(signals) == scenario.sample_count * len(scenario.channels)
        assert signals[0].timestamp == scenario.starts_at
        assert signals[-1].timestamp == scenario.ends_at

    def test_the_unit_and_tag_of_every_channel_survive(self) -> None:
        by_tag = {
            (signal.machine_id, signal.metric_name): signal.unit
            for signal in SyntheticSource(LINE_A_TWELVE_HOURS).stream()
        }
        assert by_tag[(MOTOR, "motor_temp_c")] == "degC"
        assert by_tag[(INTERLOCK, "interlock_closed")] == "bool"
        assert len(by_tag) == len(LINE_A_TWELVE_HOURS.channels)


class TestDeterminism:
    """(scenario + seed) must fully determine the output (design.md 9)."""

    def test_the_same_seed_gives_the_same_stream_every_time(self) -> None:
        source = SyntheticSource(LINE_A_TWELVE_HOURS, seed=7)
        assert list(source.stream()) == list(source.stream())

    def test_two_sources_with_the_same_seed_agree(self) -> None:
        first = list(SyntheticSource(LINE_A_TWELVE_HOURS, seed=7).stream())
        second = list(SyntheticSource(LINE_A_TWELVE_HOURS, seed=7).stream())
        assert first == second

    def test_a_different_seed_moves_the_samples(self) -> None:
        first = list(SyntheticSource(LINE_A_TWELVE_HOURS, seed=0).stream())
        second = list(SyntheticSource(LINE_A_TWELVE_HOURS, seed=1).stream())
        assert first != second

    def test_adding_a_machine_leaves_the_others_untouched(self) -> None:
        """ADR-032: noise is seeded per channel so that a measurement taken last
        week stays comparable to one taken today. With a single stream of
        randomness for the whole scenario, adding one machine would silently
        change every other machine's data and every number derived from it."""
        motor = _channel(LinearDrift(baseline=62.0, per_hour=3.0), noise_sigma=0.4)
        fan = Channel(
            machine_id=FAN,
            metric_name="fan_rpm",
            unit="rpm",
            profile=LinearDrift(baseline=1500.0, per_hour=-40.0),
            noise_sigma=12.0,
        )

        alone = list(SyntheticSource(_scenario(motor)).stream())
        together = list(SyntheticSource(_scenario(motor, fan)).stream())

        assert _values(alone, MOTOR, "motor_temp_c") == _values(together, MOTOR, "motor_temp_c")


class TestGroundTruthIsTakenFromTheCurve:
    def test_noise_does_not_move_the_answer(self) -> None:
        """The point of ADR-032. Read off the samples instead, and the target
        would be a draw from the noise distribution, so ETA error would partly
        measure the random number stream rather than the predictor."""
        quiet = SyntheticSource(LINE_A_TWELVE_HOURS, seed=0).ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        noisy = SyntheticSource(LINE_A_TWELVE_HOURS, seed=99).ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        assert quiet == noisy

    def test_the_motor_crosses_and_then_fails(self) -> None:
        truth = SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        start = LINE_A_TWELVE_HOURS.starts_at

        # 62 °C rising at 3 °C/h reaches 85 °C after 7h40m and 95 °C at hour 11.
        assert truth.crosses_at == start + timedelta(hours=7, minutes=40)
        assert truth.fails_at == start + timedelta(hours=11)

    def test_the_curve_really_is_at_the_threshold_when_it_crosses(self) -> None:
        channel = LINE_A_TWELVE_HOURS.channel(MOTOR, "motor_temp_c")
        truth = SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        assert truth.crosses_at is not None

        elapsed = truth.crosses_at - LINE_A_TWELVE_HOURS.starts_at
        assert channel.profile.value_at(elapsed) == pytest.approx(MOTOR_TEMP_LIMIT)

    def test_a_falling_signal_crosses_downwards(self) -> None:
        truth = SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
            FAN, "fan_rpm", threshold=FAN_RPM_FLOOR, comparison="below"
        )
        start = LINE_A_TWELVE_HOURS.starts_at
        assert truth.crosses_at == start + timedelta(hours=7, minutes=30)
        assert truth.fails_at == start + timedelta(hours=10)

    def test_a_healthy_machine_never_crosses(self) -> None:
        """None must be distinguishable from "crosses at hour zero", or a
        healthy machine and an already-broken one look the same."""
        truth = SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
            FAN, "cycle_time_s", threshold=CYCLE_TIME_LIMIT, comparison="above"
        )
        assert truth.crosses_at is None
        assert truth.fails_at is None

    def test_the_step_failure_has_a_crossing_but_no_failure_value(self) -> None:
        truth = SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
            INTERLOCK, "interlock_closed", threshold=1.0, comparison="below"
        )
        assert truth.crosses_at == LINE_A_TWELVE_HOURS.starts_at + timedelta(hours=9)
        # The jump is the failure; there is nothing beyond it to reach.
        assert truth.fails_at is None

    def test_an_unknown_tag_is_an_error_rather_than_an_empty_answer(self) -> None:
        with pytest.raises(KeyError, match="no channel"):
            SyntheticSource(LINE_A_TWELVE_HOURS).ground_truth(
                MOTOR, "vibration_mm_s", threshold=1.0, comparison="above"
            )


class TestWhatEachProfileIsFor:
    """Each curve exists to support or to bound one claim (ADR-032)."""

    def test_steady_is_the_machine_that_raises_nothing(self) -> None:
        profile = Steady(baseline=58.0)
        assert profile.value_at(timedelta(hours=100)) == 58.0
        assert profile.time_until(62.0, "above") is None
        assert profile.time_until(50.0, "below") is None

    def test_a_condition_already_true_at_the_start_crosses_at_zero(self) -> None:
        """A machine that is already over the line has not "never crossed"."""
        profile = LinearDrift(baseline=90.0, per_hour=3.0)
        assert profile.time_until(85.0, "above") == timedelta(0)

    def test_a_curve_moving_the_wrong_way_never_arrives(self) -> None:
        profile = LinearDrift(baseline=62.0, per_hour=-3.0)
        assert profile.time_until(85.0, "above") is None

    def test_a_straight_line_fit_predicts_the_accelerating_curve_late(self) -> None:
        """The reason ADR-020 requires error reported per forecast horizon.

        Fitting the first two hours of an exponential and extrapolating gives a
        crossing hours later than the true one. Reported as a single figure that
        error would be averaged away with the easy cases, and the report would
        overstate what the method can do.
        """
        profile = Exponential(baseline=8.0, amplitude=0.5, tau_hours=2.0)
        true_crossing = profile.time_until(SERVO_CURRENT_LIMIT, "above")
        assert true_crossing is not None

        window = timedelta(hours=2)
        slope_per_hour = (profile.value_at(window) - profile.value_at(timedelta(0))) / 2
        predicted_hours = (SERVO_CURRENT_LIMIT - profile.baseline) / slope_per_hour

        assert timedelta(hours=predicted_hours) > true_crossing
        assert true_crossing == timedelta(hours=2 * math.log(10.0))

    def test_the_step_offers_no_trend_to_extrapolate(self) -> None:
        """ADR-020's stated limitation, as a test rather than a paragraph."""
        profile = Step(baseline=1.0, delta=-1.0, after=timedelta(hours=9))
        before = [profile.value_at(timedelta(hours=hour)) for hour in range(9)]

        assert before == [1.0] * 9  # no slope exists anywhere before the failure
        assert profile.time_until(1.0, "below") == timedelta(hours=9)

    def test_a_threshold_inside_the_jump_is_never_attained(self) -> None:
        """A step from 1500 to 1000 passes 1200 without ever being 1200, but the
        rule still fires; a step that stops short does not."""
        crosses = Step(baseline=1500.0, delta=-500.0, after=timedelta(hours=3))
        stops_short = Step(baseline=1500.0, delta=-100.0, after=timedelta(hours=3))

        assert crosses.time_until(1200.0, "below") == timedelta(hours=3)
        assert stops_short.time_until(1200.0, "below") is None

    def test_a_threshold_is_strict_in_both_directions(self) -> None:
        """An interlock resting at exactly 1.0 is closed, not open. Read as
        `<=`, the safety rule would fire continuously on a healthy machine."""
        interlock = Step(baseline=1.0, delta=-1.0, after=timedelta(hours=9))
        assert interlock.value_at(timedelta(hours=8)) == 1.0
        assert interlock.time_until(1.0, "below") == timedelta(hours=9)


class TestSpikes:
    def test_a_spike_moves_one_sample_and_leaves_the_curve_alone(self) -> None:
        channel = _channel(Steady(baseline=58.0), spike=Spike(probability=0.5, magnitude=6.0))
        values = _values(list(SyntheticSource(_scenario(channel)).stream()), MOTOR, "motor_temp_c")

        deviations = {round(value - 58.0, 9) for value in values}
        assert deviations <= {0.0, 6.0}
        assert 6.0 in deviations  # the mechanism fires at all

    def test_the_healthy_machine_never_holds_a_rule_open(self) -> None:
        """R-cycle-time-drift needs 600 seconds above 62s, which at one sample a
        minute is ten in a row. Spikes must not add up to that, or the demo
        raises a work order against a machine that is fine.

        Checked across every seed rather than the shipped one: independent
        draws mean the debounce shortens the odds of a false alarm rather than
        removing them, and a claim about the demo dataset alone would say
        nothing about that. Ten in a row at p=0.02 is beyond reach; two in a row
        is not, which is why the 120-second debounce on the motor rule cannot
        make the same promise.
        """
        for seed in range(20):
            values = _values(
                list(SyntheticSource(LINE_A_TWELVE_HOURS, seed=seed).stream()),
                FAN,
                "cycle_time_s",
            )
            assert sum(value > CYCLE_TIME_LIMIT for value in values) > 0  # spikes do happen
            assert _longest_run(values, lambda value: value > CYCLE_TIME_LIMIT) < 10

    def test_the_motor_glitches_over_the_threshold_long_before_it_is_hot(self) -> None:
        """What the debounce is up against, stated as what it is.

        Single readings sit over 85 °C hours before the motor is anywhere near
        it. A two-sample debounce discards almost all of them - but adjacent
        glitches are independent draws, so "never two in a row" is not a
        property this generator has and must not be asserted as one. The
        surviving pairs are a false alarm rate to be measured in slice 5, not a
        thing to be tested away here.
        """
        source = SyntheticSource(LINE_A_TWELVE_HOURS)
        truth = source.ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        assert truth.crosses_at is not None

        # Stop an hour short of the crossing: within that hour the curve itself
        # is within 3 °C of the threshold, so a reading over the line is the
        # machine genuinely getting hot rather than a glitch.
        early_samples = int(
            (truth.crosses_at - timedelta(hours=1) - LINE_A_TWELVE_HOURS.starts_at)
            / LINE_A_TWELVE_HOURS.sample_interval
        )
        early = _values(list(source.stream()), MOTOR, "motor_temp_c")[:early_samples]

        assert max(early) > MOTOR_TEMP_LIMIT  # glitches reach over the line
        assert all(value < MOTOR_TEMP_LIMIT for value in early[-5:])  # the curve does not


class TestScenariosRefuseToBeQuietlyWrong:
    def test_a_naive_start_time_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            Scenario(
                name="test",
                starts_at=datetime(2026, 3, 3, 6, 0),
                sample_interval=timedelta(minutes=1),
                duration=timedelta(hours=1),
                channels=(_channel(Steady(baseline=58.0)),),
            )

    def test_two_curves_on_one_sensor_tag_are_rejected(self) -> None:
        with pytest.raises(ValidationError, match="two channels"):
            _scenario(_channel(Steady(baseline=58.0)), _channel(Steady(baseline=61.0)))

    def test_a_scenario_needs_at_least_one_channel(self) -> None:
        with pytest.raises(ValidationError):
            _scenario()

    def test_a_window_that_does_not_divide_into_samples_is_rejected(self) -> None:
        """A crossing timed to land in the unsampled tail would be a failure the
        ground truth insists on and the data never shows."""
        with pytest.raises(ValidationError, match="whole number"):
            _scenario(_channel(Steady(baseline=58.0)), duration=timedelta(seconds=90))

    def test_a_failure_value_the_curve_never_reaches_is_rejected(self) -> None:
        """A jump that stops short of the failure value. The drifting curves
        cannot fail this way - they are unbounded, so they arrive eventually."""
        with pytest.raises(ValidationError, match="never reaches its failure_value"):
            Step(baseline=1500.0, delta=-100.0, after=timedelta(hours=1), failure_value=1000.0)

    def test_a_scenario_cannot_begin_with_the_machine_already_failed(self) -> None:
        """Ground truth would be hour zero, and every prediction would be
        measured against a failure that had already happened."""
        with pytest.raises(ValidationError, match="already failed"):
            LinearDrift(baseline=62.0, per_hour=3.0, failure_value=50.0)

    def test_a_machine_that_never_degrades_cannot_declare_a_failure(self) -> None:
        with pytest.raises(ValidationError, match="never reaches its failure_value"):
            Steady(baseline=58.0, failure_value=95.0)

    def test_a_curve_that_does_not_move_must_say_so(self) -> None:
        """Two ways of writing the same thing would mean two paths through every
        piece of code that special-cases a flat signal."""
        with pytest.raises(ValidationError, match="Steady"):
            LinearDrift(baseline=62.0, per_hour=0.0)
        with pytest.raises(ValidationError, match="Steady"):
            Exponential(baseline=8.0, amplitude=0.0, tau_hours=2.0)
        with pytest.raises(ValidationError, match="Steady"):
            Step(baseline=1.0, delta=0.0, after=timedelta(hours=1))

    def test_a_flat_curve_with_a_failure_value_says_the_same_thing(self) -> None:
        """The shape guard has to run before the inherited failure check, which
        divides by the rate of change. Declared as a model validator it would
        run second, and a zero rate would raise ZeroDivisionError from inside
        pydantic instead of saying which field is wrong."""
        with pytest.raises(ValidationError, match="Steady"):
            LinearDrift(baseline=62.0, per_hour=0.0, failure_value=30.0)
        with pytest.raises(ValidationError, match="Steady"):
            Exponential(baseline=8.0, amplitude=0.0, tau_hours=2.0, failure_value=30.0)

    def test_a_curve_that_overflows_its_window_is_rejected_at_construction(self) -> None:
        """A profile validates by inverting its formula, which stays finite
        where running it forward does not. Without this the run raises
        OverflowError partway through a stream that has already been half
        consumed."""
        with pytest.raises(ValidationError, match="infinity"):
            _scenario(
                _channel(Exponential(baseline=8.0, amplitude=0.5, tau_hours=0.001)),
                duration=timedelta(hours=2),
            )

    def test_a_spike_must_move_the_reading(self) -> None:
        with pytest.raises(ValidationError, match="not a spike"):
            Spike(probability=0.5, magnitude=0.0)


class TestTheDemoScenarioMatchesTheRealPlant:
    """A channel no rule reads generates data that looks fine and fires nothing.

    This is the failure that would waste a week: the generator works, the rule
    engine works, and the two are pointed at different sensor tags.
    """

    def test_every_channel_is_a_real_machine_watched_by_a_real_rule(self) -> None:
        config = load_config(REPO_CONFIG)

        for channel in LINE_A_TWELVE_HOURS.channels:
            model = config.model_of(channel.machine_id)
            watching = [
                rule
                for rule in config.rules.rules
                if rule.machine_model == model and rule.metric_name == channel.metric_name
            ]
            assert watching, (
                f"{channel.machine_id} {channel.metric_name} is generated but no rule "
                f"for {model} reads it"
            )

    def test_the_thresholds_in_this_file_still_match_the_rules(self) -> None:
        """These tests assert exact crossing times against thresholds copied out
        of config. If the file moves and the copies do not, the assertions keep
        passing against a threshold nothing uses.

        Keyed by machine and metric rather than metric alone: two models may
        watch the same metric at different limits, and a dict keyed on the
        metric would quietly keep whichever rule was read last - defeating the
        drift this test exists to catch.
        """
        config = load_config(REPO_CONFIG)
        thresholds = {
            (rule.machine_model, rule.metric_name): rule.threshold for rule in config.rules.rules
        }

        expected = {
            (MOTOR, "motor_temp_c"): MOTOR_TEMP_LIMIT,
            (SERVO, "servo_current_a"): SERVO_CURRENT_LIMIT,
            (FAN, "fan_rpm"): FAN_RPM_FLOOR,
            (FAN, "cycle_time_s"): CYCLE_TIME_LIMIT,
        }
        for (machine_id, metric_name), limit in expected.items():
            assert thresholds[(config.model_of(machine_id), metric_name)] == limit

    def test_the_scenario_covers_a_predictable_and_an_unpredictable_failure(self) -> None:
        """The argument that layer 1 can be delivered without the plant needs
        both halves: something the method gets right, and something it cannot
        get at all (ADR-020)."""
        source = SyntheticSource(LINE_A_TWELVE_HOURS)
        predictable = source.ground_truth(
            MOTOR, "motor_temp_c", threshold=MOTOR_TEMP_LIMIT, comparison="above"
        )
        accelerating = source.ground_truth(
            SERVO, "servo_current_a", threshold=SERVO_CURRENT_LIMIT, comparison="above"
        )
        sudden = source.ground_truth(
            INTERLOCK, "interlock_closed", threshold=1.0, comparison="below"
        )

        for truth in (predictable, accelerating, sudden):
            assert truth.crosses_at is not None
            assert truth.crosses_at < LINE_A_TWELVE_HOURS.ends_at

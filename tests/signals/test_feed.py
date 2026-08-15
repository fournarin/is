"""Pacing: the same signals, handed over when their moment arrives (ADR-044 §4).

The property this file exists for is the one in the second test class: a feed
changes *when* a signal is handed over and never what it says. A feed that
restamped signals as "now" would look correct in every other test here and would
quietly break the link between a prediction and the curve it is scored against
(ADR-032), which is what every ETA figure in the report rests on.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from pdm.contracts import MachineId, Signal
from pdm.signals import LINE_A_TWELVE_HOURS, Feed, SyntheticSource

# Deliberately five months apart. The scenario's timeline is somebody else's and
# the process reading it has its own; a feed that only ever worked when the two
# happened to coincide would pass a test written with one datetime.
SOURCE_START = datetime(2026, 3, 3, 6, 0, tzinfo=UTC)
DECISION_START = datetime(2026, 8, 15, 9, 0, tzinfo=UTC)

MOTOR = MachineId("MC-001")


class Recorded:
    """A source of exactly these signals, in this order."""

    def __init__(self, signals: list[Signal]) -> None:
        self._signals = tuple(signals)

    def stream(self) -> Iterator[Signal]:
        return iter(self._signals)


def _samples(count: int, *, every: timedelta = timedelta(minutes=1)) -> list[Signal]:
    return [
        Signal(
            timestamp=SOURCE_START + every * index,
            machine_id=MOTOR,
            metric_name="motor_temp_c",
            value=60.0 + index,
            unit="degC",
        )
        for index in range(count)
    ]


def _feed(count: int, *, speed: float = 1.0, every: timedelta = timedelta(minutes=1)) -> Feed:
    return Feed(
        Recorded(_samples(count, every=every)),
        decision_origin=DECISION_START,
        speed=speed,
    )


class TestWhatIsDue:
    def test_the_first_sample_is_due_at_the_origin(self) -> None:
        """The source's first timestamp *is* the origin of its timeline, so the
        sample that defines it is due immediately rather than one interval in."""
        feed = _feed(5)

        assert [signal.value for signal in feed.due(DECISION_START)] == [60.0]

    def test_nothing_is_handed_over_twice(self) -> None:
        feed = _feed(5)
        feed.due(DECISION_START)

        assert feed.due(DECISION_START) == []

    def test_a_clock_that_has_not_moved_yields_nothing(self) -> None:
        """No guard is written for this and none is needed: everything up to the
        previous horizon has already been handed over."""
        feed = _feed(5)
        feed.due(DECISION_START + timedelta(minutes=3))

        assert feed.due(DECISION_START + timedelta(minutes=1)) == []

    def test_speed_maps_a_second_of_decision_time_onto_a_minute_of_source_time(self) -> None:
        feed = _feed(120, speed=60.0)

        first = feed.due(DECISION_START)
        after_ten_seconds = feed.due(DECISION_START + timedelta(seconds=10))

        assert len(first) == 1
        assert len(after_ten_seconds) == 10

    def test_at_plant_speed_a_minute_buys_a_sample(self) -> None:
        feed = _feed(10, speed=1.0)
        feed.due(DECISION_START)

        assert len(feed.due(DECISION_START + timedelta(minutes=1))) == 1

    def test_a_stall_hands_over_the_whole_backlog_rather_than_part_of_it(self) -> None:
        """A capped batch would be a stream with a silent hole in it, and the cap
        would be a constant with no source (ADR-044 §4)."""
        feed = _feed(500)

        assert len(feed.due(DECISION_START + timedelta(days=1))) == 500


class TestSourceTimeSurvives:
    def test_a_signal_keeps_the_timestamp_it_was_made_with(self) -> None:
        """The whole point of the module. `Signal.timestamp` is what the debounce
        measures duration with and what ground truth is anchored to; restamping
        it as "now" would produce a run whose ETA error could not be compared
        with any figure in docs/prediction-baseline.md (ADR-032)."""
        feed = _feed(3, speed=3600.0)

        handed_over = feed.due(DECISION_START + timedelta(minutes=1))

        assert [signal.timestamp for signal in handed_over] == [
            SOURCE_START,
            SOURCE_START + timedelta(minutes=1),
            SOURCE_START + timedelta(minutes=2),
        ]

    def test_order_is_the_stream_order(self) -> None:
        feed = _feed(50, speed=3600.0)

        handed_over = feed.due(DECISION_START + timedelta(hours=1))

        assert handed_over == sorted(handed_over, key=lambda signal: signal.timestamp)


class TestTheEnd:
    def test_an_exhausted_feed_says_so_and_stays_quiet(self) -> None:
        """Nothing restarts a scenario. Replaying a run that already happened
        would re-raise findings for failures the same data already showed."""
        feed = _feed(3)
        feed.due(DECISION_START + timedelta(hours=1))

        assert feed.exhausted
        assert feed.due(DECISION_START + timedelta(hours=2)) == []

    def test_a_feed_that_has_not_started_is_not_exhausted(self) -> None:
        feed = _feed(3)

        assert not feed.exhausted

    def test_an_empty_source_is_exhausted_the_first_time_it_is_asked(self) -> None:
        feed = Feed(Recorded([]), decision_origin=DECISION_START)

        assert feed.due(DECISION_START) == []
        assert feed.exhausted


class TestRefusals:
    def test_a_feed_needs_a_positive_speed(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            Feed(Recorded([]), decision_origin=DECISION_START, speed=0.0)

    def test_a_feed_needs_a_timezone_aware_origin(self) -> None:
        """ADR-028: the night shift crosses midnight, so a naive datetime is
        wrong for exactly one shift in three and right for the other two."""
        with pytest.raises(ValueError, match="ADR-028"):
            Feed(Recorded([]), decision_origin=datetime(2026, 8, 15, 9, 0))


class TestAgainstTheRealSource:
    def test_the_demo_scenario_arrives_whole_and_in_order(self) -> None:
        source = SyntheticSource(LINE_A_TWELVE_HOURS, seed=20260813)
        feed = Feed(source, decision_origin=DECISION_START, speed=3600.0)

        # Twelve hours of scenario at 3600x is twelve seconds of decision time.
        handed_over = feed.due(DECISION_START + timedelta(seconds=13))

        expected = LINE_A_TWELVE_HOURS.sample_count * len(LINE_A_TWELVE_HOURS.channels)
        assert len(handed_over) == expected
        assert feed.exhausted

    def test_nothing_is_generated_until_it_is_due(self) -> None:
        """A feed is a valve on a generator, not a buffer in front of one: twelve
        hours of five channels is 3605 signals and a tick wants the ten that have
        arrived."""
        source = SyntheticSource(LINE_A_TWELVE_HOURS, seed=20260813)
        feed = Feed(source, decision_origin=DECISION_START, speed=60.0)

        # One minute of decision time is one hour of scenario at 60x, and an
        # hour is sixty-one samples per channel counting the one at zero.
        first_hour = feed.due(DECISION_START + timedelta(minutes=1))

        assert len(first_hour) == 61 * len(LINE_A_TWELVE_HOURS.channels)
        assert not feed.exhausted

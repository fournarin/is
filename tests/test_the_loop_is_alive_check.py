"""The silence alarm must fire on the silence that already happened.

A check written after an incident is worth what it would have been worth during
it, so the first test is that exact gap: the last commit on 26 August 2026 at
11:10 and somebody noticing on 18 September at 08:50. Everything else here is
about the edges, because an alarm that cries wolf is turned off and an alarm
that stands down quietly is not an alarm.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.check_the_loop_is_alive import as_utc, judge, read_cadence

DURING_THE_TERM = (72, date(2026, 10, 22), "the report weeks")


class TestTheGapItWasWrittenFor:
    def test_the_twenty_three_days_would_have_been_caught(self) -> None:
        verdict = judge(
            last_commit=datetime(2026, 8, 26, 11, 10),
            now=datetime(2026, 9, 18, 8, 50),
            cadence=DURING_THE_TERM,
        )
        assert not verdict.ok

    def test_it_would_have_fired_on_the_fourth_day_rather_than_the_twenty_third(self) -> None:
        """The value of the alarm is entirely in how early it speaks. Noticing
        at the end of the gap is what already happened, by hand, on day 23.

        Day 4 rather than day 3: the window is 72 hours and 26 August 11:10 to
        29 August 11:10 is exactly 72, which is inside it. That hour is the
        whole difference between this test passing and the one above it, and
        writing the wrong day here is how a threshold gets quietly loosened."""
        verdict = judge(
            last_commit=datetime(2026, 8, 26, 11, 10),
            now=datetime(2026, 8, 30, 11, 10),
            cadence=DURING_THE_TERM,
        )
        assert not verdict.ok

    def test_the_message_names_the_routine_being_disabled_first(self) -> None:
        """Whoever reads this is reading it because something is wrong and does
        not yet know what. The order of the three questions is the finding from
        the incident: the routine was off, and that was the last thing checked."""
        verdict = judge(
            last_commit=datetime(2026, 8, 26, 11, 10),
            now=datetime(2026, 9, 18, 8, 50),
            cadence=DURING_THE_TERM,
        )
        checklist = verdict.message.split("in this order:", 1)[1]
        assert checklist.index("routine enabled") < checklist.index("spending limit")
        assert checklist.index("spending limit") < checklist.index("backlog empty")


class TestWhenItStaysQuiet:
    def test_a_working_day_of_silence_is_not_an_alarm(self) -> None:
        assert judge(
            last_commit=datetime(2026, 9, 17, 9, 0),
            now=datetime(2026, 9, 18, 9, 0),
            cadence=DURING_THE_TERM,
        ).ok

    def test_a_weekend_is_not_an_alarm(self) -> None:
        """Friday evening to Monday morning is 63 hours, and this is the case
        that decides whether anybody leaves the alarm switched on. It is why the
        window is 72 hours and not the 48 it was first written with: the first
        draft of this test was the thing that found that out."""
        assert judge(
            last_commit=datetime(2026, 9, 18, 18, 0),  # Friday evening
            now=datetime(2026, 9, 21, 9, 0),  # Monday morning
            cadence=DURING_THE_TERM,
        ).ok

    def test_exactly_at_the_threshold_is_still_within(self) -> None:
        assert judge(
            last_commit=datetime(2026, 9, 15, 9, 0),
            now=datetime(2026, 9, 18, 9, 0),
            cadence=DURING_THE_TERM,
        ).ok

    def test_one_hour_past_the_threshold_is_not(self) -> None:
        assert not judge(
            last_commit=datetime(2026, 9, 15, 8, 0),
            now=datetime(2026, 9, 18, 9, 0),
            cadence=DURING_THE_TERM,
        ).ok


class TestStandingDown:
    """After the date in the cadence file the alarm passes and says why. The
    alternative - somebody disabling the workflow in week 12 - is the same act
    that cost twenty-three days, and it would leave nothing behind saying when
    it was expected back."""

    def test_after_the_date_silence_is_not_judged(self) -> None:
        verdict = judge(
            last_commit=datetime(2026, 10, 1),
            now=datetime(2026, 11, 5),
            cadence=DURING_THE_TERM,
        )
        assert verdict.ok

    def test_and_it_says_so_rather_than_only_passing(self) -> None:
        verdict = judge(
            last_commit=datetime(2026, 10, 1),
            now=datetime(2026, 11, 5),
            cadence=DURING_THE_TERM,
        )
        assert "not being judged" in verdict.message
        assert "the report weeks" in verdict.message

    def test_the_last_day_is_still_judged(self) -> None:
        """`expected_until` is inclusive: the alarm stands down the day after."""
        assert not judge(
            last_commit=datetime(2026, 10, 1),
            now=datetime(2026, 10, 22, 23, 0),
            cadence=DURING_THE_TERM,
        ).ok


class TestTheCadenceFile:
    def test_it_parses_and_carries_the_three_things_the_check_needs(self) -> None:
        allowed, until, after = read_cadence()
        assert allowed > 0
        assert isinstance(until, date)
        assert after.strip()

    def test_the_window_ends_before_the_report_is_due(self) -> None:
        """Not a style rule. A cadence expected past the deadline would fire
        through the two weeks reserved for writing, which is when somebody turns
        it off for good."""
        _, until, _ = read_cadence()
        assert until < date(2026, 11, 12)

    def test_the_file_explains_how_to_stand_it_down(self) -> None:
        """The failure being prevented is somebody removing the workflow. The
        file has to offer the supported alternative where they will look."""
        text = (Path(__file__).resolve().parent.parent / "config" / "cadence.yaml").read_text(
            encoding="utf-8"
        )
        assert "Turning" in text and "workflow off" in text


@pytest.mark.parametrize("hours", [0, 1, 47, 71, 72])
def test_anything_inside_the_window_passes(hours: int) -> None:
    assert judge(
        last_commit=datetime(2026, 9, 18, 0, 0),
        now=datetime(2026, 9, 18, 0, 0) + timedelta(hours=hours),
        cadence=DURING_THE_TERM,
    ).ok


class TestMixedTimezones:
    """The workflow passes `git log --format=%cI`, which carries an offset, and
    `date -u`, which does not. The first run of it raised on the subtraction,
    and the workflow reads a crash as silence - so the alarm would have opened
    an issue containing a traceback every morning until somebody muted it.
    """

    def test_an_offset_commit_time_against_a_naive_now(self) -> None:
        bangkok = timezone(timedelta(hours=7))
        assert judge(
            last_commit=datetime(2026, 9, 18, 21, 0, tzinfo=bangkok),  # 14:00 UTC
            now=datetime(2026, 9, 18, 15, 0),  # naive, meaning UTC
            cadence=DURING_THE_TERM,
        ).ok

    def test_the_offset_is_honoured_rather_than_dropped(self) -> None:
        """Dropping it would read 21:00 Bangkok as 21:00 UTC and make the gap
        seven hours shorter, which on the boundary is the difference between
        firing and not."""
        bangkok = timezone(timedelta(hours=7))
        aware = datetime(2026, 9, 15, 20, 0, tzinfo=bangkok)  # 13:00 UTC
        assert not judge(
            last_commit=aware,
            now=datetime(2026, 9, 18, 14, 0),  # 73 hours later in UTC
            cadence=DURING_THE_TERM,
        ).ok

    def test_a_naive_moment_is_taken_as_utc(self) -> None:
        assert as_utc(datetime(2026, 9, 18, 12, 0)).tzinfo is UTC

    def test_an_aware_moment_keeps_its_instant(self) -> None:
        bangkok = timezone(timedelta(hours=7))
        assert as_utc(datetime(2026, 9, 18, 21, 0, tzinfo=bangkok)).hour == 14

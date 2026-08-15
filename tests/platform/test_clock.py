"""Clock port behaviour (ADR-028).

The tests that matter here are the ones showing what the port buys us: a shift
handover, a cooldown and an ETA expiry can all be exercised without a single
real second passing. Those three cases are invariants promised by ADR-023 and
ADR-025; without an injectable clock they would be untestable in CI and would
therefore pass by never being checked.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta, timezone

import pytest

from pdm.platform.clock import Clock, ScaledClock, SimulatedClock, SystemClock

BANGKOK = timezone(timedelta(hours=7))
MORNING_SHIFT_START = datetime(2026, 3, 3, 6, 0, tzinfo=BANGKOK)


def test_every_implementation_satisfies_the_port() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(SimulatedClock(MORNING_SHIFT_START), Clock)
    assert isinstance(ScaledClock(60.0), Clock)


class TestSystemClock:
    def test_now_is_timezone_aware_utc(self) -> None:
        now = SystemClock().now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_negative_sleep_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            SystemClock().sleep(-1)


class TestScaledClock:
    """Real time running fast: what a compressed demo runs on (ADR-044 §4).

    It exists because `SimulatedClock` cannot serve a long-running process - its
    `sleep` returns instantly, so a worker on one spins - and because putting the
    compression anywhere else splits source time from decision time. Every window
    in the system is measured on decision time, so a feed that ran fast against a
    clock that did not would put a ticket's "in about six hours" six minutes
    away, and no prediction could ever reach its own expiry.
    """

    def test_now_is_timezone_aware_utc(self) -> None:
        now = ScaledClock(60.0).now()
        assert now.tzinfo is not None
        assert now.utcoffset() == timedelta(0)

    def test_it_starts_where_it_is_told_and_moves_forward(self) -> None:
        clock = ScaledClock(60.0, origin=MORNING_SHIFT_START)
        first = clock.now()
        clock.sleep(60)
        second = clock.now()

        assert first >= MORNING_SHIFT_START
        assert second > first

    def test_a_scaled_second_costs_less_real_time(self) -> None:
        """The whole point: ten seconds of the timings in policy.yaml cost a
        sixth of a real second at 60x, so twelve hours of degradation fits in one
        sitting (ADR-007)."""
        clock = ScaledClock(60.0, origin=MORNING_SHIFT_START)
        before = time.monotonic()

        clock.sleep(6)

        assert time.monotonic() - before < 0.5
        assert clock.now() >= MORNING_SHIFT_START + timedelta(seconds=6)

    def test_at_speed_one_it_is_ordinary_time(self) -> None:
        clock = ScaledClock(1.0, origin=MORNING_SHIFT_START)
        clock.sleep(0.01)

        assert clock.now() - MORNING_SHIFT_START < timedelta(seconds=1)

    def test_a_negative_sleep_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            ScaledClock(60.0).sleep(-1)

    def test_a_speed_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            ScaledClock(0.0)

    def test_a_naive_origin_is_rejected(self) -> None:
        """ADR-028, for the third time in this file: the night shift crosses
        midnight."""
        with pytest.raises(ValueError, match="ADR-028"):
            ScaledClock(60.0, origin=datetime(2026, 3, 3, 6, 0))


class TestSimulatedClock:
    def test_starts_at_the_given_moment_normalised_to_utc(self) -> None:
        clock = SimulatedClock(MORNING_SHIFT_START)
        assert clock.now() == MORNING_SHIFT_START
        assert clock.now().utcoffset() == timedelta(0)

    def test_naive_start_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone-aware"):
            SimulatedClock(datetime(2026, 3, 3, 6, 0))

    def test_advance_moves_forward_and_returns_the_new_time(self) -> None:
        clock = SimulatedClock(MORNING_SHIFT_START)
        assert clock.advance(timedelta(hours=2)) == clock.now()
        assert clock.now() == MORNING_SHIFT_START + timedelta(hours=2)

    def test_sleep_advances_instead_of_waiting(self) -> None:
        clock = SimulatedClock(MORNING_SHIFT_START)
        clock.sleep(300)
        assert clock.now() == MORNING_SHIFT_START + timedelta(minutes=5)

    def test_time_never_moves_backwards(self) -> None:
        clock = SimulatedClock(MORNING_SHIFT_START)
        with pytest.raises(ValueError, match="backwards"):
            clock.advance(timedelta(minutes=-1))
        with pytest.raises(ValueError, match="backwards"):
            clock.advance_to(MORNING_SHIFT_START - timedelta(seconds=1))

    def test_advance_to_an_absolute_moment(self) -> None:
        clock = SimulatedClock(MORNING_SHIFT_START)
        handover = MORNING_SHIFT_START + timedelta(hours=8)
        assert clock.advance_to(handover) == handover


class TestWhatThePortMakesPossible:
    """Cases that could not be tested at all without an injectable clock."""

    def test_a_job_crossing_a_shift_boundary(self) -> None:
        """ADR-025: a job started at 15:00 and finished at 09:00 the next day
        must not be recorded as eighteen hours of repair work. Reproducing this
        against the real clock would take eighteen hours."""
        clock = SimulatedClock(datetime(2026, 3, 3, 15, 0, tzinfo=BANGKOK))
        started = clock.now()

        clock.advance(timedelta(hours=1))  # worked one hour
        first_segment = clock.now() - started

        clock.advance(timedelta(hours=17))  # handed over, shift ended, resumed
        resumed = clock.now()
        clock.advance(timedelta(minutes=30))
        second_segment = clock.now() - resumed

        elapsed = clock.now() - started
        worked = first_segment + second_segment

        assert elapsed == timedelta(hours=18, minutes=30)
        assert worked == timedelta(hours=1, minutes=30)

    def test_a_cooldown_expiring(self) -> None:
        """ADR-023: after a Finding resolves, a cooldown must pass before the
        same rule may raise a new one."""
        clock = SimulatedClock(MORNING_SHIFT_START)
        resolved_at = clock.now()
        cooldown = timedelta(minutes=30)

        clock.advance(timedelta(minutes=29))
        assert clock.now() - resolved_at < cooldown

        clock.advance(timedelta(minutes=2))
        assert clock.now() - resolved_at > cooldown

    def test_thirty_hours_of_scenario_cost_no_real_time(self) -> None:
        """design.md 7: the simulator must run hundreds of scenarios in CI."""
        clock = SimulatedClock(MORNING_SHIFT_START)
        for _ in range(30 * 60):
            clock.sleep(60)
        assert clock.now() == MORNING_SHIFT_START + timedelta(hours=30)


def test_utc_start_is_accepted_unchanged() -> None:
    start = datetime(2026, 3, 3, 0, 0, tzinfo=UTC)
    assert SimulatedClock(start).now() == start

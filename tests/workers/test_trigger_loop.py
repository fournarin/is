"""Signals in, tickets out, against a real PostgreSQL (ADR-044).

Every layer below this has been tested on its own: the rule engine decides, the
store holds one live record per (machine, rule), the work module prices a ticket.
This file is the first time anything runs them as one pipeline, and the tests
that matter are the ones where the layers disagree about the world:

  * `TestOneFaultOneTicket` - invariant 8 through the *whole* pipeline. Slice 5.1
    proved a hundred firings make one Finding; the failure ADR-023 was written
    about is a hundred *work orders*, and nothing has been able to check that
    until there was something issuing them.
  * `TestAPredictionOvertaken` - a prediction that comes true leaves a ticket
    describing a crossing that has already happened. Two tickets for one fault is
    what supersession exists to prevent, and until this slice it prevented it in
    a table nobody was reading.
  * `TestTheChain` - the tick schedules its successor, and the case where it
    does not is the one that stops layer 1 for ever with everything else still
    running.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    FindingKind,
    FindingStatus,
    MachineId,
    RuleId,
    Signal,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.signals import Feed
from pdm.triggers import Triggers
from pdm.triggers import repo as findings
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.workers.runtime.handlers import TriggerLoop, ensure_tick_queued, observe_handler

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-001")
TEMP_RULE = RuleId("R-motor-temp-high")
TREND_RULE = RuleId("R-motor-temp-high/trend")

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
TIMING = ClassTiming(heartbeat_seconds=10, dead_after_seconds=60)
PERIOD = timedelta(seconds=TIMING.heartbeat_seconds)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE work_order, finding, job CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


class Recorded:
    """A source of exactly these signals (the shape a replay file will have)."""

    def __init__(self, signals: list[Signal]) -> None:
        self._signals = tuple(signals)

    def stream(self) -> Iterator[Signal]:
        return iter(self._signals)


def _hot(at: datetime, value: float = 91.0) -> Signal:
    return Signal(
        timestamp=at, machine_id=MOTOR, metric_name="motor_temp_c", value=value, unit="degC"
    )


def _two_minutes_of_heat(start: datetime) -> list[Signal]:
    """Three readings spanning the 120 seconds R-motor-temp-high requires."""
    return [_hot(start + timedelta(seconds=60 * index)) for index in range(3)]


def _warming(start: datetime = NOW, *, per_hour: float = 2.0, count: int = 24) -> list[Signal]:
    """Rising towards 85 but not there yet, every five minutes."""
    step = per_hour * (5 / 60)
    return [
        _hot(start + timedelta(minutes=5 * index), value=70.0 + step * index)
        for index in range(count)
    ]


def _loop(
    clock: SimulatedClock,
    signals: list[Signal],
    *,
    predicting: bool = True,
    fallback: dict[str, Any] | None = None,
) -> TriggerLoop:
    policy = CONFIG.policy.triggers
    triggers = Triggers(
        clock,
        CONFIG.rules.rules,
        cooldown=timedelta(minutes=policy.cooldown_minutes),
        eta_grace=timedelta(minutes=policy.eta_grace_minutes),
        model_of=CONFIG.model_of,
        trend_window=timedelta(minutes=policy.trend.window_minutes) if predicting else None,
        trend_min_samples=policy.trend.min_samples,
        trend_horizon=timedelta(hours=policy.trend.max_horizon_hours),
    )
    return TriggerLoop(
        triggers=triggers,
        orders=WorkOrders(clock, fallback_minutes=FALLBACK if fallback is None else fallback),
        config=CONFIG,
        clock=clock,
        # A test advances the clock by the interval the signals were sampled at
        # and gets exactly those signals. A compressed demo differs only in how
        # fast the clock moves (ADR-044 §4).
        feed=Feed(Recorded(signals), decision_origin=clock.now()),
    )


def _open_orders(conn: Connection[Any]) -> list[tuple[str, Any, Any]]:
    return work.open_orders(conn)


class TestOneFaultOneTicket:
    """Invariant 8, through the pipeline rather than at the table."""

    def test_a_sustained_excess_becomes_a_finding_and_a_ticket(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        loop = _loop(clock, _two_minutes_of_heat(NOW))
        clock.advance(timedelta(minutes=3))

        tick = loop.tick(conn)

        assert len(tick.issued) == 1
        assert len(tick.observation.raised) == 1
        _, order, _ = _open_orders(conn)[0]
        assert order.origin is WorkOrderOrigin.CONDITION
        assert order.machine_id == MOTOR
        assert order.finding_kind is FindingKind.DETECTED
        assert "detected by R-motor-temp-high" in order.reason

    def test_a_hundred_more_hot_readings_are_still_one_ticket(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The failure ADR-023 opens with. One overheating motor becoming a
        hundred work orders is what takes `load_ratio` past 100% and makes the
        gate hold back everything - the system destroying itself in its first
        hour on real data."""
        heat = _two_minutes_of_heat(NOW) + [
            _hot(NOW + timedelta(seconds=180 + 60 * index)) for index in range(100)
        ]
        loop = _loop(clock, heat)
        clock.advance(timedelta(hours=3))

        tick = loop.tick(conn)

        assert len(tick.issued) == 1
        assert tick.observation.repeated == 100
        assert len(_open_orders(conn)) == 1
        stored = findings.live(conn)[(MOTOR, TEMP_RULE)]
        assert stored.occurrence_count == 101

    def test_a_quiet_machine_produces_nothing(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        cool = [_hot(NOW + timedelta(minutes=index), value=61.0) for index in range(30)]
        loop = _loop(clock, cool)
        clock.advance(timedelta(hours=1))

        tick = loop.tick(conn)

        assert tick.signals == 30
        assert tick.issued == ()
        assert not tick.observation.anything_happened
        assert findings.live(conn) == {}
        assert _open_orders(conn) == []


class TestPredictedWork:
    def test_a_forecast_becomes_a_ticket_that_reads_differently(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """ADR-020: predicted work is the clearest example of what a quiet shift
        should absorb, and a prediction nobody can be sent to is a prediction
        nobody acts on. The sentence differs because the decision differs."""
        loop = _loop(clock, _warming())
        clock.advance(timedelta(hours=2))

        tick = loop.tick(conn)

        assert len(tick.observation.forecast) == 1
        _, order, _ = _open_orders(conn)[0]
        assert order.finding_kind is FindingKind.PREDICTED
        assert order.eta is not None and order.eta_confidence is not None
        assert "expected to reach the threshold" in order.reason
        assert "give or take" in order.reason

    def test_prediction_is_on_in_this_process(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The point of the slice. The same signals through a loop built without
        a trend window produce nothing, which is how every process in the system
        ran until now."""
        blind = _loop(clock, _warming(), predicting=False)
        clock.advance(timedelta(hours=2))

        tick = blind.tick(conn)

        assert tick.observation.forecast == ()
        assert tick.issued == ()


class TestAPredictionOvertaken:
    """ADR-044 §7. Both halves: the ticket nobody took, and the ticket somebody did."""

    def _forecast_then_crossing(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> tuple[TriggerLoop, str]:
        signals = _warming() + _two_minutes_of_heat(NOW + timedelta(hours=3))
        loop = _loop(clock, signals)
        clock.advance(timedelta(hours=2))
        predicted = loop.tick(conn)
        assert len(predicted.issued) == 1
        return (loop, predicted.issued[0])

    def test_the_ticket_for_a_prediction_that_came_true_is_withdrawn(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        loop, predicted_ref = self._forecast_then_crossing(conn, clock)
        clock.advance(timedelta(hours=2))

        tick = loop.tick(conn)

        assert tick.cancelled == (predicted_ref,)
        assert len(tick.issued) == 1
        withdrawn = work.get(conn, predicted_ref)
        assert withdrawn is not None and withdrawn.status is WorkOrderStatus.CANCELLED
        detected = work.get(conn, tick.issued[0])
        assert detected is not None and detected.finding_kind is FindingKind.DETECTED
        assert len(_open_orders(conn)) == 1

    def test_the_finding_records_why_the_ticket_was_cancelled(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """No column says why. The cancelled order points at its Finding, and
        that row says `superseded` with the reference to what replaced it -
        which is what a trace-back reference is for (ADR-030)."""
        loop, predicted_ref = self._forecast_then_crossing(conn, clock)
        clock.advance(timedelta(hours=2))
        loop.tick(conn)

        order = work.get(conn, predicted_ref)
        assert order is not None and order.finding_ref is not None
        assert findings.status_of(conn, order.finding_ref) is FindingStatus.SUPERSEDED

    def test_a_batch_carrying_both_the_trend_and_the_crossing_leaves_one_ticket(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """One tick, both halves. The feed hands over its whole backlog after any
        stall, so this arrives on its own eventually.

        Written because ticketing detections first passed every other test in
        this class: they all advance the clock between the two, so the
        prediction's ticket always existed by the time the detection withdrew it.
        In one batch it does not, the withdrawal matches nothing, and the
        forecast's ticket is then issued against a Finding that is already
        superseded - which expiry cannot touch and no later detection will
        supersede twice. Two open tickets for one fault, for ever.
        """
        signals = _warming() + _two_minutes_of_heat(NOW + timedelta(hours=3))
        loop = _loop(clock, signals)
        clock.advance(timedelta(hours=4))

        tick = loop.tick(conn)

        assert len(tick.observation.forecast) == 1
        assert len(tick.observation.raised) == 1
        assert len(tick.issued) == 2
        assert len(tick.cancelled) == 1
        open_now = _open_orders(conn)
        assert len(open_now) == 1
        assert open_now[0][1].finding_kind is FindingKind.DETECTED

    def test_a_ticket_somebody_has_accepted_is_left_alone(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """A ticket disappearing from under a technician standing at the machine
        is worse than a ticket whose sentence has aged."""
        loop, predicted_ref = self._forecast_then_crossing(conn, clock)
        work.set_status(conn, predicted_ref, status=WorkOrderStatus.IN_PROGRESS)
        clock.advance(timedelta(hours=2))

        tick = loop.tick(conn)

        assert tick.cancelled == ()
        accepted = work.get(conn, predicted_ref)
        assert accepted is not None and accepted.status is WorkOrderStatus.IN_PROGRESS

    def test_an_expired_prediction_takes_its_untouched_ticket_with_it(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The other way a prediction ends: the ETA and its grace pass with
        nothing happening. Left in the queue, that ticket is work for a fault
        that never came, and `load_ratio` is a sum over the whole open queue."""
        loop = _loop(clock, _warming())
        clock.advance(timedelta(hours=2))
        predicted_ref = loop.tick(conn).issued[0]

        clock.advance(timedelta(days=1))
        tick = loop.tick(conn)

        assert len(tick.expired) == 1
        assert tick.cancelled == (predicted_ref,)
        assert _open_orders(conn) == []
        order = work.get(conn, predicted_ref)
        assert order is not None and order.finding_ref is not None
        assert findings.status_of(conn, order.finding_ref) is FindingStatus.EXPIRED

    def test_expiry_runs_after_observation_not_before(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The ordering in `tick` is a decision. A prediction the data still
        supports has its ETA moved forward by the re-fit; expiring first would
        retire it on the strength of an ETA this very batch was about to
        correct."""
        early = _warming()
        loop = _loop(clock, early + _warming(start=NOW + timedelta(hours=2), count=12))
        clock.advance(timedelta(hours=2))
        loop.tick(conn)
        first = findings.live(conn)[(MOTOR, TREND_RULE)]
        assert first.eta is not None

        clock.advance(timedelta(hours=1))
        tick = loop.tick(conn)

        assert tick.expired == ()
        refreshed = findings.live(conn)[(MOTOR, TREND_RULE)]
        assert refreshed.eta is not None and refreshed.eta > first.eta


class TestUnderRepair:
    """The last piece slice 5.1 left for the loop to fill in.

    The first test is the one that matters, and it is the one the first version
    of `under_repair` could not have passed: the map was built from *live*
    Findings, and a live Finding suppresses its own rule as a repeat long before
    the repair check is reached. The mechanism would have been shipped, carried a
    test, and never once fired.
    """

    def test_a_rule_stays_suppressed_while_the_repair_is_open(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """ADR-023 §4's actual case. The technician resolves the Finding and then
        spends an hour on the machine; the cooldown covers thirty minutes of
        that, and for the rest of it nothing else stops the rule raising a second
        ticket for the job somebody is standing inside the machine doing."""
        later = NOW + timedelta(minutes=45)
        loop = _loop(clock, _two_minutes_of_heat(NOW) + _two_minutes_of_heat(later))
        clock.advance(timedelta(minutes=3))
        first = loop.tick(conn)
        loop.triggers.resolve(conn, first.observation.raised[0].finding_ref)

        # Past the thirty-minute cooldown, with the repair still open.
        clock.advance(timedelta(minutes=45))
        again = loop.tick(conn)

        # Once, on the third reading: the first two are still building the run
        # the rule's `for_seconds` asks for, and only a rule that would have
        # fired can be suppressed.
        assert (again.observation.suppressed, again.observation.quiet) == (1, 2)
        assert again.issued == ()
        assert len(_open_orders(conn)) == 1

    def test_a_rule_with_an_open_ticket_is_reported_as_under_repair(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        loop = _loop(clock, _two_minutes_of_heat(NOW))
        clock.advance(timedelta(minutes=3))
        loop.tick(conn)

        assert loop.under_repair(conn) == {MOTOR: frozenset({TEMP_RULE})}

    def test_a_resolved_finding_still_reports_its_rule(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """No status filter, deliberately: the repair outlives the Finding."""
        loop = _loop(clock, _two_minutes_of_heat(NOW))
        clock.advance(timedelta(minutes=3))
        tick = loop.tick(conn)
        loop.triggers.resolve(conn, tick.observation.raised[0].finding_ref)

        assert loop.under_repair(conn) == {MOTOR: frozenset({TEMP_RULE})}

    def test_a_closed_ticket_stops_suppressing(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        from pdm.contracts import WorkOutcome

        loop = _loop(clock, _two_minutes_of_heat(NOW))
        clock.advance(timedelta(minutes=3))
        ref = loop.tick(conn).issued[0]

        work.close(
            conn,
            ref,
            status=WorkOrderStatus.CLOSED,
            outcome=WorkOutcome.FIXED,
            now=clock.now(),
        )

        assert loop.under_repair(conn) == {}

    def test_nothing_open_means_no_queries_worth_making(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        loop = _loop(clock, [])

        assert loop.under_repair(conn) == {}


class TestWhenSomethingIsWrong:
    def test_a_finding_that_cannot_be_priced_does_not_stop_the_loop(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The whole tick is one transaction. Letting `NoEstimateAvailable` out
        would roll back the Findings this batch raised, and the next tick would
        raise them again and fail again: one machine model missing from
        `fallback_minutes` would stop the pipeline for the whole plant."""
        loop = _loop(clock, _two_minutes_of_heat(NOW), fallback={})
        clock.advance(timedelta(minutes=3))

        tick = loop.tick(conn)

        assert tick.issued == ()
        assert len(tick.unpriced) == 1
        assert findings.live(conn)  # the Finding survives, visibly ticketless
        assert _open_orders(conn) == []

    def test_signals_from_a_machine_that_is_not_on_the_map_are_dropped(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """Invariant 13 guarantees every machine a *rule* names is in the
        topology. It promises nothing about what a live connection will send, and
        `model_of` on an unknown machine is a KeyError that would kill the
        tick."""
        stranger = MachineId("MC-999")
        signals = [
            Signal(
                timestamp=NOW + timedelta(seconds=60 * index),
                machine_id=stranger,
                metric_name="motor_temp_c",
                value=91.0,
                unit="degC",
            )
            for index in range(3)
        ]
        loop = _loop(clock, signals)
        clock.advance(timedelta(minutes=3))

        tick = loop.tick(conn)

        assert tick.unknown_machines == (stranger,)
        assert tick.signals == 0
        assert _open_orders(conn) == []


class TestTheChain:
    """ADR-044 §1 and §3: the schedule is a row, and a lost row is recoverable."""

    def _queue(self, clock: SimulatedClock) -> JobQueue:
        return JobQueue(
            job_class=JobClass.RUNTIME, worker="worker-runtime-1", timing=TIMING, clock=clock
        )

    def _appointments(self, conn: Connection[Any]) -> list[tuple[int, datetime]]:
        """Ticks waiting to run. Not `queue.pending`, which counts the running
        one - correctly, for the question it answers, and not this one."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, available_at FROM job WHERE kind = 'observe' AND status = 'queued' "
                "ORDER BY id"
            )
            return [(int(row[0]), row[1]) for row in cur.fetchall()]

    def test_a_tick_books_the_next_one(self, conn: Connection[Any], clock: SimulatedClock) -> None:
        queue = self._queue(clock)
        loop = _loop(clock, _two_minutes_of_heat(NOW))
        handle = observe_handler(loop, queue, clock, period=PERIOD)
        queue.enqueue(conn, kind=JobKind.OBSERVE)
        claimed = queue.claim(conn)
        assert claimed is not None
        clock.advance(timedelta(minutes=3))

        handle(conn, claimed)

        booked = self._appointments(conn)
        assert len(booked) == 1
        assert booked[0][0] != claimed.id
        assert booked[0][1] == clock.now() + PERIOD

    def test_the_tickets_and_the_appointment_commit_together(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """ADR-017 through the trigger loop: a Finding with no ticket behind it
        and a tick with no successor are the same rollback."""
        queue = self._queue(clock)
        loop = _loop(clock, _two_minutes_of_heat(NOW))
        handle = observe_handler(loop, queue, clock, period=PERIOD)
        queue.enqueue(conn, kind=JobKind.OBSERVE)
        claimed = queue.claim(conn)
        assert claimed is not None
        conn.commit()
        clock.advance(timedelta(minutes=3))

        handle(conn, claimed)
        conn.rollback()

        assert findings.live(conn) == {}
        assert _open_orders(conn) == []
        assert self._appointments(conn) == []

    def test_a_chain_that_died_is_restarted(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = self._queue(clock)

        started = ensure_tick_queued(conn, queue)

        assert started is not None
        assert started.kind == JobKind.OBSERVE.value

    def test_a_chain_that_is_alive_is_not_restarted_twice(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """Including a tick waiting out a retry backoff: ordinary retries belong
        to the queue, and this only catches a chain that has actually stopped."""
        queue = self._queue(clock)
        queue.enqueue(conn, kind=JobKind.OBSERVE, available_at=clock.now() + timedelta(minutes=5))

        assert ensure_tick_queued(conn, queue) is None

    def test_a_running_tick_counts_as_alive(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = self._queue(clock)
        queue.enqueue(conn, kind=JobKind.OBSERVE)
        queue.claim(conn)

        assert ensure_tick_queued(conn, queue) is None

"""Delivery against a real PostgreSQL: what happens when the ticket is refused.

`OwnSystemSink` cannot fail - its destination is the same database - so the
behaviour ADR-068 was written for is exercised with a sink that refuses on
purpose. That is not a workaround. The whole reason layer 4 has a delivery
record is the destination we do not have yet, and a test that only ever used the
one that cannot fail would prove nothing about the design.

Three things carry this file:

  * `TestARefusedTicketComesBackNextRound` - the "done when" of slice 12.1. A
    failure leaves the order placed and the delivery outstanding.
  * `TestOncePerRound` - two rounds over the same placement deliver it once.
  * `TestThePlacementAndTheQueueRowAreOneTransaction` - the direction ADR-068 §2
    says has to hold: a round that rolls back takes its deliveries with it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    MachineId,
    MachineModel,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderRef,
    WorkOrderStatus,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.service import DispatchRounds
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.sinks import Deliveries, DeliveryFailed, OwnSystemSink, Receipt, Ticket
from pdm.sinks import repo as delivery
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.workers.runtime.handlers import dispatch_handler
from tests.modes import automatic

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)  # 15:00 in Bangkok: the afternoon shift
AFTERNOON = ShiftId("afternoon")
TODAY = date(2026, 3, 3)
MACHINE = MachineId("MC-001")
R2000 = MachineModel("R-2000iC")
ANA = UserId("tech-ana")
ALL_SKILLS = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)

# These tests are about layer 4 and about a round meeting a database that moved
# under it, neither of which is what ADR-071's confirmation step is for. They run
# the plant in `automatic`, which is a supported mode rather than a convenience:
# the supervisor path is asserted end to end in
# `tests/dispatch/test_the_confirmation_gate.py`, where it is the subject.
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
TIMING = ClassTiming(heartbeat_seconds=10, dead_after_seconds=60)
PERIOD = timedelta(seconds=CONFIG.policy.dispatch.round_seconds)


class RefusingSink:
    """A destination that says no for the first `times` tickets it is offered.

    Counts what it was asked to take, so a test can tell "delivered once" from
    "delivered twice and recorded once" - which is the difference between
    at-least-once being a decision and being an accident.
    """

    def __init__(self, *, times: int = 1) -> None:
        self.times = times
        self.offered: list[str] = []

    @property
    def destination(self) -> str:
        return "a-cmms-that-is-down"

    def deliver(self, ticket: Ticket) -> Receipt:
        self.offered.append(str(ticket.work_order_ref))
        if len(self.offered) <= self.times:
            raise DeliveryFailed("the CMMS answered 503")
        return Receipt(external_ref=f"CMMS-{len(self.offered)}")


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "ticket_delivery CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def rounds(clock: SimulatedClock) -> DispatchRounds:
    return DispatchRounds(clock, automatic(CONFIG))


@pytest.fixture
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


def _crew(conn: Connection[Any]) -> None:
    dispatch_repo.add_technician(conn, Technician(user=ANA, skills=ALL_SKILLS), now=NOW)
    dispatch_repo.assign_to_shift(
        conn,
        ShiftAssignment(shift_id=AFTERNOON, on_date=TODAY, technician=ANA, available_minutes=480),
    )


def _ticket(orders: WorkOrders, conn: Connection[Any]) -> WorkOrderRef:
    """The repo hands back a plain string; every layer-4 signature is typed on
    `WorkOrderRef`, so the conversion happens once, here."""
    return WorkOrderRef(
        orders.from_report(
            conn,
            machine_id=MACHINE,
            machine_model=R2000,
            severity=Severity.MEDIUM,
            reported_by=UserId("supervisor"),
            description="reported in a test",
        ).ref
    )


def _placed(conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders) -> WorkOrderRef:
    _crew(conn)
    ref = _ticket(orders, conn)
    report = rounds.run(conn)
    assert report.placed == (ref,)
    return ref


class TestARefusedTicketComesBackNextRound:
    def test_the_order_stays_placed_when_the_destination_says_no(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """ADR-068 §2. A CMMS being down is a fact about the CMMS, and taking
        the job back from a technician who can already see it would turn
        somebody else's outage into our own."""
        ref = _placed(conn, rounds, orders)

        report = Deliveries(RefusingSink(), clock).run(conn, placed=[ref])

        assert report.failed == (ref,)
        order = work.get(conn, ref)
        assert order is not None
        assert order.status is WorkOrderStatus.ASSIGNED
        assert tuple(one.user for one in order.assignees) == (ANA,)

    def test_the_failure_says_what_the_destination_said(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """ "Why did this ticket never arrive" is asked days later, by somebody
        who cannot see the log line that would have answered it."""
        ref = _placed(conn, rounds, orders)

        Deliveries(RefusingSink(), clock).run(conn, placed=[ref])

        row = delivery.state_of(conn, ref)
        assert row is not None
        assert row["state"] == "failed"
        assert row["destination"] == "a-cmms-that-is-down"
        assert "503" in row["last_error"]
        assert row["delivered_at"] is None

    def test_the_next_pass_delivers_it_without_being_told_about_it(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """The retry is the point. The second pass is given no placements at all
        - it works from the table, which is what makes a failure last round
        indistinguishable from a placement this one (ADR-068 §1)."""
        ref = _placed(conn, rounds, orders)
        sink = RefusingSink(times=1)
        deliveries = Deliveries(sink, clock)

        deliveries.run(conn, placed=[ref])
        second = deliveries.run(conn)

        assert second.delivered == (ref,)
        row = delivery.state_of(conn, ref)
        assert row is not None
        assert row["state"] == "delivered"
        assert row["external_ref"] == "CMMS-2"
        # Both attempts counted. ADR-068 §4 caps nothing, so a climbing count is
        # what makes a stuck destination visible to whoever looks.
        assert row["attempts"] == 2
        assert row["last_error"] is None

    def test_a_destination_that_stays_down_keeps_the_ticket_outstanding(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """There is no attempt cap, and this is what that means: five rounds
        later the ticket is still asking to be sent. A cap would mean choosing
        how many failures are acceptable before a machine goes unattended."""
        ref = _placed(conn, rounds, orders)
        deliveries = Deliveries(RefusingSink(times=99), clock)

        deliveries.run(conn, placed=[ref])
        for _ in range(4):
            deliveries.run(conn)

        row = delivery.state_of(conn, ref)
        assert row is not None
        assert row["state"] == "failed"
        assert row["attempts"] == 5


class TestOncePerRound:
    def test_a_delivered_ticket_is_not_offered_again(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        ref = _placed(conn, rounds, orders)
        sink = RefusingSink(times=0)
        deliveries = Deliveries(sink, clock)

        deliveries.run(conn, placed=[ref])
        again = deliveries.run(conn, placed=[ref])

        assert again.delivered == ()
        assert sink.offered == [ref]

    def test_a_round_replayed_after_a_crash_queues_nothing_new(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """`ON CONFLICT DO NOTHING` is the whole of it. A worker that died
        between the placement and its own commit re-runs the round and must not
        arrive at two rows for one order."""
        ref = _placed(conn, rounds, orders)
        deliveries = Deliveries(OwnSystemSink(), clock)

        deliveries.run(conn, placed=[ref])
        deliveries.run(conn, placed=[ref])

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ticket_delivery WHERE work_order_ref = %s", (ref,))
            row = cur.fetchone()
        assert row is not None and row[0] == 1


class TestThePlacementAndTheQueueRowAreOneTransaction:
    def test_a_round_that_rolls_back_takes_its_deliveries_with_it(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """ADR-068 §2, the direction that has to hold. There can be no ticket
        placed with nothing knowing it has to go out - the same argument ADR-017
        makes for putting the job queue in PostgreSQL."""
        _crew(conn)
        _ticket(orders, conn)
        conn.commit()

        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)
        handle = dispatch_handler(
            rounds, queue, clock, period=PERIOD, deliveries=Deliveries(OwnSystemSink(), clock)
        )
        queue.enqueue(conn, kind=JobKind.DISPATCH)
        claimed = queue.claim(conn)
        assert claimed is not None

        handle(conn, claimed)
        conn.rollback()

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ticket_delivery")
            row = cur.fetchone()
        assert row is not None and row[0] == 0


class TestTheWorkerSendsWhatTheRoundPlaced:
    def test_one_tick_places_and_delivers(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """End to end through the composition root, which is the only place that
        knows both layer 3 and layer 4 exist (ADR-068)."""
        _crew(conn)
        ref = _ticket(orders, conn)

        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)
        handle = dispatch_handler(
            rounds, queue, clock, period=PERIOD, deliveries=Deliveries(OwnSystemSink(), clock)
        )
        queue.enqueue(conn, kind=JobKind.DISPATCH)
        claimed = queue.claim(conn)
        assert claimed is not None

        handle(conn, claimed)

        row = delivery.state_of(conn, ref)
        assert row is not None
        assert row["state"] == "delivered"
        assert row["destination"] == "own-system"
        assert row["external_ref"] == ref

    def test_a_round_with_no_sink_leaves_the_tickets_where_it_put_them(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """`deliveries=None` is the behaviour before layer 4 existed, kept so a
        test about scheduling need not stand up a destination."""
        _crew(conn)
        ref = _ticket(orders, conn)

        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)
        handle = dispatch_handler(rounds, queue, clock, period=PERIOD)
        queue.enqueue(conn, kind=JobKind.DISPATCH)
        claimed = queue.claim(conn)
        assert claimed is not None

        handle(conn, claimed)

        assert delivery.state_of(conn, ref) is None
        order = work.get(conn, ref)
        assert order is not None
        assert order.status is WorkOrderStatus.ASSIGNED

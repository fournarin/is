"""The PM schedule as a chain in a process, against a real PostgreSQL (ADR-083).

`tests/work/test_the_pm_schedule.py` covers what falls due. This covers the two
things only the process can get wrong:

  * **the appointment.** A scan books the next scan in its own transaction, so a
    scan that failed leaves none and `ensure_pm_scan_queued` is what starts the
    chain again (ADR-044 §3). A chain that stops is a plant whose preventive
    maintenance silently stops with it.
  * **the chain is its own.** The scan does not travel with the dispatch round,
    because a scan that failed would then roll back the round it travelled with,
    and one bad task would stop the plant being scheduled at all.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import MachineId, WorkOrderOrigin
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.workers.runtime.handlers import ensure_pm_scan_queued, pm_scan_handler

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
PERIOD = timedelta(seconds=CONFIG.policy.dispatch.round_seconds)
TIMING = ClassTiming(heartbeat_seconds=10, dead_after_seconds=60)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE work_order, pm_task, job CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def queue(clock: SimulatedClock) -> JobQueue:
    return JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)


@pytest.fixture
def handle(clock: SimulatedClock, queue: JobQueue) -> Any:
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    return pm_scan_handler(orders, CONFIG, queue, clock, period=PERIOD)


def _job(queue: JobQueue, conn: Connection[Any]) -> Any:
    job = queue.claim(conn)
    assert job is not None
    assert job.kind == JobKind.PM_SCAN.value
    return job


class TestTheScanRuns:
    def test_it_registers_the_configured_schedule_and_issues_what_is_due(
        self, conn: Connection[Any], queue: JobQueue, handle: Any
    ) -> None:
        """A plant that has just installed this knows no last-done dates, so
        its whole schedule is due at once (ADR-083 section 4)."""
        ensure_pm_scan_queued(conn, queue)

        handle(conn, _job(queue, conn))

        tasks = work.pm_tasks(conn)
        assert len(tasks) == len(CONFIG.pm_tasks)
        orders = [order for _, order, _ in work.open_orders(conn)]
        assert len(orders) == len(CONFIG.pm_tasks)
        assert all(order.origin is WorkOrderOrigin.SCHEDULED for order in orders)

    def test_a_second_scan_issues_nothing_more(
        self, conn: Connection[Any], queue: JobQueue, handle: Any, clock: SimulatedClock
    ) -> None:
        ensure_pm_scan_queued(conn, queue)
        job = _job(queue, conn)
        handle(conn, job)
        queue.finish(conn, job)
        before = len(work.open_orders(conn))

        # The successor the first scan booked, when its moment comes.
        clock.advance(PERIOD)
        handle(conn, _job(queue, conn))

        assert len(work.open_orders(conn)) == before

    def test_it_books_the_next_scan_a_round_later(
        self, conn: Connection[Any], queue: JobQueue, handle: Any, clock: SimulatedClock
    ) -> None:
        """The cadence is the dispatch round's, which is a number `policy.yaml`
        holds once rather than a constant this slice invented."""
        ensure_pm_scan_queued(conn, queue)
        job = _job(queue, conn)

        handle(conn, job)

        # Finished first: a running job counts as pending, and the appointment
        # being asked about is the one the scan just booked.
        queue.finish(conn, job)
        pending = queue.pending(conn, kind=JobKind.PM_SCAN, payload={})
        assert pending is not None
        assert pending.available_at == clock.now() + PERIOD

    def test_every_ticket_names_the_machine_it_is_for(
        self, conn: Connection[Any], queue: JobQueue, handle: Any
    ) -> None:
        ensure_pm_scan_queued(conn, queue)

        handle(conn, _job(queue, conn))

        scheduled = {MachineId(task.machine_id) for task in CONFIG.pm_tasks}
        assert {order.machine_id for _, order, _ in work.open_orders(conn)} == scheduled


class TestTheChainStartsAgain:
    def test_seeding_twice_leaves_one_appointment(
        self, conn: Connection[Any], queue: JobQueue
    ) -> None:
        """The same `pending` primitive the other two chains use: a scan that is
        queued, running or waiting out a backoff counts as coming."""
        first = ensure_pm_scan_queued(conn, queue)

        second = ensure_pm_scan_queued(conn, queue)

        assert first is not None
        assert second is None

    def test_a_chain_that_has_stopped_is_restarted(
        self, conn: Connection[Any], queue: JobQueue, handle: Any
    ) -> None:
        ensure_pm_scan_queued(conn, queue)
        job = _job(queue, conn)
        queue.finish(conn, job)

        assert ensure_pm_scan_queued(conn, queue) is not None

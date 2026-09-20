"""The second source of work, against a real PostgreSQL (ADR-010, ADR-083).

Three questions decide whether this slice is worth anything, and each of them is
a way the schedule could quietly destroy the queue rather than fill it:

  * `TestOneOrderAtATime` - a task whose order is still open does not get a
    second one. Stacking is how a neglected machine pushes `load_ratio` past the
    gate and holds back condition work, which is ADR-023's argument arriving at
    the other origin. The unique index is asserted directly, not only through
    the scan, because the scan is not the last writer that will ever exist.
  * `TestClosingMovesTheClock` - only `fixed` means the maintenance happened, and
    the next occurrence falls out of the interval. Advancing on `not_fixed`
    would hide an undone job for the length of the interval.
  * `TestATaskNobodyHasRecorded` - a task with no `last_done_at` is due from the
    day it was registered, and both the ticket and the reading say so rather
    than implying somebody knows when it was last done.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg.errors import UniqueViolation

from pdm.contracts import (
    MachineId,
    MachineModel,
    PMTaskRef,
    Severity,
    SymptomCode,
    UserId,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.work.repo import PmTaskDefinition

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
BELT = timedelta(hours=8000)  # the R-2000iC manual, page 5
MOTOR = MachineId("MC-001")
OTHER = MachineId("MC-004")
R2000 = MachineModel("R-2000iC")
PM_BELT = SymptomCode("PM-toothed-belt")
TECHNICIAN = UserId("tech-1")

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}

ONE = PmTaskDefinition(
    pm_task_ref=PMTaskRef("pm-mc-001-toothed-belt"),
    machine_id=MOTOR,
    symptom_code=PM_BELT,
    interval=BELT,
)
TWO = PmTaskDefinition(
    pm_task_ref=PMTaskRef("pm-mc-004-toothed-belt"),
    machine_id=OTHER,
    symptom_code=PM_BELT,
    interval=BELT,
)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE work_order, pm_task CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


def _model(machine_id: MachineId) -> MachineModel:
    return CONFIG.model_of(machine_id)


def _scan(conn: Connection[Any], orders: WorkOrders) -> Any:
    return orders.issue_due_pm(conn, machine_model=_model)


def _register(conn: Connection[Any], orders: WorkOrders, *tasks: PmTaskDefinition) -> None:
    orders.register_pm_tasks(conn, list(tasks))


def _accept_and_close(
    conn: Connection[Any],
    orders: WorkOrders,
    clock: SimulatedClock,
    ref: str,
    *,
    outcome: WorkOutcome,
) -> None:
    orders.accept(conn, ref, user=TECHNICIAN)
    orders.start(conn, ref, user=TECHNICIAN)
    clock.advance(timedelta(minutes=30))
    orders.close(conn, ref, user=TECHNICIAN, outcome=outcome)


class TestTheTableMirrorsTheConfiguration:
    def test_registering_writes_one_row_per_configured_task(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE, TWO)

        tasks = work.pm_tasks(conn)

        assert [task.pm_task_ref for task in tasks] == [ONE.pm_task_ref, TWO.pm_task_ref]
        assert all(task.last_done_at is None for task in tasks)

    def test_a_task_that_leaves_the_configuration_stops_being_scheduled(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """An operator deleting a task from plant.yaml has stopped the work.
        Leaving the row would keep issuing tickets nobody asked for."""
        _register(conn, orders, ONE, TWO)

        _register(conn, orders, ONE)

        assert [task.pm_task_ref for task in work.pm_tasks(conn)] == [ONE.pm_task_ref]

    def test_correcting_an_interval_does_not_undo_the_maintenance(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE)
        done_at = NOW - timedelta(days=10)
        work.record_pm_done(conn, ONE.pm_task_ref, at=done_at)

        _register(conn, orders, ONE._replace(interval=timedelta(hours=4000)))

        task = work.pm_tasks(conn)[0]
        assert task.last_done_at == done_at
        assert task.interval == timedelta(hours=4000)
        assert task.due_at == done_at + timedelta(hours=4000)


class TestWhatFallsDue:
    def test_a_due_task_becomes_one_scheduled_order(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE)

        scan = _scan(conn, orders)

        assert scan.due == 1
        assert len(scan.issued) == 1
        order = work.get(conn, scan.issued[0])
        assert order is not None
        assert order.origin is WorkOrderOrigin.SCHEDULED
        assert order.severity is Severity.LOW
        assert order.pm_task_ref == ONE.pm_task_ref
        assert order.status is WorkOrderStatus.QUEUED

    def test_a_task_not_yet_due_is_left_alone(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE)
        work.record_pm_done(conn, ONE.pm_task_ref, at=NOW - BELT / 2)

        scan = _scan(conn, orders)

        assert scan.due == 0
        assert scan.issued == ()

    def test_a_task_with_no_playbook_and_no_fallback_is_skipped_not_raised(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """One unpriceable task may not stop the schedule for the whole plant.
        The same argument the trigger loop makes about one unpriceable Finding.
        """
        priced = WorkOrders(clock, fallback_minutes=FALLBACK)
        unpriced = WorkOrders(clock, fallback_minutes={})
        _register(conn, priced, ONE, TWO)

        scan = unpriced.issue_due_pm(conn, machine_model=_model)

        assert scan.due == 2
        assert scan.issued == ()
        assert set(scan.unpriced) == {ONE.pm_task_ref, TWO.pm_task_ref}


class TestOneOrderAtATime:
    def test_a_second_scan_issues_nothing_while_the_first_order_is_open(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE)
        first = _scan(conn, orders)

        second = _scan(conn, orders)

        assert len(first.issued) == 1
        assert second.issued == ()
        assert second.due == 0

    @pytest.mark.parametrize(
        "status",
        [
            WorkOrderStatus.PROPOSED,
            WorkOrderStatus.ASSIGNED,
            WorkOrderStatus.IN_PROGRESS,
            WorkOrderStatus.HANDED_OVER,
        ],
    )
    def test_every_status_a_shift_has_not_finished_counts_as_in_flight(
        self, conn: Connection[Any], orders: WorkOrders, status: WorkOrderStatus
    ) -> None:
        """A proposal a supervisor rejected goes back to `queued` (ADR-071), so
        every one of these is a state the task must not be issued again from."""
        _register(conn, orders, ONE)
        issued = _scan(conn, orders).issued[0]
        # `handed_over` carries a note or the table refuses the row, which is
        # its own small proof that these statuses are the real ones.
        note = "handed over mid-shift" if status is WorkOrderStatus.HANDED_OVER else None
        conn.execute(
            "UPDATE work_order SET status = %s, handover_note = %s WHERE work_order_ref = %s",
            (status.value, note, issued),
        )

        assert _scan(conn, orders).issued == ()

    def test_the_database_refuses_a_second_live_order_whoever_writes_it(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """The scan skips; the index refuses. A script, a second worker or the
        next writer of this table gets the same answer (migration 0013)."""
        _register(conn, orders, ONE)
        _scan(conn, orders)

        with pytest.raises(UniqueViolation):
            conn.execute(
                "INSERT INTO work_order (origin, pm_task_ref, machine_id, severity, "
                "playbook_snapshot, estimated_minutes, required_technicians, "
                "estimate_is_fallback, reason, status, assignees, work_segments, "
                "blocked_minutes, blocked_reason, created_at) "
                "VALUES ('scheduled', %s, %s, 'low', '[]'::jsonb, 30, 1, true, "
                "'a second ticket for one task', 'queued', '[]'::jsonb, '[]'::jsonb, "
                "0, '{}', %s)",
                (str(ONE.pm_task_ref), str(MOTOR), NOW),
            )
        conn.rollback()

    def test_a_cancelled_order_makes_the_task_eligible_again(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """Nothing in the system cancels a scheduled order today, and if
        something does, the work is still owed. One replacement, not a loop."""
        _register(conn, orders, ONE)
        issued = _scan(conn, orders).issued[0]
        conn.execute(
            "UPDATE work_order SET status = 'cancelled' WHERE work_order_ref = %s", (issued,)
        )

        again = _scan(conn, orders)

        assert len(again.issued) == 1
        assert _scan(conn, orders).issued == ()


class TestClosingMovesTheClock:
    def test_closing_it_fixed_records_the_maintenance_and_sets_the_next_occurrence(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        _register(conn, orders, ONE)
        issued = _scan(conn, orders).issued[0]

        _accept_and_close(conn, orders, clock, issued, outcome=WorkOutcome.FIXED)

        task = work.pm_tasks(conn)[0]
        assert task.last_done_at == clock.now()
        assert task.due_at == clock.now() + BELT
        assert _scan(conn, orders).issued == ()

    @pytest.mark.parametrize(
        "outcome",
        [WorkOutcome.NOT_FIXED, WorkOutcome.TEMPORARY_FIX, WorkOutcome.NO_PROBLEM_FOUND],
    )
    def test_any_other_outcome_leaves_the_task_owed(
        self,
        conn: Connection[Any],
        orders: WorkOrders,
        clock: SimulatedClock,
        outcome: WorkOutcome,
    ) -> None:
        """A PM order closed `not_fixed` is a job that did not happen. The next
        scan issues it again, which is a ticket reappearing - the right
        direction, and the cost ADR-083 section 5 states."""
        _register(conn, orders, ONE)
        issued = _scan(conn, orders).issued[0]

        _accept_and_close(conn, orders, clock, issued, outcome=outcome)

        assert work.pm_tasks(conn)[0].last_done_at is None
        assert len(_scan(conn, orders).issued) == 1

    def test_a_completion_may_not_move_backwards(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """A demo seeding a date, or a closure recorded late, may not undo a
        completion already written."""
        _register(conn, orders, ONE)
        work.record_pm_done(conn, ONE.pm_task_ref, at=NOW)

        moved = work.record_pm_done(conn, ONE.pm_task_ref, at=NOW - timedelta(days=30))

        assert moved is False
        assert work.pm_tasks(conn)[0].last_done_at == NOW


class TestATaskNobodyHasRecorded:
    def test_it_is_due_from_the_day_it_was_registered(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        _register(conn, orders, ONE)

        task = work.pm_tasks(conn)[0]

        assert task.last_done_at is None
        assert task.due_at == NOW
        assert task.is_due(NOW)

    def test_the_ticket_says_so_rather_than_implying_a_date(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """A reason is read by somebody standing at a machine (ADR-005). "Due
        today" with no last-done date would read as a plant that knows."""
        _register(conn, orders, ONE)

        issued = _scan(conn, orders).issued[0]

        order = work.get(conn, issued)
        assert order is not None
        assert "never recorded as done" in order.reason
        assert "8,000 hours" in order.reason

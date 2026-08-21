"""A scheduling round in a process, against a real PostgreSQL (ADR-045, #28).

Slice 6.1 made `dispatch()` a pure function that decides and nothing called it.
This is the first time layer 3 exists in something a technician could be
affected by, and the tests that matter are the three where the decision meets a
database that moved underneath it:

  * `TestARoundIsAllOrNothing` - a round that dies before its commit must leave
    nothing. Half a round is a shift where two of five people were told to go
    somewhere and three were not, and nothing in the system would say so.
  * `TestWorkNobodyMayTouch` - an order somebody has accepted keeps its
    assignee, even when a better-scoring ticket arrives in the same round. This
    is design.md 6.2 through the process rather than in the function.
  * `TestTheSameWorldGivesTheSameWrites` - invariant 10 where it is hardest to
    hold: not "the function is pure" but "the round wrote the same rows twice".
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
    WorkOrderStatus,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.service import DispatchRounds
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.workers.runtime.handlers import dispatch_handler, ensure_round_queued

pytestmark = pytest.mark.db

# 08:00 UTC is 15:00 in Bangkok: the afternoon shift, filed under the 3rd
# (ADR-045 §7). Chosen so the round has a roster to find at all - a test written
# against a moment no shift covers would pass by reporting no capacity.
NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
AFTERNOON = ShiftId("afternoon")
TODAY = date(2026, 3, 3)

BUFFERED = MachineId("MC-001")  # st-01, twenty units of buffer
BOTTLENECK = MachineId("MC-012")  # st-03, no buffer, multiplier 3.0
R2000 = MachineModel("R-2000iC")

ANA = UserId("tech-ana")
BEN = UserId("tech-ben")
ALL_SKILLS = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
TIMING = ClassTiming(heartbeat_seconds=10, dead_after_seconds=60)
PERIOD = timedelta(seconds=CONFIG.policy.dispatch.round_seconds)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician CASCADE"
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
    return DispatchRounds(clock, CONFIG)


@pytest.fixture
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


def _crew(conn: Connection[Any], *users: UserId, minutes: int = 480) -> None:
    for user in users:
        dispatch_repo.add_technician(conn, Technician(user=user, skills=ALL_SKILLS), now=NOW)
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=AFTERNOON, on_date=TODAY, technician=user, available_minutes=minutes
            ),
        )


def _ticket(
    orders: WorkOrders,
    conn: Connection[Any],
    *,
    machine_id: MachineId = BUFFERED,
    severity: Severity = Severity.MEDIUM,
) -> str:
    """A reported fault, so a ticket exists without layer 1 being involved
    (ADR-010: most work has no Finding behind it)."""
    return orders.from_report(
        conn,
        machine_id=machine_id,
        machine_model=R2000,
        severity=severity,
        reported_by=UserId("supervisor"),
        description="reported in a test",
    ).ref


def _row(conn: Connection[Any], ref: str) -> dict[str, Any]:
    order = work.get(conn, ref)
    assert order is not None
    return {
        "status": order.status,
        "assignees": tuple(one.user for one in order.assignees),
        "score": order.priority_score,
        "reason": order.priority_reason,
    }


class TestARoundPlacesWork:
    def test_a_queued_order_comes_out_assigned_with_its_reason(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)

        report = rounds.run(conn)

        assert report.placed == (ref,)
        row = _row(conn, ref)
        assert row["status"] is WorkOrderStatus.ASSIGNED
        assert row["assignees"] == (ANA,)
        # ADR-005: why this job is ranked where it is, written where somebody
        # standing at the machine can read it.
        assert row["reason"]

    def test_a_moment_no_shift_covers_places_nothing_and_says_which(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """04:00 UTC is 11:00 in Bangkok - inside the morning shift - so the
        moment that has no shift is one nobody is rostered for. Here it is the
        roster that is empty, and the round has to say that rather than treat it
        as a quiet shift and release everything to nobody (ADR-045 §3)."""
        _ticket(orders, conn)
        report = DispatchRounds(SimulatedClock(NOW), CONFIG).run(conn)

        assert report.placed == ()
        assert "nobody is rostered on the afternoon shift" in report.round.summary


class TestWorkNobodyMayTouch:
    def test_an_accepted_order_keeps_its_assignee_when_a_better_ticket_arrives(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """design.md 6.2, through the process. A queue that reorders itself while
        a technician walks to a machine is a queue they stop believing, and the
        ticket that would take theirs is exactly the one that scores highest."""
        _crew(conn, ANA)
        mine = _ticket(orders, conn, machine_id=BUFFERED, severity=Severity.LOW)
        rounds.run(conn)
        work.set_status(conn, mine, status=WorkOrderStatus.IN_PROGRESS)
        before = _row(conn, mine)

        # A critical fault on the unbuffered bottleneck: the highest-scoring
        # thing this queue can contain, and the one that would take Ana's place
        # if the round were free to re-rank what she has already accepted.
        urgent = _ticket(orders, conn, machine_id=BOTTLENECK, severity=Severity.CRITICAL)
        report = rounds.run(conn)

        assert _row(conn, mine) == before
        # The round still does its job: the new ticket is placed, on the same
        # technician, because she has the minutes for it. What it may not do is
        # move the one she is standing at a machine for (ADR-045 §4).
        assert report.placed == (urgent,)
        assert _row(conn, urgent)["assignees"] == (ANA,)


class TestARoundIsAllOrNothing:
    def test_a_round_that_never_commits_leaves_nothing_behind(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """ADR-017. The job dying after `dispatch()` and before the commit is an
        ordinary event - a worker killed, a connection dropped - and the queue
        has to look untouched afterwards."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        conn.commit()

        rounds.run(conn)
        conn.rollback()

        assert _row(conn, ref)["status"] is WorkOrderStatus.QUEUED
        assert _row(conn, ref)["assignees"] == ()

    def test_the_round_after_it_places_the_same_work(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """Retry, which is the other half of the same property: nothing was
        written, so nothing has to be undone before it can be done."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        conn.commit()

        rounds.run(conn)
        conn.rollback()
        report = rounds.run(conn)

        assert report.placed == (ref,)
        assert _row(conn, ref)["status"] is WorkOrderStatus.ASSIGNED

    def test_an_order_accepted_between_the_read_and_the_write_is_not_overwritten(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """The `status = 'queued'` in the UPDATE, exercised directly. A round
        replayed against a queue somebody has since accepted from writes nothing
        over the top of them, and says how many it let go."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        decided = rounds.run(conn)
        assert decided.placed == (ref,)

        # Somebody picked it up; the same decision arrives a second time.
        work.set_status(conn, ref, status=WorkOrderStatus.IN_PROGRESS)
        again = rounds.run(conn)

        assert again.placed == ()
        assert _row(conn, ref)["status"] is WorkOrderStatus.IN_PROGRESS


class TestTheSameWorldGivesTheSameWrites:
    def test_two_rounds_over_an_unchanged_world_write_the_same_rows(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """Invariant 10 through the process. Slice 6.1 proved the function is a
        function; this proves nothing between it and the table smuggles in a
        clock, a set iteration or a row order."""
        _crew(conn, ANA, BEN)
        refs = [
            _ticket(orders, conn, machine_id=BOTTLENECK, severity=Severity.HIGH),
            _ticket(orders, conn, machine_id=BUFFERED, severity=Severity.HIGH),
        ]
        conn.commit()

        first = DispatchRounds(SimulatedClock(NOW), CONFIG).run(conn)
        written = {ref: _row(conn, ref) for ref in refs}
        conn.rollback()

        second = DispatchRounds(SimulatedClock(NOW), CONFIG).run(conn)

        assert first.placed == second.placed
        assert {ref: _row(conn, ref) for ref in refs} == written
        assert first.round.summary == second.round.summary


class TestTheChain:
    def _appointments(self, conn: Connection[Any]) -> list[tuple[int, datetime]]:
        """Rounds waiting to run. Not `queue.pending`, which counts the running
        one - correctly, for the question it answers, and not this one."""
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, available_at FROM job WHERE kind = 'dispatch' AND status = 'queued' "
                "ORDER BY id"
            )
            return [(int(row[0]), row[1]) for row in cur.fetchall()]

    def test_a_round_books_the_next_one_in_its_own_transaction(
        self, conn: Connection[Any], rounds: DispatchRounds, clock: SimulatedClock
    ) -> None:
        """ADR-044 §1. The schedule is a row anybody can SELECT, and a round that
        failed leaves no appointment because the whole transaction rolls back."""
        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)
        handle = dispatch_handler(rounds, queue, clock, period=PERIOD)
        queue.enqueue(conn, kind=JobKind.DISPATCH)
        claimed = queue.claim(conn)
        assert claimed is not None

        handle(conn, claimed)

        booked = self._appointments(conn)
        assert len(booked) == 1
        assert booked[0][0] != claimed.id
        assert booked[0][1] == NOW + PERIOD

    def test_a_round_that_rolls_back_leaves_no_appointment(
        self, conn: Connection[Any], rounds: DispatchRounds, clock: SimulatedClock
    ) -> None:
        """ADR-017 through layer 3: the placements and the successor are the
        same rollback, which is what `ensure_round_queued` exists to recover
        from."""
        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)
        handle = dispatch_handler(rounds, queue, clock, period=PERIOD)
        queue.enqueue(conn, kind=JobKind.DISPATCH)
        claimed = queue.claim(conn)
        assert claimed is not None
        conn.commit()

        handle(conn, claimed)
        conn.rollback()

        assert self._appointments(conn) == []

    def test_the_chain_is_restarted_only_when_it_has_actually_stopped(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """ADR-040's `pending` primitive, doing here what it does for the second
        press of a button: an ordinary retry is a round that is still coming."""
        queue = JobQueue(job_class=JobClass.RUNTIME, worker="test", timing=TIMING, clock=clock)

        started = ensure_round_queued(conn, queue)
        assert started is not None
        assert ensure_round_queued(conn, queue) is None

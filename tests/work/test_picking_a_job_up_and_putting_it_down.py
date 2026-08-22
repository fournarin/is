"""The four transitions a technician's buttons stand for, against a real database.

The test that carries the slice is
`TestTwoUsersAndTwoShifts::test_actual_minutes_is_the_sum_of_the_segments`. A job
started at 15:00 and closed at 09:00 the next morning is not eighteen hours of
work, and until something wrote a segment, nothing in the system could tell the
difference - `actual_minutes` was zero on every order ever issued, so the loop
ADR-006 describes had no input at all (ADR-025).

The rest of the file is the refusals, which is where this code earns its place:
a handover with no note leaves the next shift starting from step one, a close
with no outcome loses the only false-alarm signal the system will ever get
(ADR-022), and blocked minutes larger than the job itself are a mis-tap that
would otherwise be quietly floored to zero and learned from.
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
    AssigneeRole,
    BlockedReason,
    MachineId,
    MachineModel,
    Severity,
    UserId,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.work.service import TransitionRefused

pytestmark = pytest.mark.db

# 08:00 UTC is 15:00 in Bangkok - the middle of the afternoon shift, which is
# where a job that has to cross into the night shift starts.
AFTERNOON = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MACHINE = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
MORNING_TECH = UserId("tech-1")
NIGHT_TECH = UserId("tech-2")
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(AFTERNOON)


@pytest.fixture
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[Any]]:
    with connect(database_url) as connection:
        connection.execute("TRUNCATE work_order CASCADE")
        connection.commit()
        yield connection


def _a_job(
    conn: Connection[Any],
    orders: WorkOrders,
    *,
    severity: Severity = Severity.HIGH,
    description: str = "grinding noise from the drive end",
) -> str:
    return orders.from_report(
        conn,
        machine_id=MACHINE,
        machine_model=R2000,
        severity=severity,
        reported_by=UserId("sup-1"),
        description=description,
    ).ref


class TestTwoUsersAndTwoShifts:
    def test_actual_minutes_is_the_sum_of_the_segments(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """The point of the slice, and the arithmetic is in this test.

        The afternoon works 15:00-15:40 (40 minutes) and hands over. The night
        shift picks it up at 23:00 and works until 23:25 (25 minutes). Close time
        minus start time is eight hours and twenty-five minutes; the truth is
        sixty-five minutes, and it is the second one the estimate learns from
        (ADR-025).
        """
        ref = _a_job(conn, orders)

        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=40))
        orders.hand_over(conn, ref, user=MORNING_TECH, note="cover off, breaker CP-3 locked out")

        clock.advance(timedelta(hours=7, minutes=20))
        orders.accept(conn, ref, user=NIGHT_TECH)
        orders.start(conn, ref, user=NIGHT_TECH)
        clock.advance(timedelta(minutes=25))
        closed = orders.close(conn, ref, user=NIGHT_TECH, outcome=WorkOutcome.FIXED)

        assert closed.actual_minutes == 65
        assert closed.actual_minutes != int((clock.now() - AFTERNOON).total_seconds() // 60), (
            "elapsed time is eight hours; the job is not (ADR-025)"
        )
        assert [segment.user for segment in closed.work_segments] == [MORNING_TECH, NIGHT_TECH]
        assert all(segment.ended_at is not None for segment in closed.work_segments)

    def test_the_second_user_opens_a_segment_rather_than_extending_the_first(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """Extending the first segment would credit the morning with the night's
        work and, worse, with the eight hours in between."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=40))
        orders.hand_over(conn, ref, user=MORNING_TECH, note="cover off")
        first_ended = work.get(conn, ref).work_segments[0].ended_at  # type: ignore[union-attr]

        clock.advance(timedelta(hours=7))
        orders.accept(conn, ref, user=NIGHT_TECH)
        after = orders.start(conn, ref, user=NIGHT_TECH)

        assert len(after.work_segments) == 2
        assert after.work_segments[0].ended_at == first_ended
        assert after.work_segments[1].started_at == clock.now()
        assert after.work_segments[1].ended_at is None

    def test_handing_over_frees_the_person_who_handed_it_over(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """ADR-056. Layer 3 subtracts an order's minutes from every assignee of a
        `handed_over` order, so a technician left on the list keeps losing
        capacity on shifts they are not going to spend on it."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)

        handed = orders.hand_over(conn, ref, user=MORNING_TECH, note="waiting on the seal kit")

        assert handed.status is WorkOrderStatus.HANDED_OVER
        assert handed.assignees == ()
        assert handed.handover_note == "waiting on the seal kit"
        # The evidence of who worked stays where it belongs.
        assert handed.work_segments[0].user == MORNING_TECH


class TestAcceptingAJob:
    def test_the_first_person_on_it_is_the_primary(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        ref = _a_job(conn, orders)

        accepted = orders.accept(conn, ref, user=MORNING_TECH)

        assert accepted.status is WorkOrderStatus.ASSIGNED
        assert accepted.assignees[0].user == MORNING_TECH
        assert accepted.assignees[0].role is AssigneeRole.PRIMARY

    def test_a_second_person_on_a_two_person_job_is_a_helper(
        self, conn: Connection[Any], orders: WorkOrders, database_url: str
    ) -> None:
        """ADR-025: skills are matched against the primary, and the helper's time
        is reserved as well."""
        ref = _a_job(conn, orders)
        conn.execute(
            "UPDATE work_order SET required_technicians = 2 WHERE work_order_ref = %s", (ref,)
        )

        orders.accept(conn, ref, user=MORNING_TECH)
        both = orders.accept(conn, ref, user=NIGHT_TECH)

        assert [one.role for one in both.assignees] == [AssigneeRole.PRIMARY, AssigneeRole.HELPER]

    def test_a_one_person_job_refuses_a_second_person(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)

        with pytest.raises(TransitionRefused):
            orders.accept(conn, ref, user=NIGHT_TECH)

    def test_accepting_twice_changes_nothing(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """A second press on a phone at a machine is not an error worth a red
        screen (ADR-056)."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)

        again = orders.accept(conn, ref, user=MORNING_TECH)

        assert len(again.assignees) == 1

    def test_a_closed_job_cannot_be_accepted(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.close(conn, ref, user=MORNING_TECH, outcome=WorkOutcome.FIXED)

        with pytest.raises(TransitionRefused):
            orders.accept(conn, ref, user=NIGHT_TECH)


class TestStartingAJob:
    def test_starting_requires_having_accepted_it(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        ref = _a_job(conn, orders)

        with pytest.raises(TransitionRefused):
            orders.start(conn, ref, user=MORNING_TECH)

    def test_starting_twice_does_not_open_a_second_segment(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """Two open segments for one person would count their time twice."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=5))

        with pytest.raises(TransitionRefused):
            orders.start(conn, ref, user=MORNING_TECH)

        assert len(work.get(conn, ref).work_segments) == 1  # type: ignore[union-attr]


class TestHandingOver:
    def test_a_handover_with_no_note_is_refused(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """ADR-025: without the note the afternoon technician finds an open order
        and no idea how far the morning got, so they start from step one."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)

        with pytest.raises(ValueError, match="note"):
            orders.hand_over(conn, ref, user=MORNING_TECH, note="   ")

        still_open = work.get(conn, ref)
        assert still_open is not None
        assert still_open.status is WorkOrderStatus.IN_PROGRESS
        assert still_open.work_segments[0].ended_at is None, "the refusal changed nothing"

    def test_a_helper_stepping_off_leaves_the_job_where_it_is(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """ADR-056 §3: the order is handed over when nobody is left on it, not
        when one of two people leaves."""
        ref = _a_job(conn, orders)
        conn.execute(
            "UPDATE work_order SET required_technicians = 2 WHERE work_order_ref = %s", (ref,)
        )
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.accept(conn, ref, user=NIGHT_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=NIGHT_TECH)
        clock.advance(timedelta(minutes=20))

        after = orders.hand_over(conn, ref, user=NIGHT_TECH, note="called to the line")

        assert after.status is WorkOrderStatus.IN_PROGRESS
        assert [one.user for one in after.assignees] == [MORNING_TECH]
        assert after.handover_note == "called to the line"


class TestClosingAJob:
    def test_closing_closes_every_open_segment(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """An open segment contributes nothing to `actual_minutes`, so one left
        open at close discards the time somebody worked (ADR-056 §5)."""
        ref = _a_job(conn, orders)
        conn.execute(
            "UPDATE work_order SET required_technicians = 2 WHERE work_order_ref = %s", (ref,)
        )
        for who in (MORNING_TECH, NIGHT_TECH):
            orders.accept(conn, ref, user=who)
            orders.start(conn, ref, user=who)
        clock.advance(timedelta(minutes=30))

        closed = orders.close(conn, ref, user=MORNING_TECH, outcome=WorkOutcome.FIXED)

        assert all(segment.ended_at == clock.now() for segment in closed.work_segments)
        assert closed.actual_minutes == 60, "two people, thirty minutes each"

    def test_no_problem_found_is_preserved(self, conn: Connection[Any], orders: WorkOrders) -> None:
        """The only false-alarm signal the system will ever receive. Loop 2 -
        tuning rule thresholds - does not exist without it (ADR-022)."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)

        closed = orders.close(conn, ref, user=MORNING_TECH, outcome=WorkOutcome.NO_PROBLEM_FOUND)

        assert closed.status is WorkOrderStatus.CLOSED
        assert closed.outcome is WorkOutcome.NO_PROBLEM_FOUND
        assert closed.actual_minutes == 0, "nobody started it, and that is the truth"

    def test_blocked_minutes_cannot_exceed_the_job(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """`repair_minutes` floors at zero, which keeps the arithmetic safe and
        hides the input that was wrong (ADR-056 §6)."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=40))

        with pytest.raises(ValueError, match="blocked"):
            orders.close(
                conn,
                ref,
                user=MORNING_TECH,
                outcome=WorkOutcome.FIXED,
                blocked_minutes=90,
                blocked_reason=(BlockedReason.WAITING_PARTS,),
            )

        still_open = work.get(conn, ref)
        assert still_open is not None
        assert still_open.status is WorkOrderStatus.IN_PROGRESS
        # The refusal is decided before anything is written: an HTTPException
        # commits the request's transaction (api/deps.py), so a check made after
        # closing the segments would leave the job half ended.
        assert still_open.work_segments[0].ended_at is None

    def test_waiting_for_a_part_is_not_repair_time(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """What Loop 1 may learn from is the difference, not the elapsed time:
        left in, waiting inflates the estimate every cycle until `load_ratio`
        reads every shift as full (ADR-006, ADR-025)."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=50))

        closed = orders.close(
            conn,
            ref,
            user=MORNING_TECH,
            outcome=WorkOutcome.TEMPORARY_FIX,
            blocked_minutes=20,
            blocked_reason=(BlockedReason.WAITING_PARTS, BlockedReason.WAITING_LINE_STOP),
            technician_feedback="clamped the hose, seal kit is on order",
        )

        assert closed.actual_minutes == 50
        assert closed.blocked_minutes == 20
        assert closed.repair_minutes == 30
        assert set(closed.blocked_reason) == {
            BlockedReason.WAITING_PARTS,
            BlockedReason.WAITING_LINE_STOP,
        }
        assert closed.technician_feedback == "clamped the hose, seal kit is on order"

    def test_closing_a_job_that_is_not_yours_is_refused(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)

        with pytest.raises(TransitionRefused):
            orders.close(conn, ref, user=NIGHT_TECH, outcome=WorkOutcome.FIXED)

    def test_closing_twice_is_refused(self, conn: Connection[Any], orders: WorkOrders) -> None:
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.close(conn, ref, user=MORNING_TECH, outcome=WorkOutcome.FIXED)

        with pytest.raises(TransitionRefused):
            orders.close(conn, ref, user=MORNING_TECH, outcome=WorkOutcome.NOT_FIXED)


class TestTheOrderHasToExist:
    def test_a_transition_on_a_missing_order_says_so(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        with pytest.raises(LookupError):
            orders.accept(conn, "WO-999999", user=MORNING_TECH)


class TestTheSnapshotStaysFrozen:
    def test_working_a_job_never_touches_what_it_instructed(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """Invariant 2 through the transitions rather than through raw SQL: the
        trigger in migration 0006 would abort the transaction, so a transition
        that touched the snapshot would fail here rather than silently."""
        ref = _a_job(conn, orders)
        orders.accept(conn, ref, user=MORNING_TECH)
        orders.start(conn, ref, user=MORNING_TECH)
        clock.advance(timedelta(minutes=10))
        orders.hand_over(conn, ref, user=MORNING_TECH, note="paused")
        orders.accept(conn, ref, user=NIGHT_TECH)
        closed = orders.close(conn, ref, user=NIGHT_TECH, outcome=WorkOutcome.FIXED)

        assert closed.playbook_snapshot == ()

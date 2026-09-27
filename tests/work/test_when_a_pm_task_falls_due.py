"""Which PM tasks fall due, and what closing one means. No database (ADR-083).

The arithmetic is separated from the scan for invariant 10's reason: somebody
has to be able to check "this task was due and that one was not" against dates
written out by hand, and `now` is an argument because nothing here may read a
clock (ADR-028).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pdm.contracts import (
    MachineId,
    PMTask,
    PMTaskRef,
    Severity,
    SymptomCode,
    WorkOutcome,
)
from pdm.work import domain

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
BELT = timedelta(hours=8000)
MOTOR = MachineId("MC-001")
FALLBACK = {"R-2000iC": {Severity.LOW: 30}}


def _task(ref: str, *, due_at: datetime, last_done_at: datetime | None = None) -> PMTask:
    return PMTask(
        pm_task_ref=PMTaskRef(ref),
        machine_id=MOTOR,
        symptom_code=SymptomCode("PM-toothed-belt"),
        interval=BELT,
        due_at=due_at,
        last_done_at=last_done_at,
    )


class TestWhichTasksAreDue:
    def test_a_task_due_now_is_due(self) -> None:
        assert domain.due_pm_tasks([_task("pm-1", due_at=NOW)], live_refs=(), now=NOW)

    def test_a_task_due_a_minute_from_now_is_not(self) -> None:
        task = _task("pm-1", due_at=NOW + timedelta(minutes=1))

        assert domain.due_pm_tasks([task], live_refs=(), now=NOW) == ()

    def test_a_task_with_work_in_flight_is_skipped_however_overdue(self) -> None:
        """Skipped rather than stacked: two tickets for one job would put two
        technicians on it and price the shift for both (ADR-083 section 3)."""
        task = _task("pm-1", due_at=NOW - timedelta(days=400))

        assert domain.due_pm_tasks([task], live_refs=[PMTaskRef("pm-1")], now=NOW) == ()

    def test_one_task_in_flight_does_not_hold_back_another(self) -> None:
        held = _task("pm-1", due_at=NOW)
        free = _task("pm-2", due_at=NOW)

        due = domain.due_pm_tasks([held, free], live_refs=[PMTaskRef("pm-1")], now=NOW)

        assert [task.pm_task_ref for task in due] == [PMTaskRef("pm-2")]


class TestWhatClosingOneMeans:
    def test_only_fixed_means_the_maintenance_happened(self) -> None:
        assert domain.pm_task_was_done(WorkOutcome.FIXED) is True

    @pytest.mark.parametrize(
        "outcome",
        [WorkOutcome.NOT_FIXED, WorkOutcome.TEMPORARY_FIX, WorkOutcome.NO_PROBLEM_FOUND],
    )
    def test_nothing_else_does(self, outcome: WorkOutcome) -> None:
        """`no_problem_found` on a PM task says the technician found nothing to
        do, not that the procedure was carried out."""
        assert domain.pm_task_was_done(outcome) is False


class TestWhatTheTicketSays:
    def test_a_task_with_a_history_names_the_date_and_the_interval(self) -> None:
        task = _task("pm-1", due_at=NOW, last_done_at=NOW - BELT)

        order = domain.from_pm_task(
            task, playbook=None, machine_model="R-2000iC", fallback_minutes=FALLBACK
        )

        assert "ทำครั้งล่าสุด 4 เม.ย. 2025" in order.reason
        assert "8,000 ชั่วโมงทำงาน" in order.reason

    def test_a_task_with_none_says_that_rather_than_implying_a_date(self) -> None:
        """The honest half of "due now". Nobody knows when this was last done,
        and the person holding the ticket is the one who might (ADR-083 §4)."""
        order = domain.from_pm_task(
            _task("pm-1", due_at=NOW),
            playbook=None,
            machine_model="R-2000iC",
            fallback_minutes=FALLBACK,
        )

        assert "ยังไม่มีบันทึกว่าเคยทำ" in order.reason
        assert "ครบกำหนดตั้งแต่ลงทะเบียน" in order.reason

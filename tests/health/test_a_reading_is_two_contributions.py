"""A health reading is two halves and no third number (ADR-072, ADR-076).

The specification here is ADR-072 section 2 rather than the code: the two
contributions are reported as two, the figures under each are the ones a
supervisor checks the sentence against, and the figure that cannot be computed
is named instead of guessed.

Everything is written out by hand. `pdm.health.domain` may not open a connection
(invariant 10), so nothing in this file needs one either.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    FindingStatus,
    MachineId,
    PMTask,
    PMTaskRef,
    RuleId,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.health import (
    AGE_AGAINST_ITS_CLASS_IS_ABSENT,
    ClosedRepair,
    CurrentContribution,
    HistoryContribution,
    MachineHealth,
    assess,
)

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
YEAR_AGO = NOW - timedelta(days=365)
MC = MachineId("MC-012")
OTHER = MachineId("MC-004")


def repair(
    *,
    machine: MachineId = MC,
    days_ago: float,
    outcome: WorkOutcome = WorkOutcome.FIXED,
    origin: WorkOrderOrigin = WorkOrderOrigin.CONDITION,
    ref: str = "wo-1",
) -> ClosedRepair:
    return ClosedRepair(
        work_order_ref=WorkOrderRef(ref),
        machine_id=machine,
        closed_at=NOW - timedelta(days=days_ago),
        origin=origin,
        outcome=outcome,
    )


def finding(
    *,
    machine: MachineId = MC,
    severity: Severity = Severity.HIGH,
    status: FindingStatus = FindingStatus.OPEN,
    kind: FindingKind = FindingKind.DETECTED,
    eta_hours: float | None = None,
) -> Finding:
    return Finding(
        machine_id=machine,
        component=ComponentLabel("axis-2"),
        symptom_code=SymptomCode("SYM-014"),
        severity=severity,
        rule_id=RuleId("rule-1"),
        detected_at=NOW - timedelta(hours=2),
        evidence={"value": 81.0},
        kind=kind,
        eta=None if eta_hours is None else NOW + timedelta(hours=eta_hours),
        eta_confidence=None if eta_hours is None else timedelta(hours=2),
        status=status,
    )


class TestThereIsNoThirdNumber:
    def test_a_reading_carries_the_two_contributions_and_nothing_else(self) -> None:
        """The change this whole record exists to refuse is a `score` field."""
        assert set(MachineHealth.model_fields) == {"machine_id", "history", "now"}

    def test_neither_contribution_carries_a_figure_derived_from_the_other(self) -> None:
        """No field on either half may be named for the blend (ADR-072 §2).

        A weak check on purpose: what it can catch is somebody adding
        `overall_score` to one of the halves because one screen wanted a single
        column, which is exactly how the refusal would be lost.
        """
        blended = {"score", "index", "health_score", "overall", "percent", "rating"}
        for model in (HistoryContribution, CurrentContribution):
            assert not blended & set(model.model_fields), model


class TestWhatTheHistoryCounts:
    def test_a_machine_asked_about_with_no_records_still_gets_a_row(self) -> None:
        readings = assess((MC, OTHER), repairs=(repair(days_ago=10),), now=NOW)
        assert [r.machine_id for r in readings] == [MC, OTHER]
        empty = readings[1].history
        assert empty.failures == 0
        assert empty.closed_orders == 0
        assert empty.days_since_last_failure is None

    def test_scheduled_work_is_not_a_failure_however_it_closed(self) -> None:
        readings = assess(
            (MC,),
            repairs=(
                repair(days_ago=5, origin=WorkOrderOrigin.SCHEDULED, ref="pm-1"),
                repair(days_ago=9, origin=WorkOrderOrigin.SCHEDULED, ref="pm-2"),
            ),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        history = readings[0].history
        assert history.closed_orders == 2
        assert history.pm_completed == 2
        assert history.failures == 0

    def test_a_fault_a_person_reported_is_a_failure(self) -> None:
        """Manual work that found something is a failure the rules missed."""
        readings = assess(
            (MC,),
            repairs=(repair(days_ago=5, origin=WorkOrderOrigin.MANUAL),),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        assert readings[0].history.failures == 1

    def test_an_order_that_found_nothing_is_a_false_alarm_and_not_a_failure(self) -> None:
        readings = assess(
            (MC,),
            repairs=(repair(days_ago=5, outcome=WorkOutcome.NO_PROBLEM_FOUND),),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        history = readings[0].history
        assert history.false_alarms == 1
        assert history.failures == 0
        assert "ADR-073" in history.reason

    def test_the_rate_is_over_one_span_shared_by_every_machine(self) -> None:
        """A machine whose first record is late did not fail earlier (ADR-076 §4)."""
        readings = assess(
            (MC, OTHER),
            repairs=(
                repair(machine=MC, days_ago=300, ref="wo-a"),
                repair(machine=OTHER, days_ago=10, ref="wo-b"),
            ),
            now=NOW,
        )
        first, second = readings
        assert first.history.observed_from == second.history.observed_from
        assert first.history.failures_per_100_days == second.history.failures_per_100_days

    def test_no_span_means_no_rate_rather_than_a_rate_of_zero(self) -> None:
        readings = assess((MC,), now=NOW)
        history = readings[0].history
        assert history.failures_per_100_days is None
        assert history.observed_from is None
        assert "No closed work orders" in history.reason

    def test_the_reason_names_the_counts_it_came_from(self) -> None:
        readings = assess(
            (MC,),
            repairs=(repair(days_ago=30), repair(days_ago=10, ref="wo-2")),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        reason = readings[0].history.reason
        assert "failed 2 times" in reason
        assert "365 observed days" in reason
        assert "10 days ago" in reason

    def test_a_window_that_starts_after_it_is_read_at_is_refused(self) -> None:
        with pytest.raises(ValueError, match="cannot start after"):
            assess((MC,), now=NOW, observed_from=NOW + timedelta(days=1))


class TestWhatCannotBeComputedSaysSo:
    def test_every_reading_names_the_figure_adr_072_asked_for_and_nothing_holds(self) -> None:
        readings = assess((MC,), now=NOW)
        assert AGE_AGAINST_ITS_CLASS_IS_ABSENT in readings[0].history.absent

    def test_the_supervisor_reads_the_absence_as_well_as_the_figures(self) -> None:
        """Principle 5 is only kept if it reaches the sentence somebody reads."""
        readings = assess((MC,), repairs=(repair(days_ago=3),), now=NOW)
        assert "machine register" in readings[0].history.reason


class TestPMIsCountedAndNotRankedOn:
    def test_an_overdue_task_is_counted_with_how_late_the_worst_of_them_is(self) -> None:
        tasks = (
            PMTask(
                pm_task_ref=PMTaskRef("pm-1"),
                machine_id=MC,
                symptom_code=SymptomCode("PM-ROUTINE"),
                interval=timedelta(days=30),
                due_at=NOW - timedelta(days=40),
            ),
            PMTask(
                pm_task_ref=PMTaskRef("pm-2"),
                machine_id=MC,
                symptom_code=SymptomCode("PM-GREASE"),
                interval=timedelta(days=90),
                due_at=NOW + timedelta(days=5),
            ),
        )
        history = assess((MC,), pm_tasks=tasks, now=NOW)[0].history
        assert history.pm_overdue == 1
        assert history.pm_overdue_days == pytest.approx(40.0)
        assert "work to schedule" in history.reason

    def test_another_machines_task_is_not_this_machines_backlog(self) -> None:
        tasks = (
            PMTask(
                pm_task_ref=PMTaskRef("pm-1"),
                machine_id=OTHER,
                symptom_code=SymptomCode("PM-ROUTINE"),
                interval=timedelta(days=30),
                due_at=NOW - timedelta(days=40),
            ),
        )
        assert assess((MC,), pm_tasks=tasks, now=NOW)[0].history.pm_overdue == 0


class TestWhatTheMachineIsSayingNow:
    def test_nothing_open_is_an_answer_rather_than_an_empty_row(self) -> None:
        current = assess((MC,), now=NOW)[0].now
        assert current.open_findings == 0
        assert current.highest_severity is None
        assert "Nothing is open" in current.reason

    def test_acknowledged_findings_still_stand(self) -> None:
        """Somebody having seen it does not make the machine well."""
        current = assess(
            (MC,),
            findings=(finding(status=FindingStatus.ACKNOWLEDGED),),
            now=NOW,
        )[0].now
        assert current.open_findings == 1
        assert current.acknowledged == 1

    @pytest.mark.parametrize(
        "status",
        [FindingStatus.RESOLVED, FindingStatus.EXPIRED, FindingStatus.SUPERSEDED],
    )
    def test_a_finding_that_has_finished_is_not_what_the_machine_is_saying_now(
        self, status: FindingStatus
    ) -> None:
        current = assess((MC,), findings=(finding(status=status),), now=NOW)[0].now
        assert current.open_findings == 0

    def test_the_worst_severity_standing_is_the_one_reported(self) -> None:
        current = assess(
            (MC,),
            findings=(
                finding(severity=Severity.LOW),
                finding(severity=Severity.CRITICAL),
                finding(severity=Severity.MEDIUM),
            ),
            now=NOW,
        )[0].now
        assert current.highest_severity is Severity.CRITICAL
        assert current.open_findings == 3

    def test_the_soonest_forecast_crossing_is_repeated_and_not_recomputed(self) -> None:
        current = assess(
            (MC,),
            findings=(
                finding(kind=FindingKind.PREDICTED, eta_hours=9),
                finding(kind=FindingKind.PREDICTED, eta_hours=4),
                finding(),
            ),
            now=NOW,
        )[0].now
        assert current.predicted == 2
        assert current.detected == 1
        assert current.soonest_eta == NOW + timedelta(hours=4)
        assert current.hours_to_soonest_eta == pytest.approx(4.0)
        assert "ADR-020" in current.reason

    def test_another_machines_finding_is_not_this_machines_news(self) -> None:
        current = assess((MC,), findings=(finding(machine=OTHER),), now=NOW)[0].now
        assert current.open_findings == 0


class TestOnlyClosedOrdersAreHistory:
    def _order(self, status: WorkOrderStatus, outcome: WorkOutcome | None) -> WorkOrder:
        return WorkOrder(
            origin=WorkOrderOrigin.MANUAL,
            machine_id=MC,
            severity=Severity.HIGH,
            estimated_minutes=45,
            estimate_is_fallback=True,
            reason="Reported by an operator.",
            status=status,
            work_segments=(
                WorkSegment(
                    user=UserId("tech-1"),
                    started_at=NOW - timedelta(hours=2),
                    ended_at=NOW - timedelta(hours=1),
                ),
            ),
            outcome=outcome,
        )

    def test_a_job_still_running_is_not_a_failure_the_machine_has_finished_having(
        self,
    ) -> None:
        order = self._order(WorkOrderStatus.IN_PROGRESS, None)
        with pytest.raises(ValueError, match="only a closed order is history"):
            ClosedRepair.from_order(WorkOrderRef("wo-9"), order, closed_at=NOW)

    def test_a_closed_order_reduces_to_the_four_facts_history_reads(self) -> None:
        order = self._order(WorkOrderStatus.CLOSED, WorkOutcome.FIXED)
        reduced = ClosedRepair.from_order(WorkOrderRef("wo-9"), order, closed_at=NOW)
        assert reduced.machine_id == MC
        assert reduced.origin is WorkOrderOrigin.MANUAL
        assert reduced.outcome is WorkOutcome.FIXED
        assert reduced.is_failure
        assert not reduced.is_false_alarm

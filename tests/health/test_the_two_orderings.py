"""Two orderings, and what each of them refuses to be moved by (ADR-076 §2-3).

`by_history` and `by_now` exist instead of one ranking because one ranking is the
blended number ADR-072 section 2 refuses, arriving as a sort key. What is tested
here is mostly what does *not* move a machine: overdue PM and a run of false
alarms are both on the reading, both displayed, and neither is allowed to lift a
machine past one that has actually been failing.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingStatus,
    MachineId,
    PMTask,
    PMTaskRef,
    RuleId,
    Severity,
    SymptomCode,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOutcome,
)
from pdm.health import ClosedRepair, MachineHealth, assess, by_history, by_now

NOW = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
YEAR_AGO = NOW - timedelta(days=365)

MC_001 = MachineId("MC-001")
MC_004 = MachineId("MC-004")
MC_012 = MachineId("MC-012")
MC_018 = MachineId("MC-018")


def failures(machine: MachineId, *days_ago: float) -> tuple[ClosedRepair, ...]:
    return tuple(
        ClosedRepair(
            work_order_ref=WorkOrderRef(f"wo-{machine}-{index}"),
            machine_id=machine,
            closed_at=NOW - timedelta(days=day),
            origin=WorkOrderOrigin.CONDITION,
            outcome=WorkOutcome.FIXED,
        )
        for index, day in enumerate(days_ago)
    )


def alarms(machine: MachineId, count: int) -> tuple[ClosedRepair, ...]:
    return tuple(
        ClosedRepair(
            work_order_ref=WorkOrderRef(f"fa-{machine}-{index}"),
            machine_id=machine,
            closed_at=NOW - timedelta(days=index + 1),
            origin=WorkOrderOrigin.CONDITION,
            outcome=WorkOutcome.NO_PROBLEM_FOUND,
        )
        for index in range(count)
    )


def open_finding(machine: MachineId, severity: Severity) -> Finding:
    return Finding(
        machine_id=machine,
        component=ComponentLabel("axis-2"),
        symptom_code=SymptomCode("SYM-014"),
        severity=severity,
        rule_id=RuleId("rule-1"),
        detected_at=NOW - timedelta(hours=2),
        evidence={"value": 81.0},
        status=FindingStatus.OPEN,
    )


def overdue_pm(machine: MachineId, days: float) -> PMTask:
    return PMTask(
        pm_task_ref=PMTaskRef(f"pm-{machine}"),
        machine_id=machine,
        symptom_code=SymptomCode("PM-ROUTINE"),
        interval=timedelta(days=30),
        due_at=NOW - timedelta(days=days),
    )


def order_of(readings: tuple[MachineHealth, ...]) -> list[str]:
    return [str(reading.machine_id) for reading in readings]


class TestByHistory:
    def test_the_machine_that_failed_most_often_comes_first(self) -> None:
        readings = assess(
            (MC_001, MC_012),
            repairs=failures(MC_001, 300) + failures(MC_012, 10, 40, 80),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        assert order_of(by_history(readings)) == ["MC-012", "MC-001"]

    def test_an_equal_rate_is_broken_by_the_more_recent_failure(self) -> None:
        readings = assess(
            (MC_001, MC_012),
            repairs=failures(MC_001, 200) + failures(MC_012, 3),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        assert order_of(by_history(readings)) == ["MC-012", "MC-001"]

    def test_a_machine_nothing_is_known_about_sorts_below_one_that_has_not_failed(
        self,
    ) -> None:
        """Two different claims, and a ranking that conflated them would say the
        quieter one out loud on evidence it does not have."""
        known = assess((MC_001,), repairs=failures(MC_001, 300), now=NOW)[0]
        unknown = assess((MC_018,), now=NOW)[0]
        assert unknown.history.failures_per_100_days is None
        assert order_of(by_history((unknown, known))) == ["MC-001", "MC-018"]

    def test_overdue_pm_does_not_lift_a_machine_past_one_that_is_failing(self) -> None:
        readings = assess(
            (MC_001, MC_012),
            repairs=failures(MC_012, 10, 40),
            pm_tasks=(overdue_pm(MC_001, days=120),),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        ranked = by_history(readings)
        assert order_of(ranked) == ["MC-012", "MC-001"]
        # And it is still visible on the machine it belongs to.
        assert ranked[1].history.pm_overdue == 1

    def test_a_run_of_false_alarms_does_not_lift_a_machine_either(self) -> None:
        readings = assess(
            (MC_004, MC_012),
            repairs=alarms(MC_004, 6) + failures(MC_012, 30),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        ranked = by_history(readings)
        assert order_of(ranked) == ["MC-012", "MC-004"]
        assert ranked[1].history.false_alarms == 6

    def test_the_order_is_total_so_a_measurement_of_it_reproduces(self) -> None:
        readings = assess((MC_018, MC_001, MC_004), now=NOW)
        assert order_of(by_history(readings)) == ["MC-001", "MC-004", "MC-018"]


class TestByNow:
    def test_the_worst_thing_standing_open_comes_first(self) -> None:
        readings = assess(
            (MC_001, MC_012),
            findings=(
                open_finding(MC_001, Severity.HIGH),
                open_finding(MC_001, Severity.HIGH),
                open_finding(MC_012, Severity.CRITICAL),
            ),
            now=NOW,
        )
        assert order_of(by_now(readings)) == ["MC-012", "MC-001"]

    def test_equal_severity_is_broken_by_how_many_are_open(self) -> None:
        readings = assess(
            (MC_001, MC_012),
            findings=(
                open_finding(MC_001, Severity.HIGH),
                open_finding(MC_012, Severity.HIGH),
                open_finding(MC_012, Severity.HIGH),
            ),
            now=NOW,
        )
        assert order_of(by_now(readings)) == ["MC-012", "MC-001"]

    def test_a_machine_with_nothing_open_sorts_last_however_bad_its_history(self) -> None:
        readings = assess(
            (MC_012, MC_001),
            repairs=failures(MC_012, 1, 2, 3, 4),
            findings=(open_finding(MC_001, Severity.LOW),),
            now=NOW,
            observed_from=YEAR_AGO,
        )
        assert order_of(by_now(readings)) == ["MC-001", "MC-012"]
        # The history half still says what it said. That is the point of two.
        assert order_of(by_history(readings)) == ["MC-012", "MC-001"]

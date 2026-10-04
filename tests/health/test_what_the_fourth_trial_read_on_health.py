"""The fourth trial's fourth finding, on the overview's machine health.

Two things were wrong on one panel. A predicted job closed before the machine
crossed its threshold put MC-001 at the top of "fails most" with one failure,
when nothing had failed. And two minutes of closed orders were drawn as a
ranking, with "0.0 วัน" in every row, although ADR-116 says no rate exists under
a week - a list headed "fails most" was ordered by nothing.

Written out by hand: `pdm.health.domain` may not open a connection.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pdm.contracts import (
    FindingKind,
    FindingRef,
    MachineId,
    Severity,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.health import (
    MINIMUM_OBSERVED_DAYS,
    ClosedRepair,
    assess,
    by_history,
    history_too_short,
)

NOW = datetime(2026, 10, 4, 1, 47, tzinfo=UTC)
MC_001 = MachineId("MC-001")
MC_004 = MachineId("MC-004")


def repair(
    machine: MachineId,
    *,
    days_ago: float,
    kind: FindingKind | None,
    came_true: bool = False,
    outcome: WorkOutcome = WorkOutcome.FIXED,
    index: int = 0,
) -> ClosedRepair:
    return ClosedRepair(
        work_order_ref=WorkOrderRef(f"wo-{machine}-{index}"),
        machine_id=machine,
        closed_at=NOW - timedelta(days=days_ago),
        origin=WorkOrderOrigin.CONDITION,
        outcome=outcome,
        finding_kind=kind,
        came_true=came_true,
    )


class TestAPredictionActedOnIsNotAFailure:
    def test_a_prediction_closed_before_its_detection_is_prevented(self) -> None:
        prevented = repair(MC_001, days_ago=1, kind=FindingKind.PREDICTED)
        assert prevented.is_prevented
        assert not prevented.is_failure
        assert not prevented.is_false_alarm

    def test_a_prediction_its_detection_overtook_did_fail(self) -> None:
        came_true = repair(MC_001, days_ago=1, kind=FindingKind.PREDICTED, came_true=True)
        assert came_true.is_failure
        assert not came_true.is_prevented

    def test_a_detection_is_still_a_failure(self) -> None:
        assert repair(MC_001, days_ago=1, kind=FindingKind.DETECTED).is_failure

    def test_a_prediction_that_found_nothing_is_still_a_false_alarm(self) -> None:
        nothing = repair(
            MC_001, days_ago=1, kind=FindingKind.PREDICTED, outcome=WorkOutcome.NO_PROBLEM_FOUND
        )
        assert nothing.is_false_alarm
        assert not nothing.is_prevented

    def test_the_run_4_machine_does_not_rank_above_one_that_failed(self) -> None:
        readings = assess(
            [MC_001, MC_004],
            repairs=[
                repair(MC_001, days_ago=3, kind=FindingKind.PREDICTED, index=1),
                repair(MC_001, days_ago=2, kind=FindingKind.PREDICTED, index=2),
                repair(MC_004, days_ago=5, kind=FindingKind.DETECTED),
            ],
            now=NOW,
            observed_from=NOW - timedelta(days=30),
        )
        first, second = by_history(readings)
        assert first.machine_id == MC_004
        assert second.history.failures == 0
        assert second.history.prevented == 2
        assert "ซ่อมก่อนเสียตามที่คาดการณ์ไว้ 2 ครั้ง ไม่นับเป็นการเสีย" in second.history.reason

    def test_from_order_carries_the_kind_and_whether_it_came_true(self) -> None:
        order = WorkOrder(
            origin=WorkOrderOrigin.CONDITION,
            finding_ref=FindingRef("f-1"),
            machine_id=MC_001,
            severity=Severity.MEDIUM,
            finding_kind=FindingKind.PREDICTED,
            eta=NOW + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
            estimated_minutes=30,
            reason="Trend towards the threshold.",
            status=WorkOrderStatus.CLOSED,
            work_segments=(
                WorkSegment(
                    user=UserId("tech-1"),
                    started_at=NOW - timedelta(minutes=10),
                    ended_at=NOW - timedelta(minutes=2),
                ),
            ),
            outcome=WorkOutcome.FIXED,
        )
        prevented = ClosedRepair.from_order(WorkOrderRef("wo-1"), order, closed_at=NOW)
        assert prevented.finding_kind is FindingKind.PREDICTED
        assert prevented.is_prevented

        failed = ClosedRepair.from_order(WorkOrderRef("wo-1"), order, closed_at=NOW, came_true=True)
        assert failed.is_failure


class TestUnderAWeekThereIsNoRanking:
    def test_two_minutes_is_one_sentence_naming_what_is_needed(self) -> None:
        sentence = history_too_short(NOW - timedelta(minutes=2), 2 / 1440)
        assert sentence is not None
        assert f"อย่างน้อย {MINIMUM_OBSERVED_DAYS:.0f} วัน" in sentence
        assert "ไม่ถึง 1 วัน" in sentence
        assert "0.0" not in sentence and "0 วัน" not in sentence.replace("ไม่ถึง 1 วัน", "")

    def test_a_few_days_says_how_many(self) -> None:
        sentence = history_too_short(NOW - timedelta(days=3), 3.0)
        assert sentence is not None
        assert "แค่ 3 วัน" in sentence

    def test_nothing_closed_says_so(self) -> None:
        assert history_too_short(None, 0.0) is not None

    def test_a_week_ranks(self) -> None:
        assert history_too_short(NOW - timedelta(days=7), MINIMUM_OBSERVED_DAYS) is None

    def test_a_machine_reason_never_says_zero_point_zero_days(self) -> None:
        (reading,) = assess(
            [MC_001],
            repairs=[repair(MC_001, days_ago=0.001, kind=FindingKind.DETECTED)],
            now=NOW,
            observed_from=NOW - timedelta(minutes=2),
        )
        assert "0.0 วัน" not in reading.history.reason
        assert "ไม่ถึง 1 วัน" in reading.history.reason

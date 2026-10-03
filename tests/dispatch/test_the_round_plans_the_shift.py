"""ADR-128: the deployed round plans with CP-SAT, and a predicted job's reason
says what waiting risks rather than what is already happening."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pdm.contracts import (
    FindingKind,
    FindingRef,
    MachineId,
    Severity,
    SkillId,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.dispatch import Queued, dispatch, schedule
from pdm.dispatch.service import planner
from pdm.platform.config import Config, load_config

CONFIG = load_config(Path("config"))
NOW = datetime(2026, 3, 3, 3, 0, tzinfo=UTC)
MECHANICAL = SkillId("robot_mechanical")
ANA = UserId("ana")


def _with_planner(name: str) -> Config:
    dispatch_policy = CONFIG.policy.dispatch.model_copy(update={"planner": name})
    return Config(
        CONFIG.plant, CONFIG.rules, CONFIG.policy.model_copy(update={"dispatch": dispatch_policy})
    )


def _predicted() -> Queued:
    order = WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=FindingRef("F-1"),
        machine_id=MachineId("MC-012"),
        severity=Severity.HIGH,
        finding_kind=FindingKind.PREDICTED,
        eta=NOW + timedelta(hours=3),
        eta_confidence=timedelta(hours=1),
        estimated_minutes=60,
        required_skill=MECHANICAL,
        required_technicians=1,
        reason="because a test said so",
        status=WorkOrderStatus.QUEUED,
    )
    return Queued(ref="WO-p", order=order, created_at=NOW)


class TestWhichPlannerRuns:
    def test_the_shipped_configuration_plans_with_cp_sat(self) -> None:
        assert CONFIG.policy.dispatch.planner == "cp_sat"
        assert planner(CONFIG) is schedule

    def test_greedy_is_still_one_setting_away(self) -> None:
        assert planner(_with_planner("greedy")) is dispatch


class TestAPredictedJobsReason:
    def test_it_does_not_say_the_line_is_losing_production_already(self) -> None:
        """The machine is running until the forecast comes true."""
        result = dispatch(
            [_predicted()],
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            assignments=[(ANA, 300)],
            config=CONFIG,
            now=NOW,
        )
        (placed,) = result.placed
        assert "ถ้างานนี้รอ" not in placed.priority_reason
        assert "ถ้าเครื่องหยุดตามที่พยากรณ์" in placed.priority_reason


class TestThePlanSpeaksThai:
    """ADR-093 for the planner too. Until ADR-128 nothing showed 3D's text to a
    person, and it said "the shift plan starts this now; ... (optimal)"."""

    def test_no_english_reaches_the_shift_lead(self) -> None:
        import re

        second = _predicted()
        other = Queued(
            ref="WO-q",
            order=second.order.model_copy(update={"machine_id": MachineId("MC-001")}),
            created_at=NOW,
        )
        result = schedule(
            [_predicted(), other],
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            assignments=[(ANA, 300)],
            config=CONFIG,
            now=NOW,
        )
        said = [result.summary, *(one.priority_reason for one in result.placed)]
        assert len(result.placed) == 2
        for sentence in said:
            assert not re.search(r"[a-z]{3,}", sentence), sentence
            assert "นาที" not in sentence.split(" · ")[0], "no minute in the plan's clause"

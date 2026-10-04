"""ADR-131: a predicted job's waiting costs less than a stop already happening.

Trial run 5: an operator reported MC-012 stopped (severity high, about 180 units
lost) and it ranked below a predicted job on MC-004 whose machine was still
running. The downtime term priced the forecast stop as if it were happening.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
from pdm.dispatch.solver import _job
from pdm.platform.config import load_config

CONFIG = load_config(Path("config"))
NOW = datetime(2026, 3, 3, 3, 0, tzinfo=UTC)
MECHANICAL = SkillId("robot_mechanical")
ANA = UserId("ana")
STOPPED = MachineId("MC-012")
RUNNING = MachineId("MC-004")


def _predicted(machine: MachineId = RUNNING) -> Queued:
    order = WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=FindingRef("F-p"),
        machine_id=machine,
        severity=Severity.HIGH,
        finding_kind=FindingKind.PREDICTED,
        eta=NOW + timedelta(hours=3),
        eta_confidence=timedelta(hours=1),
        estimated_minutes=60,
        required_skill=MECHANICAL,
        required_technicians=1,
        reason="forecast to cross its threshold",
        status=WorkOrderStatus.QUEUED,
    )
    return Queued(ref="WO-a-predicted", order=order, created_at=NOW)


def _happening(origin: WorkOrderOrigin, machine: MachineId = STOPPED) -> Queued:
    order = WorkOrder(
        origin=origin,
        finding_ref=FindingRef("F-d") if origin is WorkOrderOrigin.CONDITION else None,
        machine_id=machine,
        severity=Severity.HIGH,
        finding_kind=FindingKind.DETECTED if origin is WorkOrderOrigin.CONDITION else None,
        estimated_minutes=60,
        required_skill=MECHANICAL,
        required_technicians=1,
        reason="the machine has stopped",
        status=WorkOrderStatus.QUEUED,
    )
    return Queued(ref="WO-b-happening", order=order, created_at=NOW)


def _round(queue: list[Queued], planner=dispatch):  # type: ignore[no-untyped-def]
    return planner(
        queue,
        technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
        assignments=[(ANA, 300)],
        config=CONFIG,
        now=NOW,
    )


@pytest.mark.parametrize("origin", [WorkOrderOrigin.MANUAL, WorkOrderOrigin.CONDITION])
class TestAStopAlreadyHappeningRanksFirst:
    def test_the_greedy_score(self, origin: WorkOrderOrigin) -> None:
        result = _round([_predicted(), _happening(origin)])
        scores = {placed.ref: placed.priority_score for placed in result.placed}
        assert scores["WO-b-happening"] > scores["WO-a-predicted"]

    def test_even_when_the_forecast_machine_would_cost_more(self, origin: WorkOrderOrigin) -> None:
        """Swap the machines: the running one is now the costlier stop. A stop
        that has happened still outranks one that has not."""
        result = _round([_predicted(STOPPED), _happening(origin, RUNNING)])
        scores = {placed.ref: placed.priority_score for placed in result.placed}
        assert scores["WO-b-happening"] > scores["WO-a-predicted"]

    def test_the_shift_plan_agrees(self, origin: WorkOrderOrigin) -> None:
        result = _round([_predicted(), _happening(origin)], planner=schedule)
        scores = {placed.ref: placed.priority_score for placed in result.placed}
        assert scores["WO-b-happening"] > scores["WO-a-predicted"]


class TestTheTerm:
    def test_the_downtime_term_is_zero_for_a_predicted_order(self) -> None:
        result = _round([_predicted(), _happening(WorkOrderOrigin.MANUAL)])
        terms = {placed.ref: placed.terms for placed in result.placed}
        assert terms["WO-a-predicted"].downtime == 0.0
        assert terms["WO-b-happening"].downtime == 1.0

    def test_the_solver_prices_a_predicted_order_at_zero(self) -> None:
        assert _job(_predicted(), 1.0, CONFIG).rate == 0.0
        assert _job(_happening(WorkOrderOrigin.MANUAL), 1.0, CONFIG).rate > 0.0


class TestTheReasonStillStatesTheForecastStop:
    def test_the_cost_of_the_forecast_stop_is_printed(self) -> None:
        result = _round([_predicted()])
        (placed,) = result.placed
        assert "ถ้าเครื่องหยุดตามที่พยากรณ์ สายการผลิตจะเสียราว" in placed.priority_reason
        assert "ถ้างานนี้รอ" not in placed.priority_reason

    def test_a_stop_already_happening_says_waiting_costs(self) -> None:
        result = _round([_predicted(), _happening(WorkOrderOrigin.MANUAL)])
        reasons = {placed.ref: placed.priority_reason for placed in result.placed}
        assert "ถ้างานนี้รอ สายการผลิตจะเสียราว" in reasons["WO-b-happening"]

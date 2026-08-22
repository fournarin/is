"""Loop 1's evidence, read out of a real PostgreSQL (ADR-031, ADR-066).

Two things are checked here that the pure tests cannot: that the repair time the
loop learns from is the segments minus the waiting as the database holds them,
and that the false-alarm count reaches the rule that raised the Finding through
the join rather than through anything the work order stores.

The second matters because a work order deliberately does not carry a rule_id.
ADR-030 copies onto the order only what the scheduler needs, and the rule is not
that - so the count Loop 2 will one day need has to come from the join, and a
join nobody tested is a count that silently reads zero.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    ComponentLabel,
    Finding,
    MachineId,
    MachineModel,
    RuleId,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.triggers import repo as triggers
from pdm.work import playbook_ref_for
from pdm.work import repo as work
from pdm.work.estimates import propose

pytestmark = pytest.mark.db

NOW = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
SYM = SymptomCode("SYM-014")
OTHER_SYM = SymptomCode("SYM-031")
R2000IC = MachineModel("R-2000iC")
MOTOR = MachineId("MC-001")
RULE = RuleId("R-motor-temp-high")
OTHER_RULE = RuleId("R-fan-rpm-low")
REF = playbook_ref_for(SYM, R2000IC)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE work_order, finding CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _finding(conn: Connection[Any], *, rule_id: RuleId, symptom: SymptomCode) -> str:
    finding = Finding(
        machine_id=MOTOR,
        component=ComponentLabel("belt_motor"),
        symptom_code=symptom,
        severity=Severity.HIGH,
        rule_id=rule_id,
        detected_at=NOW,
        evidence={"metric": "motor_temp_c", "value": 91.0, "threshold": 85.0},
    )
    return str(triggers.raise_finding(conn, finding))


def _closed(
    conn: Connection[Any],
    *,
    finding_ref: str | None,
    worked_minutes: int,
    blocked_minutes: int = 0,
    outcome: WorkOutcome = WorkOutcome.FIXED,
    playbook_ref: str | None = REF,
) -> str:
    segments: tuple[WorkSegment, ...] = ()
    if worked_minutes > 0:
        segments = (
            WorkSegment(
                user=UserId("tech-1"),
                started_at=NOW,
                ended_at=NOW + timedelta(minutes=worked_minutes),
            ),
        )
    order = WorkOrder(
        origin=WorkOrderOrigin.CONDITION if finding_ref else WorkOrderOrigin.MANUAL,
        finding_ref=finding_ref,  # type: ignore[arg-type]
        machine_id=MOTOR,
        severity=Severity.HIGH,
        playbook_ref=playbook_ref,  # type: ignore[arg-type]
        estimated_minutes=45,
        reason="over threshold for 20 minutes",
        status=WorkOrderStatus.CLOSED,
        work_segments=segments,
        blocked_minutes=blocked_minutes,
        outcome=outcome,
    )
    return work.issue(conn, order, now=NOW)


class TestWhatTheEvidenceReadsAs:
    def test_the_repair_time_is_the_segments_with_the_waiting_removed(
        self, conn: Connection[Any]
    ) -> None:
        finding = _finding(conn, rule_id=RULE, symptom=SYM)
        ref = _closed(conn, finding_ref=finding, worked_minutes=90, blocked_minutes=40)

        jobs = work.closed_jobs_for(conn, playbook_ref=REF)

        assert [(job.work_order_ref, job.repair_minutes) for job in jobs] == [(ref, 50)]
        assert jobs[0].rule_id == RULE

    def test_open_orders_are_not_evidence(self, conn: Connection[Any]) -> None:
        finding = _finding(conn, rule_id=RULE, symptom=SYM)
        open_order = WorkOrder(
            origin=WorkOrderOrigin.CONDITION,
            finding_ref=finding,  # type: ignore[arg-type]
            machine_id=MOTOR,
            severity=Severity.HIGH,
            playbook_ref=REF,
            estimated_minutes=45,
            reason="over threshold for 20 minutes",
            status=WorkOrderStatus.IN_PROGRESS,
            work_segments=(WorkSegment(user=UserId("tech-1"), started_at=NOW),),
        )
        work.issue(conn, open_order, now=NOW)

        assert work.closed_jobs_for(conn, playbook_ref=REF) == []

    def test_another_playbooks_jobs_are_not_this_playbooks_evidence(
        self, conn: Connection[Any]
    ) -> None:
        finding = _finding(conn, rule_id=RULE, symptom=SYM)
        _closed(
            conn,
            finding_ref=finding,
            worked_minutes=200,
            playbook_ref=playbook_ref_for(OTHER_SYM, R2000IC),
        )
        mine = _closed(conn, finding_ref=finding, worked_minutes=50)

        jobs = work.closed_jobs_for(conn, playbook_ref=REF)

        assert [job.work_order_ref for job in jobs] == [mine]

    def test_the_evidence_becomes_a_proposal(self, conn: Connection[Any]) -> None:
        """End to end on real rows: five closed jobs of a known length, and the
        number a reviewer would be shown."""
        finding = _finding(conn, rule_id=RULE, symptom=SYM)
        for _ in range(5):
            _closed(conn, finding_ref=finding, worked_minutes=80, blocked_minutes=20)

        proposal = propose(
            work.closed_jobs_for(conn, playbook_ref=REF),
            symptom_code=SYM,
            machine_model=R2000IC,
            current_minutes=45,
            min_observations=5,
            max_change_ratio=0.20,
        )

        assert proposal is not None
        assert proposal.median_minutes == 60
        assert proposal.proposed_minutes == 54  # 45 + 20%, and the record says so
        assert proposal.capped is True


class TestTheFalseAlarmCount:
    def test_it_is_counted_per_rule_and_per_symptom(self, conn: Connection[Any]) -> None:
        motor = _finding(conn, rule_id=RULE, symptom=SYM)
        _closed(conn, finding_ref=motor, worked_minutes=10, outcome=WorkOutcome.NO_PROBLEM_FOUND)
        _closed(conn, finding_ref=motor, worked_minutes=10, outcome=WorkOutcome.NO_PROBLEM_FOUND)
        # Resolved first: one open Finding per (machine, rule) is the whole of
        # ADR-023, so a second one needs the first out of the way.
        triggers.resolve(conn, motor, now=NOW)  # type: ignore[arg-type]
        fan = _finding(conn, rule_id=OTHER_RULE, symptom=OTHER_SYM)
        _closed(conn, finding_ref=fan, worked_minutes=10, outcome=WorkOutcome.NO_PROBLEM_FOUND)
        _closed(conn, finding_ref=fan, worked_minutes=60, outcome=WorkOutcome.FIXED)

        counts = work.false_alarms(conn)

        assert [(count.symptom_code, count.rule_id, count.orders) for count in counts] == [
            (SYM, RULE, 2),
            (OTHER_SYM, OTHER_RULE, 1),
        ]

    def test_work_no_rule_raised_is_reported_rather_than_counted_against_one(
        self, conn: Connection[Any]
    ) -> None:
        """A reported fault that turned out to be nothing is not a rule's false
        alarm. Dropping it would be the honest-looking mistake; counting it
        against a rule would be the dangerous one."""
        _closed(conn, finding_ref=None, worked_minutes=10, outcome=WorkOutcome.NO_PROBLEM_FOUND)

        counts = work.false_alarms(conn)

        assert [(count.symptom_code, count.rule_id, count.orders) for count in counts] == [
            (None, None, 1)
        ]

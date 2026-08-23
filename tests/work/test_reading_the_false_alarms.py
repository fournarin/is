"""Loop 2's evidence, read out of a real PostgreSQL (ADR-031, ADR-067).

Three things are checked here that the pure tests cannot. That the reading a
proposal is built from is the one layer 1 wrote into `evidence`, reached through
the join rather than through anything the work order stores - a work order
deliberately carries no rule_id (ADR-030). That a Finding which flapped forty
times is **one** observation and not forty, which is the difference between an
evidence set and one sensor's morning (ADR-023, ADR-067 section 2). And that a
Finding whose evidence recorded no reading is counted rather than quietly
shrinking the set it was part of.
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
    FindingKind,
    MachineId,
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
from pdm.work import repo as work
from pdm.work.thresholds import NoProposal, ThresholdProposal, propose

pytestmark = pytest.mark.db

NOW = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
SYM = SymptomCode("SYM-014")
RULE = RuleId("R-motor-temp-high")
OTHER_RULE = RuleId("R-fan-rpm-low")


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


def _finding(
    conn: Connection[Any],
    *,
    machine: str,
    rule_id: RuleId = RULE,
    value: float | None = 91.0,
    kind: FindingKind = FindingKind.DETECTED,
) -> str:
    """One Finding on its own machine, so ADR-023's suppression key stays clear.

    The key is (machine_id, rule_id), so a rule watching ten machines can hold ten
    open Findings - which is also what a rule does in a plant.
    """
    evidence: dict[str, object] = {"metric_name": "motor_temp_c", "threshold": 85.0}
    if value is not None:
        evidence["value"] = value
    return str(
        triggers.raise_finding(
            conn,
            Finding(
                machine_id=MachineId(machine),
                component=ComponentLabel("belt_motor"),
                symptom_code=SYM,
                severity=Severity.HIGH,
                rule_id=rule_id,
                detected_at=NOW,
                evidence=evidence,
                kind=kind,
                eta=NOW + timedelta(hours=6) if kind is FindingKind.PREDICTED else None,
                eta_confidence=timedelta(hours=2) if kind is FindingKind.PREDICTED else None,
            ),
        )
    )


def _closed(
    conn: Connection[Any],
    *,
    finding_ref: str,
    machine: str,
    outcome: WorkOutcome,
) -> str:
    order = WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=finding_ref,  # type: ignore[arg-type]
        machine_id=MachineId(machine),
        severity=Severity.HIGH,
        estimated_minutes=45,
        reason="over threshold for 20 minutes",
        status=WorkOrderStatus.CLOSED,
        work_segments=(
            WorkSegment(
                user=UserId("tech-1"), started_at=NOW, ended_at=NOW + timedelta(minutes=30)
            ),
        ),
        outcome=outcome,
    )
    return work.issue(conn, order, now=NOW)


def _history(conn: Connection[Any], readings: list[tuple[float, WorkOutcome]]) -> list[str]:
    refs = []
    for index, (value, outcome) in enumerate(readings):
        machine = f"MC-{index:03d}"
        finding = _finding(conn, machine=machine, value=value)
        refs.append(_closed(conn, finding_ref=finding, machine=machine, outcome=outcome))
    return refs


ALARM = WorkOutcome.NO_PROBLEM_FOUND
FIXED = WorkOutcome.FIXED


class TestWhatTheReaderGathers:
    def test_the_reading_comes_from_the_findings_evidence_through_the_join(
        self, conn: Connection[Any]
    ) -> None:
        _history(conn, [(86.5, ALARM), (93.0, FIXED)])

        groups = work.firings_behind_rules(conn)

        assert [group.rule_id for group in groups] == [RULE]
        assert sorted(firing.value for firing in groups[0].firings) == [86.5, 93.0]

    def test_one_finding_that_fired_forty_times_is_one_observation(
        self, conn: Connection[Any]
    ) -> None:
        """ADR-023's occurrence count is not a count of evidence.

        Weighted by occurrences this one flapping sensor would be forty
        observations, clear the floor of ten on its own, and produce a proposal
        that read as though forty jobs supported it.
        """
        finding = _finding(conn, machine="MC-001", value=86.5)
        for _ in range(39):
            triggers.repeat(conn, machine_id=MachineId("MC-001"), rule_id=RULE, now=NOW)
        _closed(conn, finding_ref=finding, machine="MC-001", outcome=ALARM)

        groups = work.firings_behind_rules(conn)

        assert len(groups[0].firings) == 1

    def test_a_finding_with_no_reading_is_counted_rather_than_dropped(
        self, conn: Connection[Any]
    ) -> None:
        finding = _finding(conn, machine="MC-001", value=None)
        _closed(conn, finding_ref=finding, machine="MC-001", outcome=ALARM)
        good = _finding(conn, machine="MC-002", value=93.0)
        _closed(conn, finding_ref=good, machine="MC-002", outcome=FIXED)

        groups = work.firings_behind_rules(conn)

        assert len(groups[0].firings) == 1
        assert groups[0].without_a_reading == 1

    def test_open_orders_are_not_evidence(self, conn: Connection[Any]) -> None:
        finding = _finding(conn, machine="MC-001", value=86.5)
        work.issue(
            conn,
            WorkOrder(
                origin=WorkOrderOrigin.CONDITION,
                finding_ref=finding,  # type: ignore[arg-type]
                machine_id=MachineId("MC-001"),
                severity=Severity.HIGH,
                estimated_minutes=45,
                reason="over threshold for 20 minutes",
                status=WorkOrderStatus.IN_PROGRESS,
            ),
            now=NOW,
        )

        assert work.firings_behind_rules(conn) == []

    def test_each_rule_gets_its_own_group(self, conn: Connection[Any]) -> None:
        motor = _finding(conn, machine="MC-001", value=86.5)
        _closed(conn, finding_ref=motor, machine="MC-001", outcome=ALARM)
        fan = _finding(conn, machine="MC-002", rule_id=OTHER_RULE, value=1150.0)
        _closed(conn, finding_ref=fan, machine="MC-002", outcome=FIXED)

        groups = work.firings_behind_rules(conn)

        assert [group.rule_id for group in groups] == [OTHER_RULE, RULE]

    def test_a_predicted_finding_is_carried_and_marked(self, conn: Connection[Any]) -> None:
        """Carried by the reader, set aside by the arithmetic.

        The reader does not filter, so the count of what was set aside can be
        reported; the decision belongs in one place (ADR-067 section 2).
        """
        finding = _finding(conn, machine="MC-001", value=86.5, kind=FindingKind.PREDICTED)
        _closed(conn, finding_ref=finding, machine="MC-001", outcome=ALARM)

        groups = work.firings_behind_rules(conn)

        assert groups[0].firings[0].finding_kind is FindingKind.PREDICTED


class TestTheEvidenceBecomesAProposal:
    def test_end_to_end_on_real_rows(self, conn: Connection[Any]) -> None:
        """Six false alarms up to 87.0 and four faults from 92.0, on real rows.

        The number a reviewer would be shown, worked out by hand: 87.0 is the
        hottest reading nobody found anything at, it sits below 92.0, and the cap
        allows 93.5 so nothing is held back.
        """
        _history(
            conn,
            [
                (85.4, ALARM),
                (85.9, ALARM),
                (86.2, ALARM),
                (86.6, ALARM),
                (86.8, ALARM),
                (87.0, ALARM),
                (92.0, FIXED),
                (95.5, FIXED),
                (99.0, FIXED),
                (104.0, FIXED),
            ],
        )

        (group,) = work.firings_behind_rules(conn)
        result = propose(
            group.firings,
            rule_id=RULE,
            comparison="above",
            current_threshold=85.0,
            safety_critical=False,
            min_observations=10,
            max_change_ratio=0.10,
        )

        assert isinstance(result, ThresholdProposal)
        assert result.proposed_threshold == 87.0
        assert result.false_alarms == 6
        assert len(result.still_fires_on) == 4

    def test_nothing_in_this_path_writes_a_threshold(self, conn: Connection[Any]) -> None:
        """The rule the loop learns from is untouched by the loop.

        `rules.yaml` is not a table, so there is nothing here that could be
        written - which is the point, and this asserts the path stays that way:
        the proposal is a value in memory and the run leaves no trace of it.
        """
        _history(conn, [(86.0, ALARM)] * 6 + [(96.0, FIXED)] * 4)

        (group,) = work.firings_behind_rules(conn)
        result = propose(
            group.firings,
            rule_id=RULE,
            comparison="above",
            current_threshold=85.0,
            safety_critical=False,
            min_observations=10,
            max_change_ratio=0.10,
        )

        assert isinstance(result, (ThresholdProposal, NoProposal))
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM finding")
            assert cur.fetchone() == (10,)

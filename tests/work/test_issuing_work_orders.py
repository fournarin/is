"""Layer 4 against a real PostgreSQL: three origins, one ticket (ADR-010).

The test that matters most in this file is the one that tries to change a
`playbook_snapshot` through raw SQL and must fail. Invariant 2 asks for a
database constraint rather than a convention, because frozen pydantic models stop
the application and stop nothing else - and the column is the only evidence of
what a job closed a year ago instructed (ADR-018).

The rest is the pricing. An order priced wrongly does not raise anything: it
makes the shift look busier or emptier than it is, and the load gate then holds
back or releases the wrong work with no error anywhere (design.md 13.2).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

# The trigger raises with ERRCODE restrict_violation, which psycopg maps to this.
# Asserting the class rather than the message means a future trigger that keeps
# the words and loses the error code still fails this test.
from psycopg.errors import RestrictViolation

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    FindingRef,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    PMTask,
    PMTaskRef,
    Role,
    RuleId,
    Severity,
    SkillId,
    SymptomCode,
    UserId,
    WorkOrderOrigin,
)
from pdm.contracts.ids import DocumentId
from pdm.platform.auth import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import repo as playbooks
from pdm.work import NoEstimateAvailable, WorkOrders
from pdm.work import repo as work

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
R2000IC = MachineModel("R-2000iC")
MOTOR = MachineId("MC-001")
SYM = SymptomCode("SYM-014")
ENGINEER = UserId("eng-1")
TECHNICIAN = UserId("tech-1")

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE work_order, playbook_proposal, playbook, chunk, document_page, "
            "document, access_log, session, account CASCADE"
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
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


@pytest.fixture
def manual(conn: Connection[Any], tmp_path: Path, clock: SimulatedClock) -> DocumentId:
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    document = library.add(
        conn,
        content=b"%PDF-1.4 a manual",
        filename="r-2000ic.pdf",
        content_type="application/pdf",
        machine_model=R2000IC,
        title="R-2000iC Maintenance Manual",
        uploaded_by=UserId("op-1"),
    )
    auth = Authentication(LocalAccounts(), clock)
    auth.create_account(
        conn, user=ENGINEER, display_name="An Engineer", role=Role.ENGINEER, password="x" * 12
    )
    return document.document_id


def _approved_playbook(
    conn: Connection[Any],
    manual: DocumentId,
    *,
    symptom: SymptomCode = SYM,
    minutes: int = 45,
    technicians: int = 1,
) -> Playbook:
    playbook = Playbook(
        symptom_code=symptom,
        machine_model=R2000IC,
        steps=(
            PlaybookStep(
                text="Retighten the motor mount bolts to 42 Nm.",
                source_doc=manual,
                page=4,
                confidence=0.9,
            ),
        ),
        estimated_minutes=minutes,
        required_skill=SkillId("robot_mechanical"),
        required_technicians=technicians,
        source_doc=manual,
        page=4,
        status=PlaybookStatus.APPROVED,
        approved_by=ENGINEER,
        approved_at=NOW,
        approver_role=Role.ENGINEER,
    )
    playbooks.save_approved(
        conn, playbook, approved_by=ENGINEER, approved_at=NOW, approver_role=Role.ENGINEER
    )
    return playbook


def _finding(**overrides: Any) -> Finding:
    base: dict[str, Any] = {
        "machine_id": MOTOR,
        "component": ComponentLabel("belt_motor"),
        "symptom_code": SYM,
        "severity": Severity.HIGH,
        "rule_id": RuleId("R-motor-temp-high"),
        "detected_at": NOW,
        "evidence": {"value": 91.0, "threshold": 85.0, "for_seconds": 1200},
    }
    return Finding(**(base | overrides))


class TestInvariantTwo:
    """The snapshot is frozen by the database, not by good manners."""

    def test_raw_sql_cannot_change_a_snapshot(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """The case the trigger exists for: a writer that is not this codebase.

        A migration, a repair script, or a future repo.py doing `UPDATE
        work_order SET ...` all reach this row, and none of them goes through a
        frozen pydantic model.
        """
        _approved_playbook(conn, manual)
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        with pytest.raises(RestrictViolation, match="frozen when the order is issued"):
            conn.execute(
                "UPDATE work_order SET playbook_snapshot = '[]'::jsonb WHERE work_order_ref = %s",
                (issued.ref,),
            )
        conn.rollback()

    def test_the_approval_on_the_snapshot_is_frozen_too(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """Who approved it is half the evidence. Steps nobody can attribute
        prove nothing after an accident (principle 2)."""
        _approved_playbook(conn, manual)
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        with pytest.raises(RestrictViolation):
            conn.execute(
                "UPDATE work_order SET snapshot_approved_by = 'somebody-else' "
                "WHERE work_order_ref = %s",
                (issued.ref,),
            )
        conn.rollback()

    def test_everything_else_on_the_order_still_moves(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """The trigger has to be narrow, or the order could never be worked on."""
        _approved_playbook(conn, manual)
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        conn.execute(
            "UPDATE work_order SET priority_score = 7.5, priority_reason = 'first of four' "
            "WHERE work_order_ref = %s",
            (issued.ref,),
        )

        after = work.get(conn, issued.ref)
        assert after is not None
        assert after.priority_score == 7.5


class TestAConditionOrder:
    def test_the_playbook_is_bound_when_the_order_is_created(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """design.md 3.1: not at dispatch, because load_ratio needs the duration
        before anything is handed out."""
        _approved_playbook(conn, manual, minutes=45)

        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        assert issued.order.estimated_minutes == 45
        assert issued.order.required_skill == SkillId("robot_mechanical")
        assert issued.order.estimate_is_fallback is False
        assert issued.order.playbook_snapshot

    def test_the_snapshot_is_the_steps_as_they_were(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        _approved_playbook(conn, manual)

        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        stored = work.get(conn, issued.ref)
        assert stored is not None
        assert stored.playbook_snapshot[0].text.startswith("Retighten")
        assert stored.playbook_snapshot[0].page == 4
        assert stored.snapshot_approved_by == ENGINEER

    def test_a_ticket_number_comes_from_the_database(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        _approved_playbook(conn, manual)

        first = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )
        second = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-2"), machine_model=R2000IC
        )

        assert first.ref != second.ref
        assert first.ref.startswith("WO-")

    def test_a_detected_finding_says_what_crossed_what(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        _approved_playbook(conn, manual)

        issued = orders.from_finding(
            conn,
            _finding(occurrence_count=4),
            finding_ref=FindingRef("F-1"),
            machine_model=R2000IC,
        )

        assert "detected" in issued.order.reason
        assert "seen 4 times" in issued.order.reason

    def test_a_predicted_finding_keeps_its_interval(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """ui.md 2.2: "in about 6 hours" reads as more trustworthy than "in
        about 6 hours, give or take 2", and the second one is the truth."""
        _approved_playbook(conn, manual)

        issued = orders.from_finding(
            conn,
            _finding(
                kind=FindingKind.PREDICTED,
                eta=NOW + timedelta(hours=6),
                eta_confidence=timedelta(hours=2),
            ),
            finding_ref=FindingRef("F-1"),
            machine_model=R2000IC,
        )

        assert "predicted" in issued.order.reason
        assert "give or take 2 hours" in issued.order.reason
        assert issued.order.eta == NOW + timedelta(hours=6)


class TestWhenThereIsNoPlaybook:
    """design.md 3.2: the silent failure this whole path exists to prevent."""

    def test_the_job_is_still_priced_and_still_queued(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        assert issued.order.estimated_minutes == FALLBACK["R-2000iC"][Severity.HIGH]
        assert issued.order.estimate_is_fallback is True
        assert issued.order.playbook_ref is None

    def test_the_skill_is_left_empty_rather_than_guessed(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """A guess sends the wrong person to an electrical fault, and the guess
        is worse than the absence because the absence is visible (ADR-041)."""
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        assert issued.order.required_skill is None

    def test_a_model_with_no_fallback_declared_refuses_rather_than_inventing_one(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        with pytest.raises(NoEstimateAvailable, match="fallback_minutes"):
            orders.from_finding(
                conn,
                _finding(),
                finding_ref=FindingRef("F-1"),
                machine_model=MachineModel("R-9999iZ"),
            )

    def test_a_draft_playbook_is_not_bound(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """Invariant 3 reaches this far: a draft is not served, and binding one
        would put unreviewed steps on a ticket. The store cannot hold a draft
        (ADR-038), so this is belt and braces - and it is the belt that would
        matter if that ever changed."""
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        assert issued.order.playbook_snapshot == ()
        assert issued.order.estimate_is_fallback is True


class TestScheduledAndManualOrders:
    def test_a_pm_task_becomes_a_low_severity_order(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """ADR-010: the work a quiet shift is meant to absorb."""
        task = PMTask(
            pm_task_ref=PMTaskRef("PM-1"),
            machine_id=MOTOR,
            symptom_code=SymptomCode("PM-grease-axis-1"),
            interval=timedelta(days=30),
            due_at=NOW,
        )

        issued = orders.from_pm_task(conn, task, machine_model=R2000IC)

        assert issued.order.origin is WorkOrderOrigin.SCHEDULED
        assert issued.order.severity is Severity.LOW
        assert issued.order.pm_task_ref == PMTaskRef("PM-1")
        assert "scheduled maintenance" in issued.order.reason

    def test_a_pm_task_finds_its_playbook_through_the_ordinary_lookup(
        self, conn: Connection[Any], orders: WorkOrders, manual: DocumentId
    ) -> None:
        """design.md 13.3: layer 2 never learns the word "PM"."""
        pm_symptom = SymptomCode("PM-grease-axis-1")
        _approved_playbook(conn, manual, symptom=pm_symptom, minutes=30)
        task = PMTask(
            pm_task_ref=PMTaskRef("PM-1"),
            machine_id=MOTOR,
            symptom_code=pm_symptom,
            interval=timedelta(days=30),
            due_at=NOW,
        )

        issued = orders.from_pm_task(conn, task, machine_model=R2000IC)

        assert issued.order.estimated_minutes == 30
        assert issued.order.estimate_is_fallback is False

    def test_a_report_keeps_the_words_the_person_used(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        issued = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000IC,
            severity=Severity.MEDIUM,
            reported_by=TECHNICIAN,
            description="grinding noise from the belt side when the axis reverses",
        )

        assert issued.order.origin is WorkOrderOrigin.MANUAL
        assert "grinding noise" in issued.order.reason
        assert TECHNICIAN in issued.order.reason

    def test_a_report_with_no_symptom_code_still_becomes_a_ticket(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """Otherwise the system quietly requires a diagnosis before it will
        accept a problem, which is the wrong way round."""
        issued = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000IC,
            severity=Severity.LOW,
            reported_by=TECHNICIAN,
            description="something rattles",
        )

        assert issued.order.estimate_is_fallback is True
        assert work.get(conn, issued.ref) is not None


class TestWhatTheDispatchTickWillRead:
    def test_open_orders_come_back_oldest_first(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """Not sorted by severity: ranking is layer 3's job, and a repository
        that pre-sorted by one term of the score would be deciding part of it."""
        first = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000IC,
            severity=Severity.LOW,
            reported_by=TECHNICIAN,
            description="first",
        )
        clock.advance(timedelta(minutes=10))
        second = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000IC,
            severity=Severity.CRITICAL,
            reported_by=TECHNICIAN,
            description="second",
        )

        assert [ref for ref, _ in orders.open_orders(conn)] == [first.ref, second.ref]

    def test_a_closed_order_leaves_the_queue_and_stays_in_the_table(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        issued = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000IC,
            severity=Severity.LOW,
            reported_by=TECHNICIAN,
            description="something rattles",
        )

        conn.execute(
            "UPDATE work_order SET status = 'closed', outcome = 'fixed', closed_at = %s "
            "WHERE work_order_ref = %s",
            (clock.now(), issued.ref),
        )

        assert orders.open_orders(conn) == []
        assert work.get(conn, issued.ref) is not None

    def test_what_a_finding_produced_can_be_traced_back(
        self, conn: Connection[Any], orders: WorkOrders
    ) -> None:
        """The direction ADR-030 keeps open: back from the order, never from the
        scheduler."""
        issued = orders.from_finding(
            conn, _finding(), finding_ref=FindingRef("F-1"), machine_model=R2000IC
        )

        assert [ref for ref, _ in work.for_finding(conn, FindingRef("F-1"))] == [issued.ref]

"""What the technician's screen reads, and the two things it must not get wrong.

Slice 10.3 turns one work order into the screen somebody stands at a machine
holding, and the ticket endpoint had to grow four things to serve it: the steps
that were issued, whether the job is predicted or already over, the interval
around a prediction, and how often the rule behind it has fired.

Two of these tests carry the slice:

  * `test_the_steps_are_the_ones_the_order_was_issued_with` - ADR-018 dropped the
    playbook version chain on the argument that the work order keeps its own
    copy. A screen reading the served table instead would show a technician
    steps nobody ever gave them, and the approval that overwrites the row is a
    normal Tuesday.
  * `test_seen_n_times_counts_up_while_the_orders_own_figures_do_not` - the two
    halves of ADR-041 in one assertion. The snapshot on the order is frozen on
    purpose; the recurrence is read live on purpose; and a screen showing both
    has to get each from the right side.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import (
    ComponentLabel,
    DocumentId,
    Finding,
    FindingKind,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    RuleId,
    Severity,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import repo as playbooks
from pdm.triggers import repo as findings
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
SYM = SymptomCode("SYM-014")
RULE = RuleId("R-motor-temp-high/trend")
TECHNICIAN = UserId("tech-1")
ENGINEER = UserId("eng-1")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}

ISSUED_STEP = "Isolate breaker CP-3 and apply your personal lock."
REAPPROVED_STEP = "Isolate breaker CP-7 and apply your personal lock."


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


def _playbook(manual: DocumentId, *, step: str, page: int) -> Playbook:
    return Playbook(
        symptom_code=SYM,
        machine_model=R2000,
        steps=(PlaybookStep(text=step, source_doc=manual, page=page, confidence=0.9),),
        estimated_minutes=45,
        required_skill=SkillId("robot_mechanical"),
        required_technicians=1,
        source_doc=manual,
        page=page,
        status=PlaybookStatus.APPROVED,
        approved_by=ENGINEER,
        approved_at=NOW,
        approver_role=Role.ENGINEER,
    )


def _approve(conn: Connection[Any], playbook: Playbook) -> None:
    playbooks.save_approved(
        conn, playbook, approved_by=ENGINEER, approved_at=NOW, approver_role=Role.ENGINEER
    )


@pytest.fixture
def world(database_url: str, clock: SimulatedClock, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A predicted job with a playbook and a live Finding, and a reported job
    with neither."""
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    refs: dict[str, str] = {}

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, chunk, document_page, document, "
            "playbook, playbook_proposal, access_log, session, account CASCADE"
        )
        for user, name, role in [
            (TECHNICIAN, "Somchai", Role.TECHNICIAN),
            (ENGINEER, "Pranee", Role.ENGINEER),
        ]:
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        manual = library.add(
            conn,
            content=b"%PDF-1.4 a manual",
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000,
            title="R-2000iC Maintenance Manual",
            uploaded_by=ENGINEER,
        ).document_id
        _approve(conn, _playbook(manual, step=ISSUED_STEP, page=142))

        finding = Finding(
            machine_id=MOTOR,
            component=ComponentLabel("belt_motor"),
            symptom_code=SYM,
            severity=Severity.HIGH,
            rule_id=RULE,
            detected_at=NOW,
            evidence={"trend": True, "slope_per_hour": 1.4},
            kind=FindingKind.PREDICTED,
            eta=NOW + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
        )
        finding_ref = findings.raise_finding(conn, finding)
        refs["predicted"] = orders.from_finding(
            conn, finding, finding_ref=finding_ref, machine_model=R2000
        ).ref
        # No Finding behind it and no symptom code, so no playbook either: the
        # shape most of the backlog has (ADR-010).
        refs["reported"] = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000,
            severity=Severity.MEDIUM,
            reported_by=ENGINEER,
            description="grinding noise on start-up",
            # The machine already carries the predicted job above, and a report
            # on a machine with work open is refused unless somebody says it is
            # a different fault (ADR-077 §3). This one is: a noise on start-up
            # is not the motor temperature trend.
            distinct_from=[refs["predicted"]],
        ).ref
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "clock": clock, "refs": refs, "manual": manual, "url": database_url}
    finally:
        pool.close()


@pytest.fixture
def client(world: dict[str, Any], tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(
        pool=world["pool"],
        library=DocumentLibrary(FilesystemObjectStore(tmp_path), world["clock"]),
        clock=world["clock"],
    )
    with TestClient(app) as test_client:
        response = test_client.post(
            "/sessions", json={"user": str(TECHNICIAN), "password": PASSWORD}
        )
        assert response.status_code == 201, response.text
        yield test_client


def _ticket(client: TestClient, ref: str) -> dict[str, Any]:
    response = client.get(f"/work-orders/{ref}")
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestAPredictionArrivesWholeOrNotAtAll:
    def test_a_predicted_ticket_never_serialises_an_eta_without_its_interval(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-020. "About six hours" reads as more trustworthy than "about six
        hours, give or take two", and the first is a promise the system cannot
        keep. The pair is the contract, and this is the layer where dropping
        half of it would be invisible."""
        body = _ticket(client, world["refs"]["predicted"])

        assert body["finding_kind"] == "predicted"
        assert body["eta"] is not None
        assert body["eta_confidence_minutes"] == 120

    def test_a_reported_ticket_carries_no_eta_at_all(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        body = _ticket(client, world["refs"]["reported"])

        assert body["finding_kind"] is None
        assert body["eta"] is None
        assert body["eta_confidence_minutes"] is None


class TestTheStepsAreTheOnesThatWereIssued:
    def test_the_steps_are_the_ones_the_order_was_issued_with(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-018 dropped the version chain because the order keeps its own
        copy. Re-approving the playbook overwrites the served row, and the
        ticket must not move with it - a technician standing at the machine is
        carrying out what they were given, not what was approved since."""
        ref = world["refs"]["predicted"]
        before = _ticket(client, ref)
        assert [step["text"] for step in before["steps"]] == [ISSUED_STEP]

        with connect(world["url"]) as conn:
            _approve(conn, _playbook(world["manual"], step=REAPPROVED_STEP, page=7))
            conn.commit()

        after = _ticket(client, ref)
        assert [step["text"] for step in after["steps"]] == [ISSUED_STEP]
        assert [step["page"] for step in after["steps"]] == [142]

    def test_each_step_brings_the_page_it_came_from(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """The page number is what the screen turns into a link that opens the
        manual there. Without it the citation is a claim nobody can check."""
        step = _ticket(client, world["refs"]["predicted"])["steps"][0]

        assert step["page"] == 142
        assert step["source_doc"] == str(world["manual"])

    def test_a_job_with_no_playbook_has_no_steps_rather_than_empty_ones(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        body = _ticket(client, world["refs"]["reported"])

        assert body["steps"] == []
        assert body["estimate_is_fallback"] is True


class TestHowOftenThisHasBeenSeen:
    def test_seen_n_times_counts_up_while_the_orders_own_figures_do_not(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-023 raises the count on the existing Finding rather than opening a
        second one, and ADR-041 freezes what the order copied. The screen shows
        both at once, so each has to come from the right side: the count moves,
        the severity and the ETA do not."""
        ref = world["refs"]["predicted"]
        before = _ticket(client, ref)
        assert before["recurrence"]["occurrence_count"] == 1

        with connect(world["url"]) as conn:
            for minutes in (5, 10, 15):
                assert findings.repeat(
                    conn, machine_id=MOTOR, rule_id=RULE, now=NOW + timedelta(minutes=minutes)
                )
            conn.commit()

        after = _ticket(client, ref)
        assert after["recurrence"]["occurrence_count"] == 4
        assert after["recurrence"]["last_seen_at"] is not None
        assert after["recurrence"]["detected_at"] == before["recurrence"]["detected_at"]
        # The frozen half, unmoved.
        assert after["eta"] == before["eta"]
        assert after["severity"] == before["severity"]

    def test_work_with_no_finding_says_nothing_rather_than_seen_once(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """Most lower-priority work has no Finding at all (ADR-010). "Seen once"
        and "there is nothing to count" are different sentences, and a screen
        must not print the first when it means the second."""
        assert _ticket(client, world["refs"]["reported"])["recurrence"] is None


class TestWhereToLookWithoutSteps:
    """ADR-118: a ticket with no approved steps names where to look instead of
    only "don't guess" - the manuals in service, and a waiting draft's pages,
    marked as not approved."""

    def test_a_job_without_steps_names_the_manual_for_its_model(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        ticket = _ticket(client, world["refs"]["reported"])

        assert ticket["steps"] == []
        assert ticket["where_to_look"] == [
            {
                "document_id": str(world["manual"]),
                "manual": "R-2000iC Maintenance Manual",
                "page": None,
                "from_unapproved_draft": False,
            }
        ]

    def test_a_job_with_steps_needs_no_such_list(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        assert _ticket(client, world["refs"]["predicted"])["where_to_look"] == []

    def test_a_waiting_draft_s_pages_come_first_and_say_they_are_unapproved(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        from pdm.playbooks.domain import ProposalOrigin

        other = SymptomCode("SYM-021")
        with connect(world["url"]) as conn:
            finding = Finding(
                machine_id=MachineId("MC-004"),
                component=ComponentLabel("servo_axis_1"),
                symptom_code=other,
                severity=Severity.MEDIUM,
                rule_id=RuleId("R-servo-current-high"),
                detected_at=NOW,
                evidence={"value": 13.1},
                kind=FindingKind.DETECTED,
            )
            finding_ref = findings.raise_finding(conn, finding)
            ref = (
                WorkOrders(world["clock"], fallback_minutes=FALLBACK)
                .from_finding(conn, finding, finding_ref=finding_ref, machine_model=R2000)
                .ref
            )
            playbooks.add_proposal(
                conn,
                symptom_code=other,
                machine_model=R2000,
                origin=ProposalOrigin.DRAFTED,
                outcome="repair",
                steps=(
                    PlaybookStep(
                        text="Check axis 1 current.",
                        source_doc=world["manual"],
                        page=57,
                        confidence=0.8,
                    ),
                    PlaybookStep(
                        text="Inspect the reducer.",
                        source_doc=world["manual"],
                        page=57,
                        confidence=0.8,
                    ),
                ),
                tools=(),
                proposed_skill=None,
                proposed_minutes=None,
                rejected=(),
                reason="drafted for the test",
                created_at=NOW,
                created_by=ENGINEER,
            )
            conn.commit()

        where = _ticket(client, ref)["where_to_look"]

        assert where[0] == {
            "document_id": str(world["manual"]),
            "manual": "R-2000iC Maintenance Manual",
            "page": 57,
            "from_unapproved_draft": True,
        }
        assert where[1]["page"] is None
        assert len(where) == 2

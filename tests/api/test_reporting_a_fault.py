"""The third origin, over HTTP: somebody saw something (slice 16.2, ADR-077).

`from_report()` has been in the work module since it was written and, until this
router, was called by tests and by nothing a person could reach. What is checked
here is the endpoint's own decisions rather than the order the work module
builds - which of them may report, what severity a report may carry, and what a
second report on a machine that already has work open does.

The refusals matter more than the acceptance. A report is the one input to this
system that arrives with no rule behind it, and every one of these rules exists
because of what happens on a plant floor rather than in a test: four people see
one stopped line, somebody reaches for `critical` because it is the strongest
word on the screen, and somebody types a machine number that is on a different
line.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import (
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    Severity,
    SkillId,
    SymptomCode,
    UserId,
    WorkOutcome,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.playbooks import repo as playbooks
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MACHINE = MachineId("MC-012")
OTHER_MACHINE = MachineId("MC-018")
R2000 = MachineModel("R-2000iC")
SYMPTOM = SymptomCode("SYM-hydraulic-leak")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}

# All four roles, because ADR-077 section 1 is the claim that all four may report
# and a test that signed in as one of them would not be testing it.
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Nok"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
    Role.OPERATOR: (UserId("op-1"), "Malee"),
}


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def world(database_url: str, clock: SimulatedClock, tmp_path: Path) -> Iterator[dict[str, Any]]:
    from pdm.platform.documents import DocumentLibrary
    from pdm.platform.objects import FilesystemObjectStore

    auth = Authentication(LocalAccounts(), clock)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, playbook, document_page, document, "
            "access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)
        manual = library.add(
            conn,
            content=b"%PDF-1.4 a manual",
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000,
            title="R-2000iC Maintenance Manual",
            uploaded_by=UserId("eng-1"),
        ).document_id
        playbooks.save_approved(
            conn,
            Playbook(
                symptom_code=SYMPTOM,
                machine_model=R2000,
                steps=(
                    PlaybookStep(
                        text="isolate the hydraulic supply at the wall valve",
                        source_doc=manual,
                        page=41,
                        confidence=0.9,
                    ),
                ),
                estimated_minutes=45,
                required_skill=SkillId("hydraulics"),
                required_technicians=1,
                source_doc=manual,
                page=41,
                revision=1,
                status=PlaybookStatus.APPROVED,
                approved_by=UserId("eng-1"),
                approved_at=NOW,
                approver_role=Role.ENGINEER,
            ),
            approved_by=UserId("eng-1"),
            approved_at=NOW,
            approver_role=Role.ENGINEER,
        )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "clock": clock, "database_url": database_url}
    finally:
        pool.close()


@pytest.fixture
def client(world: dict[str, Any], tmp_path: Any) -> Iterator[TestClient]:
    from pdm.platform.documents import DocumentLibrary
    from pdm.platform.objects import FilesystemObjectStore

    app = create_app(
        pool=world["pool"],
        library=DocumentLibrary(FilesystemObjectStore(tmp_path), world["clock"]),
        clock=world["clock"],
    )
    with TestClient(app) as test_client:
        yield test_client


def _signed_in(client: TestClient, role: Role) -> TestClient:
    user, _ = PEOPLE[role]
    response = client.post("/sessions", json={"user": str(user), "password": PASSWORD})
    assert response.status_code == 201, response.text
    return client


def _report(client: TestClient, **fields: Any) -> Any:
    body: dict[str, Any] = {
        "machine_id": str(MACHINE),
        "severity": "medium",
        "description": "oil under the base plate, about a hand's width",
    }
    body.update(fields)
    return client.post("/work-orders", json=body)


class TestAnybodyOnTheFloorMayReport:
    """ADR-077 section 1. The role is not the gate; the session is."""

    @pytest.mark.parametrize("role", list(PEOPLE))
    def test_every_role_with_an_account_may_report(self, client: TestClient, role: Role) -> None:
        _signed_in(client, role)
        response = _report(client)
        assert response.status_code == 201, response.text
        assert response.json()["ref"].startswith("WO-")

    def test_a_report_with_no_session_is_refused(self, client: TestClient) -> None:
        """`reason` names the reporter, so an anonymous report is one nobody can
        be asked about (ADR-024's consequence, ADR-077 section 1)."""
        assert _report(client).status_code == 401

    def test_the_report_is_in_the_access_log_with_who_made_it(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.OPERATOR)
        assert _report(client).status_code == 201

        with connect(world["database_url"]) as conn:
            rows = conn.execute(
                "SELECT user_id, role, allowed FROM access_log WHERE action = 'report_fault'"
            ).fetchall()
        assert rows == [("op-1", "operator", True)]


class TestWhatTheTicketSays:
    def test_the_reason_is_the_reporters_words_with_who_and_when_around_them(
        self, client: TestClient
    ) -> None:
        """ADR-005 and ADR-077 section 5: the endpoint may not rephrase it."""
        _signed_in(client, Role.TECHNICIAN)
        response = _report(client, description="ได้ยินเสียงดังผิดปกติที่หัวจับ")
        assert response.status_code == 201, response.text

        reason = response.json()["reason"]
        assert "ได้ยินเสียงดังผิดปกติที่หัวจับ" in reason
        assert "tech-1" in reason
        assert "2026-03-03 08:00 UTC" in reason

    def test_a_report_with_no_symptom_code_is_priced_from_the_fallback_and_says_so(
        self, client: TestClient
    ) -> None:
        """No code means no playbook, and `required_skill` stays empty rather
        than guessed: a guess sends the wrong person (ADR-041, ADR-077 §4)."""
        _signed_in(client, Role.TECHNICIAN)
        body = _report(client).json()

        assert body["playbook_ref"] is None
        assert body["estimate_is_fallback"] is True
        assert body["required_skill"] is None
        assert body["estimated_minutes"] == FALLBACK[str(R2000)][Severity.MEDIUM]

    def test_a_report_that_names_a_symptom_binds_that_playbook(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        body = _report(client, symptom_code=str(SYMPTOM)).json()

        assert body["playbook_ref"] is not None
        assert body["estimate_is_fallback"] is False
        assert body["estimated_minutes"] == 45
        assert body["required_skill"] == "hydraulics"

    def test_the_ticket_starts_queued_and_nothing_has_ranked_it(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """A report joins the queue and is proposed by a round like any other
        work; the reporter does not set a priority (ADR-071, ADR-077 §1)."""
        _signed_in(client, Role.SUPERVISOR)
        ref = _report(client).json()["ref"]

        with connect(world["database_url"]) as conn:
            row = conn.execute(
                "SELECT origin, status, priority_score, priority_reason "
                "FROM work_order WHERE work_order_ref = %s",
                (ref,),
            ).fetchone()
        assert row is not None
        origin, status_, score, priority_reason = row
        assert (origin, status_) == ("manual", "queued")
        assert (score, priority_reason) == (0.0, "")


class TestTheRefusalsAreNamed:
    def test_critical_is_refused_and_the_message_says_what_to_do_instead(
        self, client: TestClient
    ) -> None:
        """ADR-077 section 2. `high` already passes the gate on a heavy shift, so
        the ceiling costs no urgency; what it stops is a report outranking a
        measured crossing."""
        _signed_in(client, Role.TECHNICIAN)
        response = _report(client, severity="critical")

        assert response.status_code == 422
        assert "call the shift lead" in response.text

    def test_high_is_not_refused(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        assert _report(client, severity="high").status_code == 201

    def test_a_machine_this_plant_does_not_have_is_refused(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        response = _report(client, machine_id="MC-999")

        assert response.status_code == 422
        assert "MC-999" in response.text

    def test_a_description_of_spaces_is_refused_at_the_schema(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        assert _report(client, description="   ").status_code == 422

    def test_nothing_is_written_when_a_report_is_refused(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        _report(client, severity="critical")
        _report(client, machine_id="MC-999")

        with connect(world["database_url"]) as conn:
            written = conn.execute("SELECT count(*) FROM work_order").fetchone()
        assert written == (0,)


class TestASecondReportOnAMachineAlreadyBeingWorked:
    """ADR-077 section 3 - ADR-023's argument arriving with people instead of
    readings. One line stops, four people see it, four technicians are sent."""

    def test_the_second_report_is_refused_and_names_the_open_ticket(
        self, client: TestClient
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        first = _report(client).json()["ref"]

        second = _report(client, description="same noise as before")
        assert second.status_code == 409
        assert second.json()["detail"]["open_orders"] == [first]

    def test_another_machine_is_not_refused(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        _report(client)
        assert _report(client, machine_id=str(OTHER_MACHINE)).status_code == 201

    def test_naming_the_open_ticket_lets_a_different_fault_through(
        self, client: TestClient
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        first = _report(client).json()["ref"]

        second = _report(
            client,
            description="separate to the leak: the guard interlock is not latching",
            distinct_from=[first],
        )
        assert second.status_code == 201, second.text
        assert f"reported alongside {first}" in second.json()["reason"]

    def test_a_ticket_that_appeared_since_the_refusal_refuses_the_retry_too(
        self, client: TestClient
    ) -> None:
        """The override is against what the reporter was shown, which is the
        whole reason `distinct_from` names references rather than being a flag."""
        _signed_in(client, Role.TECHNICIAN)
        first = _report(client).json()["ref"]
        meanwhile = _report(client, distinct_from=[first]).json()["ref"]

        retry = _report(client, distinct_from=[first])
        assert retry.status_code == 409
        assert retry.json()["detail"]["open_orders"] == [first, meanwhile]

    def test_a_closed_ticket_does_not_hold_the_machine_shut(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        first = _report(client).json()["ref"]

        orders = WorkOrders(world["clock"], fallback_minutes=FALLBACK)
        with connect(world["database_url"]) as conn:
            orders.accept(conn, first, user=UserId("tech-1"))
            orders.start(conn, first, user=UserId("tech-1"))
            orders.close(conn, first, user=UserId("tech-1"), outcome=WorkOutcome.FIXED)
            conn.commit()

        assert _report(client).status_code == 201


class TestTheListOfMachinesToReportAgainst:
    """The report screen cannot offer a machine it has never heard of, and a
    free-text box on a phone collects typos and answers them with a 422."""

    def test_every_role_may_read_it(self, client: TestClient) -> None:
        _signed_in(client, Role.OPERATOR)
        response = client.get("/machines")
        assert response.status_code == 200, response.text
        assert {machine["machine_id"] for machine in response.json()} == {
            machine_id for station in CONFIG.stations.values() for machine_id in station.machine_ids
        }

    def test_it_is_in_line_order_because_that_is_the_order_somebody_walks_past(
        self, client: TestClient
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        machines = client.get("/machines").json()
        assert [machine["seq"] for machine in machines] == sorted(
            machine["seq"] for machine in machines
        )

    def test_each_machine_says_where_it_stands_and_what_it_is(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        machines = {row["machine_id"]: row for row in client.get("/machines").json()}
        assert machines[str(MACHINE)]["model"] == str(R2000)
        assert machines[str(MACHINE)]["station_id"]
        assert machines[str(MACHINE)]["line_id"]

    def test_it_needs_a_session_like_everything_else(self, client: TestClient) -> None:
        assert client.get("/machines").status_code == 401

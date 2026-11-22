"""What the technician's job page reads besides the steps (ADR-134).

The redesigned job page puts the station's name on its sign, the line's lamps
beside it, the reading behind the ticket, the last jobs on the same machine,
who approved the steps, and "step 2 of 6" with a button that resumes there.
Each comes from a record the system already keeps; these tests pin where.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import (
    ComponentLabel,
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
from tests.released import released

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
TECHNICIAN = UserId("tech-1")
OTHER = UserId("tech-2")
ENGINEER = UserId("eng-1")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def world(database_url: str, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A forecast on MC-012 with a two-step playbook, and a reported job on the
    same machine for the history."""
    clock = SimulatedClock(NOW)
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, chunk, document_page, document, "
            "playbook, playbook_proposal, access_log, session, account CASCADE"
        )
        for user, name, role in [
            (TECHNICIAN, "Somchai", Role.TECHNICIAN),
            (OTHER, "Malee", Role.TECHNICIAN),
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
        playbook = Playbook(
            symptom_code=SymptomCode("SYM-014"),
            machine_model=R2000,
            steps=(
                PlaybookStep(text="Isolate the cell.", source_doc=manual, page=2, confidence=0.9),
                PlaybookStep(
                    text="Remove the belt guard.", source_doc=manual, page=4, confidence=0.9
                ),
            ),
            estimated_minutes=45,
            required_skill=SkillId("robot_mechanical"),
            required_technicians=1,
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
        finding = Finding(
            machine_id=MOTOR,
            component=ComponentLabel("belt_motor"),
            symptom_code=SymptomCode("SYM-014"),
            severity=Severity.HIGH,
            rule_id=RuleId("R-motor-temp-high/trend"),
            detected_at=NOW,
            evidence={
                "slope_per_hour": 1.4,
                "threshold": 85.0,
                "comparison": "above",
                "metric_name": "motor_temp_c",
                "value": 78.0,
                "unit": "degC",
                "measured_at": NOW.isoformat(),
            },
            kind=FindingKind.PREDICTED,
            eta=NOW + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
        )
        predicted = orders.from_finding(
            conn, finding, finding_ref=findings.raise_finding(conn, finding), machine_model=R2000
        ).ref
        reported = orders.from_report(
            conn,
            machine_id=MOTOR,
            machine_model=R2000,
            severity=Severity.MEDIUM,
            reported_by=ENGINEER,
            description="fan cover rattling",
            distinct_from=[predicted],
        ).ref
        released(conn, predicted)
        released(conn, reported)
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    app = create_app(
        pool=pool, library=DocumentLibrary(FilesystemObjectStore(tmp_path), clock), clock=clock
    )
    try:
        with TestClient(app) as client:
            yield {"client": client, "clock": clock, "predicted": predicted, "reported": reported}
    finally:
        pool.close()


def _as(client: TestClient, user: UserId) -> TestClient:
    client.cookies.clear()
    response = client.post("/sessions", json={"user": str(user), "password": PASSWORD})
    assert response.status_code == 201, response.text
    return client


def _ticket(client: TestClient, ref: str) -> dict[str, Any]:
    response = client.get(f"/work-orders/{ref}")
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestTheTicketCarriesItsEvidence:
    def test_the_reading_behind_a_forecast(self, world: dict[str, Any]) -> None:
        body = _ticket(_as(world["client"], TECHNICIAN), world["predicted"])
        assert body["reading"] == {
            "metric_name": "motor_temp_c",
            "metric_title": "อุณหภูมิมอเตอร์",
            "unit": "degC",
            "value": 78.0,
            "measured_at": "2026-03-03T08:00:00Z",
            "threshold": 85.0,
            "comparison": "above",
            "slope_per_hour": 1.4,
        }

    def test_a_reported_job_has_no_reading(self, world: dict[str, Any]) -> None:
        body = _ticket(_as(world["client"], TECHNICIAN), world["reported"])
        assert body["reading"] is None

    def test_the_station_by_the_name_the_floor_uses(self, world: dict[str, Any]) -> None:
        body = _ticket(_as(world["client"], TECHNICIAN), world["predicted"])
        assert body["station"] == "สถานี 3"
        assert body["station_name"] == "ติดตั้งหลังคา"
        assert body["machine_model"] == "R-2000iC"

    def test_who_approved_the_steps_and_whom_to_ask(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        body = _ticket(client, world["predicted"])
        approval = body["approval"]
        assert datetime.fromisoformat(approval.pop("approved_at")) == NOW
        assert approval == {
            "approved_by": "Pranee",
            "revision": 1,
            "manual": "R-2000iC Maintenance Manual",
        }
        # The reported job has no steps; the engineer to ask is the one who
        # approves this model's playbooks.
        reported = _ticket(client, world["reported"])
        assert reported["approval"] is None
        assert reported["engineer"] == "Pranee"


class TestStepReached:
    def test_moving_on_is_kept_and_the_ticket_resumes_there(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        ref = world["predicted"]
        assert client.post(f"/work-orders/{ref}/accept").status_code == 200
        assert client.post(f"/work-orders/{ref}/start").status_code == 200
        assert _ticket(client, ref)["step_reached"] is None

        moved = client.post(f"/work-orders/{ref}/progress", json={"step": 2})
        assert moved.status_code == 200, moved.text
        body = _ticket(client, ref)
        assert body["step_reached"] == 2
        assert datetime.fromisoformat(body["started_at"]) == NOW
        # Back a step is a move like any other: the page resumes where they are.
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 1}).status_code == 200
        assert _ticket(client, ref)["step_reached"] == 1

    def test_a_step_the_order_does_not_have_is_refused(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        ref = world["predicted"]
        client.post(f"/work-orders/{ref}/accept")
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 3}).status_code == 422
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 0}).status_code == 422

    def test_somebody_not_on_the_job_cannot_move_it(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        client.post(f"/work-orders/{world['predicted']}/accept")
        other = _as(world["client"], OTHER)
        response = other.post(f"/work-orders/{world['predicted']}/progress", json={"step": 2})
        assert response.status_code == 409


class TestTheLastJobsOnThisMachine:
    def test_a_closed_job_is_the_next_ones_history(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        ref = world["reported"]
        client.post(f"/work-orders/{ref}/accept")
        client.post(f"/work-orders/{ref}/start")
        world["clock"].advance(timedelta(minutes=40))
        closed = client.post(
            f"/work-orders/{ref}/close",
            json={"outcome": "fixed", "technician_feedback": "two cover screws were loose"},
        )
        assert closed.status_code == 200, closed.text

        history = _ticket(client, world["predicted"])["history"]
        assert [one["ref"] for one in history] == [ref]
        assert history[0]["minutes"] == 40
        assert history[0]["by"] == ["Somchai"]
        assert history[0]["outcome"] == "fixed"
        assert history[0]["note"] == "two cover screws were loose"
        # A job is not its own history.
        assert _ticket(client, ref)["history"] == []


class TestTheLineLamps:
    def test_a_technician_reads_the_lamps_and_nothing_else(self, world: dict[str, Any]) -> None:
        client = _as(world["client"], TECHNICIAN)
        response = client.get("/line/lamps")
        assert response.status_code == 200, response.text
        (line,) = response.json()["lines"]
        assert [lamp["seq"] for lamp in line] == [1, 2, 3, 4]
        assert line[2] == {"seq": 3, "name": "ติดตั้งหลังคา", "state": "predicted"}
        assert {lamp["state"] for lamp in (line[0], line[1], line[3])} == {"normal"}
        # The lead's view stays the lead's.
        assert client.get("/overview/line").status_code == 403

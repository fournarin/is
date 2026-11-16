"""Isolation point by point, over HTTP (ADR-135, REQ-H-04, REQ-H-06).

The endpoint refuses, not only the button: a job cannot move past an isolation
step until each point is off and locked, past a waiting hazard until its time is
up, or past a verify step until zero energy is confirmed. A lock goes into the
register with its owner and comes off only by that owner. Closing or handing
over says what is still locked, and the answer has to agree with the register.
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
    IsolationPoint,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    RuleId,
    Severity,
    SkillId,
    StepKind,
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
from pdm.work import WorkOrders, locks
from tests.released import released

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
TECHNICIAN = UserId("tech-1")
OTHER = UserId("tech-2")
ENGINEER = UserId("eng-1")
PASSWORD = "correct horse battery staple"
CP3 = IsolationPoint(point_id="CP-3", label="เบรกเกอร์ CP-3", energy="electrical")
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
                PlaybookStep(
                    text="Press the emergency stop.", source_doc=manual, page=2, confidence=0.9
                ),
                PlaybookStep(
                    text="Open breaker CP-3 and apply a personal lock.",
                    source_doc=manual,
                    page=2,
                    confidence=0.9,
                    kind=StepKind.ISOLATION,
                    hazards=("W012",),
                    isolation_points=(CP3,),
                ),
                PlaybookStep(
                    text="Wait 5 minutes for the DC bus to discharge.",
                    source_doc=manual,
                    page=2,
                    confidence=0.9,
                    kind=StepKind.HAZARD,
                    hazards=("W012",),
                    wait_minutes=5,
                ),
                PlaybookStep(
                    text="Verify zero energy at CP-3.",
                    source_doc=manual,
                    page=2,
                    confidence=0.9,
                    kind=StepKind.VERIFY,
                    isolation_points=(CP3,),
                ),
                PlaybookStep(
                    text="Remove your lock and run the axis.",
                    source_doc=manual,
                    page=4,
                    confidence=0.9,
                    kind=StepKind.RESTORE,
                    isolation_points=(CP3,),
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


def _working(world: dict[str, Any]) -> TestClient:
    client = _as(world["client"], TECHNICIAN)
    ref = world["predicted"]
    assert client.post(f"/work-orders/{ref}/accept").status_code == 200
    assert client.post(f"/work-orders/{ref}/start").status_code == 200
    return client


def _confirm(client: TestClient, ref: str, step: int, item: str, **body: str) -> Any:
    return client.post(f"/work-orders/{ref}/steps/{step}/confirm", json={"item": item, **body})


def _lock_cp3(client: TestClient, ref: str) -> None:
    assert _confirm(client, ref, 2, "off", point_id="CP-3").status_code == 200
    locked = _confirm(client, ref, 2, "locked", point_id="CP-3", lock_no="ก-03")
    assert locked.status_code == 200, locked.text


class TestTheJobWaitsForEachPoint:
    def test_the_step_after_an_isolation_is_refused_until_it_is_locked(
        self, world: dict[str, Any]
    ) -> None:
        client, ref = _working(world), world["predicted"]
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 2}).status_code == 200
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 3}).status_code == 409
        _lock_cp3(client, ref)
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 3}).status_code == 200

    def test_points_are_confirmed_in_order(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        out_of_order = _confirm(client, ref, 2, "locked", point_id="CP-3", lock_no="ก-03")
        assert out_of_order.status_code == 409, out_of_order.text
        assert "CP-3" in out_of_order.json()["detail"]

    def test_each_confirmation_is_recorded_with_who_and_when(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        body = _ticket(client, ref)
        assert [
            (one["step"], one["point_id"], one["item"], one["by"]) for one in body["confirmations"]
        ] == [
            (2, "CP-3", "off", "tech-1"),
            (2, "CP-3", "locked", "tech-1"),
        ]
        (on,) = body["locks"]
        assert (on["point_id"], on["lock_no"], on["owner_name"], on["step"]) == (
            "CP-3",
            "ก-03",
            "Somchai",
            2,
        )
        assert body["your_lock_numbers"] == ["ก-03"]
        assert body["steps"][1]["kind"] == "isolation"
        assert body["steps"][1]["isolation_points"][0]["point_id"] == "CP-3"
        assert body["missing_verify"] is False

    def test_a_wait_holds_the_job_until_its_time_is_up(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 3}).status_code == 200
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 4}).status_code == 409
        world["clock"].advance(timedelta(minutes=5))
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 4}).status_code == 200

    def test_verify_before_working_on_it(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        client.post(f"/work-orders/{ref}/progress", json={"step": 3})
        world["clock"].advance(timedelta(minutes=5))
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 5}).status_code == 409
        assert _confirm(client, ref, 4, "verified", point_id="CP-3").status_code == 200
        assert client.post(f"/work-orders/{ref}/progress", json={"step": 5}).status_code == 200


class TestTheRegister:
    def test_a_lock_number_is_on_one_point_at_a_time(self, world: dict[str, Any]) -> None:
        """The database's rule, not the screen's: the same personal lock cannot
        hang on two points at once."""
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        with connect(os.environ["DATABASE_URL"]) as conn:
            again = locks.apply_lock(
                conn,
                work_order_ref=ref,
                machine_id=MOTOR,
                point_id="V-7",
                lock_no="ก-03",
                owner=TECHNICIAN,
                step=2,
                now=NOW,
            )
        assert again is False

    def test_only_the_owner_takes_a_lock_off(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        released = _confirm(client, ref, 5, "released", point_id="CP-3")
        assert released.status_code == 200, released.text
        assert _ticket(client, ref)["locks"] == []


class TestClosingSaysWhatIsLocked:
    def test_released_is_refused_while_my_lock_is_on(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        refused = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert refused.status_code == 409
        assert "ก-03" in refused.json()["detail"]
        assert (
            client.post(f"/work-orders/{ref}/close", json={"outcome": "fixed"}).status_code == 409
        )

    def test_still_locked_closes_with_the_line_on_top_of_the_note(
        self, world: dict[str, Any]
    ) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        closed = client.post(
            f"/work-orders/{ref}/close",
            json={
                "outcome": "temporary_fix",
                "lock_state": "still_locked",
                "lock_reason": "รออะไหล่",
                "technician_feedback": "สั่งพัดลมแล้ว",
            },
        )
        assert closed.status_code == 200, closed.text
        history = _ticket(client, world["reported"])["history"]
        assert history[0]["note"] == "สถานะกุญแจ: ยังล็อกอยู่ ก-03 ที่ CP-3 · เหตุ: รออะไหล่\nสั่งพัดลมแล้ว"
        # The lock is still on the machine for the next person to see.
        assert [one["lock_no"] for one in _ticket(client, world["reported"])["locks"]] == ["ก-03"]

    def test_not_isolated_is_refused_while_a_lock_is_on(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        refused = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "not_isolated"}
        )
        assert refused.status_code == 409

    def test_a_handover_keeps_the_lock_and_says_so(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        refused = client.post(
            f"/work-orders/{ref}/handover", json={"note": "ถึงขั้น 2", "lock_state": "released"}
        )
        assert refused.status_code == 409
        handed = client.post(
            f"/work-orders/{ref}/handover",
            json={"note": "ถึงขั้น 2", "lock_state": "still_locked", "lock_reason": "หมดกะ"},
        )
        assert handed.status_code == 200, handed.text
        assert handed.json()["handover_note"].startswith("สถานะกุญแจ: ยังล็อกอยู่ ก-03 ที่ CP-3")

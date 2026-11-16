"""Isolation point by point, over HTTP (ADR-135, ADR-136, REQ-H-04, REQ-H-06).

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
    Assignee,
    AssigneeRole,
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
    WorkOrderStatus,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import repo as playbooks
from pdm.triggers import repo as findings
from pdm.work import WorkOrders, locks
from pdm.work import repo as work_repo
from tests.released import released

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
TECHNICIAN = UserId("tech-1")
OTHER = UserId("tech-2")
ENGINEER = UserId("eng-1")
LEAD = UserId("sup-1")
AXIS = MachineId("MC-004")
PASSWORD = "correct horse battery staple"
CP3 = IsolationPoint(point_id="CP-3", label="เบรกเกอร์ CP-3", energy="electrical")
V7 = IsolationPoint(point_id="V-7", label="วาล์วลม V-7", energy="pneumatic")
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
            (LEAD, "Anan", Role.SUPERVISOR),
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
                    text="Remove your lock.",
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
        # A job on another machine whose restore step has two points (N4).
        two = (CP3, V7)
        playbooks.save_approved(
            conn,
            playbook.model_copy(
                update={
                    "symptom_code": SymptomCode("SYM-021"),
                    "steps": (
                        PlaybookStep(
                            text="Isolate.",
                            source_doc=manual,
                            page=2,
                            confidence=0.9,
                            kind=StepKind.ISOLATION,
                            isolation_points=two,
                        ),
                        PlaybookStep(
                            text="Verify.",
                            source_doc=manual,
                            page=2,
                            confidence=0.9,
                            kind=StepKind.VERIFY,
                            isolation_points=two,
                        ),
                        PlaybookStep(
                            text="Restore.",
                            source_doc=manual,
                            page=2,
                            confidence=0.9,
                            kind=StepKind.RESTORE,
                            isolation_points=two,
                        ),
                    ),
                }
            ),
            approved_by=ENGINEER,
            approved_at=NOW,
            approver_role=Role.ENGINEER,
        )
        axis_finding = Finding(
            machine_id=AXIS,
            component=ComponentLabel("servo_axis_1"),
            symptom_code=SymptomCode("SYM-021"),
            severity=Severity.MEDIUM,
            rule_id=RuleId("R-servo-current-high"),
            detected_at=NOW,
            evidence={},
            kind=FindingKind.DETECTED,
        )
        two_points = orders.from_finding(
            conn,
            axis_finding,
            finding_ref=findings.raise_finding(conn, axis_finding),
            machine_model=R2000,
        ).ref
        released(conn, two_points)
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
            yield {
                "client": client,
                "clock": clock,
                "predicted": predicted,
                "reported": reported,
                "two_points": two_points,
            }
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


CHECKS = ("tools_removed", "guards_back", "people_clear", "operator_told")


def _db(world: dict[str, Any]) -> Any:
    return connect(os.environ["DATABASE_URL"], autocommit=True)


def _working(world: dict[str, Any], user: UserId = TECHNICIAN) -> TestClient:
    client = _as(world["client"], user)
    ref = world["predicted"]
    assert client.post(f"/work-orders/{ref}/accept").status_code == 200
    assert client.post(f"/work-orders/{ref}/start").status_code == 200
    return client


def _also_on_it(world: dict[str, Any], user: UserId) -> TestClient:
    """A second technician put on the same job, as a lead would."""
    with _db(world) as conn:
        work_repo.add_assignee(
            conn, world["predicted"], Assignee(user=user, role=AssigneeRole.HELPER)
        )
    client = _as(world["client"], user)
    assert client.post(f"/work-orders/{world['predicted']}/start").status_code == 200
    return client


def _confirm(client: TestClient, ref: str, step: int, item: str, **body: str) -> Any:
    return client.post(f"/work-orders/{ref}/steps/{step}/confirm", json={"item": item, **body})


def _go(client: TestClient, ref: str, step: int) -> int:
    return int(client.post(f"/work-orders/{ref}/progress", json={"step": step}).status_code)


def _lock_cp3(client: TestClient, ref: str, number: str = "ก-03") -> None:
    assert _go(client, ref, 2) == 200
    off = _confirm(client, ref, 2, "off", point_id="CP-3")
    assert off.status_code == 200, off.text
    locked = _confirm(client, ref, 2, "locked", point_id="CP-3", lock_no=number)
    assert locked.status_code == 200, locked.text


def _to_restore(client: TestClient, world: dict[str, Any]) -> None:
    """Locked, waited, verified, at the restore step."""
    ref = world["predicted"]
    _lock_cp3(client, ref)
    assert _go(client, ref, 3) == 200
    world["clock"].advance(timedelta(minutes=5))
    assert _go(client, ref, 4) == 200
    assert _confirm(client, ref, 4, "verified", point_id="CP-3").status_code == 200
    assert _go(client, ref, 5) == 200


def _release(client: TestClient, lock_id: int, reason: str = "คนรับใส่แล้ว", **witness: str) -> Any:
    """The owner takes their lock off outside the restore step, with the shift lead signing."""
    body = {"reason": reason, "witness": str(LEAD), "witness_password": PASSWORD, **witness}
    return client.post(f"/locks/{lock_id}/release", json=body)


def _my_lock_id(client: TestClient) -> int:
    (one,) = client.get("/locks/mine").json()
    return int(one["lock_id"])


class TestTheJobWaitsForEachPoint:
    def test_the_step_after_an_isolation_is_refused_until_it_is_locked(
        self, world: dict[str, Any]
    ) -> None:
        client, ref = _working(world), world["predicted"]
        assert _go(client, ref, 2) == 200
        assert _go(client, ref, 3) == 409
        _lock_cp3(client, ref)
        assert _go(client, ref, 3) == 200

    def test_points_are_confirmed_in_order(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        assert _go(client, ref, 2) == 200
        out_of_order = _confirm(client, ref, 2, "locked", point_id="CP-3", lock_no="ก-03")
        assert out_of_order.status_code == 409, out_of_order.text
        assert "CP-3" in out_of_order.json()["detail"]

    def test_each_confirmation_is_recorded_with_who_and_when(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        body = _ticket(client, ref)
        assert [
            (one["step"], one["point_id"], one["item"], one["by"]) for one in body["confirmations"]
        ] == [(2, "CP-3", "off", "tech-1"), (2, "CP-3", "locked", "tech-1")]
        (on,) = body["locks"]
        assert (on["point_id"], on["lock_no"], on["owner_name"], on["step"]) == (
            "CP-3",
            "ก-03",
            "Somchai",
            2,
        )
        assert body["your_lock_numbers"] == ["ก-03"]
        assert [one["key"] for one in body["restore_checks"]] == list(CHECKS)
        assert body["missing_verify"] is False

    def test_a_wait_holds_the_job_until_its_time_is_up(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        assert _go(client, ref, 3) == 200
        assert _go(client, ref, 4) == 409
        world["clock"].advance(timedelta(minutes=5))
        assert _go(client, ref, 4) == 200


class TestNothingIsConfirmedAhead:
    """B1: a confirmation belongs to a step the job has reached, after everything before it."""

    def test_a_step_not_reached_is_refused(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        assert _confirm(client, ref, 2, "off", point_id="CP-3").status_code == 409
        assert _confirm(client, ref, 4, "verified", point_id="CP-3").status_code == 409

    def test_the_lock_cannot_come_off_at_the_isolation_step(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        assert _confirm(client, ref, 5, "released", point_id="CP-3").status_code == 409
        assert len(_ticket(client, ref)["locks"]) == 1

    def test_a_wait_cannot_be_started_early(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        assert _confirm(client, ref, 3, "wait_started").status_code == 409

    def test_your_own_lock_on_a_job_you_hold_comes_off_only_in_the_restore_step(
        self, world: dict[str, Any]
    ) -> None:
        """N1: taking it off from "my locks" and then closing as "back to production"
        skipped tools, guards, people and operator. Refused, even witnessed."""
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        refused = _release(client, _my_lock_id(client), "เสร็จแล้ว")
        assert refused.status_code == 409, refused.text
        assert "ขั้นคืนพลังงาน" in refused.json()["detail"]
        assert len(_ticket(client, ref)["locks"]) == 1
        closed = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert closed.status_code == 409


class TestEveryoneHangsTheirOwnLock:
    """B4, group lockout (1910.147(f)(3))."""

    def test_a_second_technician_locks_for_themselves(self, world: dict[str, Any]) -> None:
        first = _working(world)
        ref = world["predicted"]
        _lock_cp3(first, ref)
        second = _also_on_it(world, OTHER)
        assert _go(second, ref, 3) == 409, "the first person's lock does not cover the second"
        mine = _confirm(second, ref, 2, "locked", point_id="CP-3", lock_no="ก-09")
        assert mine.status_code == 200, mine.text
        assert sorted(one["lock_no"] for one in _ticket(second, ref)["locks"]) == ["ก-03", "ก-09"]

    def test_nobody_takes_off_another_persons_lock(self, world: dict[str, Any]) -> None:
        first = _working(world)
        ref = world["predicted"]
        _to_restore(first, world)
        for key in CHECKS:
            assert _confirm(first, ref, 5, "checked", point_id=key).status_code == 200
        theirs = _my_lock_id(first)
        # The clients share one session jar: from here every request is the second person's.
        second = _also_on_it(world, OTHER)
        assert _release(second, theirs, "x").status_code == 409
        assert _confirm(second, ref, 5, "released", point_id="CP-3").status_code == 409
        assert [one["lock_no"] for one in _ticket(second, ref)["locks"]] == ["ก-03"]

    def test_the_receiver_of_a_handover_locks_for_themselves(self, world: dict[str, Any]) -> None:
        first = _working(world)
        ref = world["predicted"]
        _lock_cp3(first, ref)
        handed = first.post(
            f"/work-orders/{ref}/handover",
            json={"note": "ถึงขั้น 2", "lock_state": "still_locked", "lock_reason": "หมดกะ"},
        )
        assert handed.status_code == 200, handed.text
        with _db(world) as conn:
            work_repo.add_assignee(conn, ref, Assignee(user=OTHER, role=AssigneeRole.PRIMARY))
            work_repo.set_status(conn, ref, status=WorkOrderStatus.ASSIGNED)
        second = _as(world["client"], OTHER)
        assert second.post(f"/work-orders/{ref}/start").status_code == 200
        # N2: the sender cannot take theirs off before the receiver's is on - no gap.
        sender = _as(world["client"], TECHNICIAN)
        early = _release(sender, _my_lock_id(sender))
        assert early.status_code == 409, early.text
        assert "คนรับงาน" in early.json()["detail"]
        second = _as(world["client"], OTHER)
        assert _go(second, ref, 3) == 409
        assert (
            _confirm(second, ref, 2, "locked", point_id="CP-3", lock_no="ก-09").status_code == 200
        )
        assert _go(second, ref, 3) == 200
        # Only then does the first person take theirs off, from their own list.
        first = _as(world["client"], TECHNICIAN)
        lock_id = _my_lock_id(first)
        assert _release(first, lock_id).status_code == 200
        assert [one["lock_no"] for one in _ticket(first, ref)["locks"]] == ["ก-09"]


class TestRestoring:
    def test_the_plants_checks_come_before_the_lock_comes_off(self, world: dict[str, Any]) -> None:
        """B5."""
        client, ref = _working(world), world["predicted"]
        _to_restore(client, world)
        early = _confirm(client, ref, 5, "released", point_id="CP-3")
        assert early.status_code == 409
        for key in CHECKS:
            assert _confirm(client, ref, 5, "checked", point_id=key).status_code == 200
        released = _confirm(client, ref, 5, "released", point_id="CP-3")
        assert released.status_code == 200, released.text
        assert _ticket(client, ref)["locks"] == []

    def test_only_the_owner_takes_a_lock_off(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _to_restore(client, world)
        for key in CHECKS:
            _confirm(client, ref, 5, "checked", point_id=key)
        assert _confirm(client, ref, 5, "released", point_id="CP-3").status_code == 200
        assert _ticket(client, ref)["locks"] == []

    def test_a_lock_number_is_on_one_point_at_a_time(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _lock_cp3(client, ref)
        with _db(world) as conn:
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

    def test_whoever_took_over_must_answer_while_anybodys_lock_is_on(
        self, world: dict[str, Any]
    ) -> None:
        """Red line 3: the second person has no lock of their own on and still may
        not close without saying what is locked."""
        first = _working(world)
        ref = world["predicted"]
        _lock_cp3(first, ref)
        second = _also_on_it(world, OTHER)
        assert (
            second.post(f"/work-orders/{ref}/close", json={"outcome": "fixed"}).status_code == 409
        )
        released = second.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert released.status_code == 409
        handed = second.post(f"/work-orders/{ref}/handover", json={"note": "ถึงขั้น 2"})
        assert handed.status_code == 409

    def test_released_is_refused_while_another_jobs_lock_is_on_the_machine(
        self, world: dict[str, Any]
    ) -> None:
        """B2: two work orders on one machine."""
        client, ref = _working(world), world["predicted"]
        _to_restore(client, world)
        with _db(world) as conn:
            assert locks.apply_lock(
                conn,
                work_order_ref=world["reported"],
                machine_id=MOTOR,
                point_id="CP-3",
                lock_no="ก-77",
                owner=OTHER,
                step=1,
                now=NOW,
            )
        for key in CHECKS:
            _confirm(client, ref, 5, "checked", point_id=key)
        assert _confirm(client, ref, 5, "released", point_id="CP-3").status_code == 200
        refused = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert refused.status_code == 409
        assert "ก-77" in refused.json()["detail"]
        # N3: still locked and not isolated are untrue too - this answer is the true one.
        for untrue in ("still_locked", "not_isolated"):
            body = {"outcome": "fixed", "lock_state": untrue}
            assert client.post(f"/work-orders/{ref}/close", json=body).status_code == 409
        assert (
            client.post(f"/work-orders/{ref}/close", json={"outcome": "fixed"}).status_code == 409
        )
        closed = client.post(
            f"/work-orders/{ref}/close",
            json={"outcome": "fixed", "lock_state": "released_machine_locked"},
        )
        assert closed.status_code == 200, closed.text

    def test_not_isolated_is_refused_after_a_release(self, world: dict[str, Any]) -> None:
        client, ref = _working(world), world["predicted"]
        _to_restore(client, world)
        for key in CHECKS:
            _confirm(client, ref, 5, "checked", point_id=key)
        _confirm(client, ref, 5, "released", point_id="CP-3")
        refused = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "not_isolated"}
        )
        assert refused.status_code == 409
        closed = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert closed.status_code == 200, closed.text

    def test_still_locked_closes_and_the_owner_takes_it_off_later(
        self, world: dict[str, Any]
    ) -> None:
        """B3: a lock left on at close is still its owner's to record coming off."""
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
        assert [one["lock_no"] for one in _ticket(client, world["reported"])["locks"]] == ["ก-03"]
        lock_id = _my_lock_id(client)
        assert _release(client, lock_id, " ").status_code == 422, "a reason is required"
        unwitnessed = client.post(f"/locks/{lock_id}/release", json={"reason": "ได้อะไหล่"})
        assert unwitnessed.status_code == 422, "and a witness"
        wrong = _release(client, lock_id, "ได้อะไหล่", witness_password="not it")
        assert wrong.status_code == 403
        not_a_lead = _release(client, lock_id, "ได้อะไหล่", witness=str(OTHER))
        assert not_a_lead.status_code == 403, "a technician cannot witness"
        off = _release(client, lock_id, "ได้อะไหล่ ปิดเครื่องเรียบร้อย")
        assert off.status_code == 200, off.text
        with _db(world) as conn:
            row = conn.execute(
                "SELECT release_reason, release_witness FROM lock_record WHERE lock_id = %s",
                (lock_id,),
            ).fetchone()
        assert row == ("ได้อะไหล่ ปิดเครื่องเรียบร้อย", "sup-1")
        assert client.get("/locks/mine").json() == []
        assert _ticket(client, world["reported"])["locks"] == []

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


class TestARestoreStepWithTwoPoints:
    def test_both_locks_come_off_in_one_restore_step(self, world: dict[str, Any]) -> None:
        """N4: the second release was refused because the isolation step behind it
        asked for the first lock again."""
        client = _as(world["client"], TECHNICIAN)
        ref = world["two_points"]
        assert client.post(f"/work-orders/{ref}/accept").status_code == 200
        assert client.post(f"/work-orders/{ref}/start").status_code == 200
        for point, number in (("CP-3", "ก-03"), ("V-7", "ก-04")):
            assert _confirm(client, ref, 1, "off", point_id=point).status_code == 200
            assert (
                _confirm(client, ref, 1, "locked", point_id=point, lock_no=number).status_code
                == 200
            )
        assert _go(client, ref, 2) == 200
        for point in ("CP-3", "V-7"):
            assert _confirm(client, ref, 2, "verified", point_id=point).status_code == 200
        assert _go(client, ref, 3) == 200
        for key in CHECKS:
            assert _confirm(client, ref, 3, "checked", point_id=key).status_code == 200
        for point in ("CP-3", "V-7"):
            released = _confirm(client, ref, 3, "released", point_id=point)
            assert released.status_code == 200, released.text
        assert _ticket(client, ref)["locks"] == []
        closed = client.post(
            f"/work-orders/{ref}/close", json={"outcome": "fixed", "lock_state": "released"}
        )
        assert closed.status_code == 200, closed.text

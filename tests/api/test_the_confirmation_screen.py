"""The press the advisor asked for, through HTTP (ADR-071, #81).

`tests/dispatch/test_the_confirmation_gate.py` covers the flow against the
database. This file covers the three things that only exist at this seam:

  * **who may press it.** ADR-024 makes the shift lead the person who answers
    for what the shift is sent to do, and invariant 6 says the endpoint refuses
    rather than the button being hidden.
  * **what leaves the system, and when.** The delivery row is queued by the
    confirmation's own transaction and by nothing else (ADR-071 §5). A ticket
    reaching a destination before anybody approved it is the one failure this
    whole step exists to prevent.
  * **`/work-orders/mine` is not a work order called "mine".** Starlette matches
    in definition order, and behind `/work-orders/{work_order_ref}` the
    technician's queue would be a 404 for ever.
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
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import (
    MachineId,
    MachineModel,
    Role,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.service import DispatchRounds
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)  # 15:00 in Bangkok: the afternoon shift
AFTERNOON = ShiftId("afternoon")
BOTTLENECK = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
TECH = UserId("tech-1")
PEOPLE = {
    Role.TECHNICIAN: (TECH, "Somchai"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
    Role.ENGINEER: (UserId("eng-1"), "Pim"),
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
def world(database_url: str, clock: SimulatedClock) -> Iterator[dict[str, Any]]:
    """One shift, one technician, one reported fault - and a round that has run.

    The round is run here rather than in each test because it is the precondition
    for every one of them: the shipped configuration is `confirmation:
    supervisor`, so what exists after a round is a question, not a job.
    """
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, dispatch_proposal, ticket_delivery, work_order_override, "
            "finding, job, shift_assignment, technician, access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        dispatch_repo.add_technician(
            conn,
            Technician(user=TECH, skills=frozenset({SkillId("robot_mechanical")})),
            known_skills={SkillId("robot_mechanical")},
            now=NOW,
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=AFTERNOON,
                on_date=NOW.date(),
                technician=TECH,
                available_minutes=480,
            ),
        )
        ref = orders.from_report(
            conn,
            machine_id=BOTTLENECK,
            machine_model=R2000,
            severity=Severity.HIGH,
            reported_by=UserId("sup-1"),
            description="grinding noise",
        ).ref
        report = DispatchRounds(clock, CONFIG).run(conn)
        assert report.proposed == (ref,), "the fixture must leave one question open"
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "clock": clock, "ref": ref}
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


def _deliveries(database_url: str) -> list[dict[str, Any]]:
    with connect(database_url) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM ticket_delivery ORDER BY work_order_ref")
        return [dict(row) for row in cur.fetchall()]


class TestWhatIsWaitingToBeDecided:
    def test_the_proposal_carries_the_round_it_was_decided_against(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """Not the round in front of the reader. A supervisor answering "should
        this go out" is answering about the shift the scheduler saw."""
        _signed_in(client, Role.SUPERVISOR)

        (waiting,) = client.get("/dispatch/proposals").json()

        assert waiting["ref"] == world["ref"]
        assert waiting["assignees"] == [str(TECH)]
        assert waiting["priority_reason"] != ""
        assert waiting["band"] is not None
        assert waiting["expires_at"] > waiting["proposed_at"]

    def test_a_technician_may_read_it(self, client: TestClient) -> None:
        """ADR-005's reason: a technician who can see their next job is waiting
        on an approval knows something different from one whose screen is empty."""
        _signed_in(client, Role.TECHNICIAN)

        assert client.get("/dispatch/proposals").status_code == 200

    def test_only_a_supervisor_may_answer_it(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)

        refused = client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        assert refused.status_code == 403


class TestConfirming:
    def test_it_becomes_the_technicians_job_and_leaves_the_list(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)

        answered = client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        assert answered.status_code == 201, answered.text
        assert answered.json()["state"] == "confirmed"
        assert client.get("/dispatch/proposals").json() == []
        assert client.get(f"/work-orders/{world['ref']}").json()["status"] == "assigned"

    def test_the_ticket_is_queued_to_leave_only_once_it_is_confirmed(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """ADR-068 wrote the delivery row beside the placement so that a ticket
        could never be somebody's job without something knowing it had to go out.
        With a person in the middle, this request is the one that makes it
        somebody's job (ADR-071 §5)."""
        _signed_in(client, Role.SUPERVISOR)
        assert _deliveries(database_url) == []

        client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        (queued,) = _deliveries(database_url)
        assert queued["work_order_ref"] == world["ref"]
        assert queued["state"] == "pending"

    def test_the_second_press_is_told_rather_than_recorded_twice(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)
        client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        again = client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        assert again.status_code == 404
        assert world["ref"] in again.json()["detail"]

    def test_confirming_something_nobody_proposed_is_a_404(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        answered = client.post("/dispatch/proposals/WO-nothing/confirm")

        assert answered.status_code == 404


class TestRejecting:
    def test_it_goes_back_into_the_queue_and_nothing_leaves(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)

        answered = client.post(
            f"/dispatch/proposals/{world['ref']}/reject",
            json={"reason": "somchai is already at the press"},
        )

        assert answered.status_code == 201, answered.text
        assert client.get(f"/work-orders/{world['ref']}").json()["status"] == "queued"
        assert _deliveries(database_url) == []

    def test_rejecting_without_a_reason_is_refused(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """A rejection with no reason is indistinguishable from a misclick when
        somebody reads it back six weeks later (ADR-059)."""
        _signed_in(client, Role.SUPERVISOR)

        for body in ({}, {"reason": ""}, {"reason": "   "}):
            refused = client.post(f"/dispatch/proposals/{world['ref']}/reject", json=body)
            assert refused.status_code == 422, body


class TestTheTechniciansOwnQueue:
    def test_mine_is_not_read_as_a_work_order_reference(self, client: TestClient) -> None:
        """The route ordering, asserted rather than trusted. Behind
        `/work-orders/{work_order_ref}` this would be a 404 for ever, and the
        symptom would be an empty screen rather than an error anybody chases."""
        _signed_in(client, Role.TECHNICIAN)

        mine = client.get("/work-orders/mine")

        assert mine.status_code == 200
        assert isinstance(mine.json(), list)

    def test_it_is_empty_while_the_work_is_only_proposed(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)

        assert client.get("/work-orders/mine").json() == []

    def test_it_holds_the_job_once_it_is_confirmed(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)
        client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        _signed_in(client, Role.TECHNICIAN)
        (mine,) = client.get("/work-orders/mine").json()

        assert mine["ref"] == world["ref"]
        assert mine["status"] == "assigned"
        assert mine["priority_reason"] != ""

    def test_somebody_with_no_work_gets_an_empty_list_rather_than_a_refusal(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """Always the caller's own work and never a parameter, so there is
        nothing to leak and no reason to narrow the route to technicians."""
        _signed_in(client, Role.SUPERVISOR)
        client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        _signed_in(client, Role.ENGINEER)

        assert client.get("/work-orders/mine").json() == []


class TestTheBoard:
    """ADR-093: the shift lead's board names people and shows what they are on."""

    def test_a_proposal_names_who_it_goes_to(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)

        (waiting,) = client.get("/dispatch/proposals").json()

        assert waiting["assignee_names"] == ["Somchai"]

    def test_confirmed_work_is_on_the_board_until_it_closes(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)
        assert client.get("/work-orders/active").json() == []

        client.post(f"/dispatch/proposals/{world['ref']}/confirm")

        (active,) = client.get("/work-orders/active").json()
        assert active["ref"] == world["ref"]
        assert active["status"] == "assigned"
        assert active["assignee_names"] == ["Somchai"]

    def test_a_technician_is_not_shown_the_floor(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)

        assert client.get("/work-orders/active").status_code == 403

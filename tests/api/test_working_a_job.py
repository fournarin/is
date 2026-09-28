"""The four buttons, over HTTP (slice 9.1, ADR-024, ADR-025).

Two rules are checked here rather than only in `tests/work`, because they are
rules about the *endpoint* refusing and not about a button being hidden
(invariant 6):

  * only a technician may accept and close work - ADR-024's table, where an
    engineer who found the URL is refused and recorded rather than refused and
    forgotten;
  * a handover with no note is refused at the schema, so the request never
    reaches the code that would have to decide what an empty note means.
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
from pdm.contracts import MachineId, MachineModel, Role, Severity, UserId
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders
from tests.released import released

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MACHINE = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Nok"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
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
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)

    with connect(database_url) as conn:
        conn.execute("TRUNCATE work_order, access_log, session, account CASCADE")
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)
        ref = orders.from_report(
            conn,
            machine_id=MACHINE,
            machine_model=R2000,
            severity=Severity.HIGH,
            reported_by=UserId("sup-1"),
            description="grinding noise from the drive end",
        ).ref
        released(conn, ref)
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


class TestOneJobEndToEnd:
    def test_accept_start_hand_over_and_close(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """The walk a technician's screen makes, with the durations the segments
        say rather than the clock on the wall."""
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]
        clock: SimulatedClock = world["clock"]

        assert client.post(f"/work-orders/{ref}/accept").status_code == 200
        assert client.post(f"/work-orders/{ref}/start").status_code == 200
        clock.advance(timedelta(minutes=25))
        handed = client.post(
            f"/work-orders/{ref}/handover", json={"note": "cover off, CP-3 locked"}
        )
        assert handed.status_code == 200, handed.text
        assert handed.json()["status"] == "handed_over"

        clock.advance(timedelta(hours=6))
        client.post(f"/work-orders/{ref}/accept")
        client.post(f"/work-orders/{ref}/start")
        clock.advance(timedelta(minutes=15))
        closed = client.post(
            f"/work-orders/{ref}/close",
            json={
                "outcome": "fixed",
                "blocked_minutes": 5,
                "blocked_reason": ["waiting_parts"],
            },
        )

        assert closed.status_code == 200, closed.text
        body = closed.json()
        assert body["status"] == "closed"
        assert body["actual_minutes"] == 40, "twenty-five and fifteen, not six and a half hours"
        assert body["repair_minutes"] == 35

    def test_the_ticket_view_shows_the_work_as_it_happens(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """The status a technician's queue reads is the one the transitions
        wrote, not a second answer computed somewhere else."""
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]

        client.post(f"/work-orders/{ref}/accept")
        client.post(f"/work-orders/{ref}/start")

        ticket = client.get(f"/work-orders/{ref}").json()
        assert ticket["status"] == "in_progress"
        assert ticket["assignees"] == ["tech-1"]


class TestWhatTheEndpointRefuses:
    def test_a_handover_with_no_note_is_refused(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-025. Refused at the schema, so the code below never has to decide
        what an empty note means."""
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]
        client.post(f"/work-orders/{ref}/accept")
        client.post(f"/work-orders/{ref}/start")

        assert client.post(f"/work-orders/{ref}/handover", json={"note": ""}).status_code == 422
        assert client.post(f"/work-orders/{ref}/handover", json={}).status_code == 422
        # Spaces clear min_length and are not a note.
        assert client.post(f"/work-orders/{ref}/handover", json={"note": "  "}).status_code == 422
        assert client.get(f"/work-orders/{ref}").json()["status"] == "in_progress"

    def test_a_close_with_no_outcome_is_refused(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-022: an order that has ended has to say how, and
        `no_problem_found` is the answer the threshold loop needs most."""
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]
        client.post(f"/work-orders/{ref}/accept")

        assert client.post(f"/work-orders/{ref}/close", json={}).status_code == 422
        assert (
            client.post(f"/work-orders/{ref}/close", json={"outcome": "sorted"}).status_code == 422
        )

    def test_no_problem_found_closes_the_job(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]
        client.post(f"/work-orders/{ref}/accept")

        closed = client.post(f"/work-orders/{ref}/close", json={"outcome": "no_problem_found"})

        assert closed.status_code == 200, closed.text
        assert closed.json()["outcome"] == "no_problem_found"

    def test_blocked_minutes_larger_than_the_job_are_refused(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)
        ref = world["ref"]
        client.post(f"/work-orders/{ref}/accept")
        client.post(f"/work-orders/{ref}/start")
        world["clock"].advance(timedelta(minutes=10))

        refused = client.post(
            f"/work-orders/{ref}/close",
            json={"outcome": "fixed", "blocked_minutes": 30, "blocked_reason": ["waiting_parts"]},
        )

        assert refused.status_code == 422
        assert client.get(f"/work-orders/{ref}").json()["status"] == "in_progress"

    def test_starting_a_job_nobody_accepted_is_a_conflict(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)

        assert client.post(f"/work-orders/{world['ref']}/start").status_code == 409

    def test_a_transition_on_a_job_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        assert client.post("/work-orders/WO-999999/accept").status_code == 404


class TestWhoMayWorkAJob:
    def test_only_a_technician_accepts_and_closes(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-024's table, checked at the endpoint. An engineer may approve the
        playbook and may not take the job."""
        _signed_in(client, Role.ENGINEER)
        ref = world["ref"]

        assert client.post(f"/work-orders/{ref}/accept").status_code == 403
        assert client.post(f"/work-orders/{ref}/start").status_code == 403
        assert client.post(f"/work-orders/{ref}/handover", json={"note": "n"}).status_code == 403
        assert (
            client.post(f"/work-orders/{ref}/close", json={"outcome": "fixed"}).status_code == 403
        )

    def test_the_refusal_is_recorded(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """ "Who tried to and could not" is the question asked after an incident,
        and it is the entry a rollback would discard (ADR-019, api/deps.py)."""
        _signed_in(client, Role.SUPERVISOR)
        client.post(f"/work-orders/{world['ref']}/accept")

        with connect(database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM access_log WHERE action = 'accept_work_order'")
            assert cur.fetchone()[0] == 1  # type: ignore[index]

    def test_signing_in_is_required(self, client: TestClient, world: dict[str, Any]) -> None:
        assert client.post(f"/work-orders/{world['ref']}/accept").status_code == 401

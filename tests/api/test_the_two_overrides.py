"""ADR-005 in the other direction: a person overruling layer 3, on the record.

The system explains itself to a person - that is `/dispatch/round` and the
ticket's two reasons - and a person explains themselves to the system when they
overrule it. Two overrides are in the design and until this slice neither had
anywhere to land, which is the failure that cannot be repaired afterwards: a
round is computed when asked and never stored (ADR-050), so an override nobody
wrote down cannot be reconstructed from anything.

The three tests that matter:

  * `TestDisagreement::test_a_disagreement_changes_nothing_about_the_round` - the
    whole argument for the button. A ranking that can be argued down is not a
    ranking, and the value of "I disagree" is the record rather than the effect.
  * `TestRelease::test_a_released_ticket_is_in_the_next_round` - ADR-011's
    sentence running both ways. The gate tells the shift lead what it is
    holding, and the shift lead can answer.
  * `TestRelease::test_releasing_without_a_reason_is_refused` - an override with
    no reason is indistinguishable from a bug when somebody reads it six weeks
    later.
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
    Role,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

# 08:00 UTC is 15:00 in Bangkok: the afternoon shift, filed under the 3rd.
NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
AFTERNOON = ShiftId("afternoon")
BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
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
    """A shift the gate has something to hold on.

    Ninety minutes of technician against two sixty-minute jobs puts the ratio
    over the heavy boundary, so the low-severity ticket is held and the
    high-severity one is released - which is the state a supervisor is looking at
    when they press the button.
    """
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    refs: dict[str, str] = {}

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, work_order_override, finding, job, shift_assignment, "
            "technician, access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        dispatch_repo.add_technician(
            conn,
            Technician(user=UserId("tech-1"), skills=frozenset({SkillId("robot_mechanical")})),
            known_skills={SkillId("robot_mechanical")},
            now=NOW,
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=AFTERNOON,
                on_date=NOW.date(),
                technician=UserId("tech-1"),
                available_minutes=90,
            ),
        )

        refs["urgent"] = orders.from_report(
            conn,
            machine_id=BOTTLENECK,
            machine_model=R2000,
            severity=Severity.HIGH,
            reported_by=UserId("sup-1"),
            description="grinding noise",
        ).ref
        refs["held"] = orders.from_report(
            conn,
            machine_id=BUFFERED,
            machine_model=R2000,
            severity=Severity.LOW,
            reported_by=UserId("sup-1"),
            description="weeping seal",
        ).ref
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "clock": clock, "refs": refs}
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


def _overrides(database_url: str) -> list[dict[str, Any]]:
    from psycopg.rows import dict_row

    with connect(database_url) as conn, conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM work_order_override ORDER BY id")
        return [dict(row) for row in cur.fetchall()]


class TestDisagreement:
    def test_a_disagreement_changes_nothing_about_the_round(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """The point of the endpoint, stated as the thing it must not do.

        Re-ranking on an objection would make the queue negotiable, and a queue
        that can be talked to is one where the easy job reaches the top on the
        shift where that is worst.
        """
        _signed_in(client, Role.TECHNICIAN)
        before = client.get("/dispatch/round").json()

        recorded = client.post(
            f"/work-orders/{world['refs']['urgent']}/disagreement",
            json={"reason": "the fan on MC-018 is worse and it is not on this list"},
        )
        assert recorded.status_code == 201, recorded.text

        after = client.get("/dispatch/round").json()
        # `at` is the only thing allowed to differ, and on a simulated clock it
        # does not: the round is a function of its arguments (invariant 10).
        assert after == before
        assert [one["ref"] for one in after["placed"]] == [one["ref"] for one in before["placed"]]

    def test_the_record_names_who_and_why(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)

        client.post(
            f"/work-orders/{world['refs']['urgent']}/disagreement",
            json={"reason": "  the seal is leaking onto the floor  "},
        )

        rows = _overrides(database_url)
        assert len(rows) == 1
        assert rows[0]["kind"] == "priority_disagreement"
        assert rows[0]["work_order_ref"] == world["refs"]["urgent"]
        assert rows[0]["user_id"] == "tech-1"
        assert rows[0]["role"] == "technician"
        assert rows[0]["reason"] == "the seal is leaking onto the floor"
        assert rows[0]["at"] == NOW
        # A disagreement is about one ticket's rank, not about the shift.
        assert rows[0]["band"] is None

    def test_an_empty_reason_is_refused(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        _signed_in(client, Role.TECHNICIAN)

        for body in ({"reason": ""}, {"reason": "   "}, {}):
            response = client.post(
                f"/work-orders/{world['refs']['urgent']}/disagreement", json=body
            )
            assert response.status_code == 422, response.text
        assert _overrides(database_url) == []

    def test_a_ticket_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        response = client.post("/work-orders/WO-999999/disagreement", json={"reason": "no"})
        assert response.status_code == 404

    def test_signing_in_is_required(self, client: TestClient, world: dict[str, Any]) -> None:
        response = client.post(
            f"/work-orders/{world['refs']['urgent']}/disagreement", json={"reason": "no"}
        )
        assert response.status_code == 401


class TestRelease:
    def test_a_released_ticket_is_in_the_next_round(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """ADR-011 both ways: the gate says what it is holding and the shift lead
        answers. What was held is placed, and the round no longer holds it."""
        _signed_in(client, Role.SUPERVISOR)
        held = world["refs"]["held"]

        before = client.get("/dispatch/round").json()
        assert held in {one["ref"] for one in before["held"]}

        response = client.post(
            f"/dispatch/held/{held}/release",
            json={"reason": "the line is stopping for a die change anyway"},
        )
        assert response.status_code == 201, response.text

        after = client.get("/dispatch/round").json()
        assert held in {one["ref"] for one in after["placed"]}
        assert held not in {one["ref"] for one in after["held"]}

    def test_the_record_reads_back_in_the_context_that_produced_it(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """The round is never stored, so what a reader would need six weeks later
        is copied onto the record: who, when, why, and what the load was."""
        _signed_in(client, Role.SUPERVISOR)

        response = client.post(
            f"/dispatch/held/{world['refs']['held']}/release",
            json={"reason": "the technician is already at that machine"},
        )

        body = response.json()
        assert body["by"] == "sup-1"
        assert body["band"] == "heavy"
        assert body["load_ratio"] >= CONFIG.policy.load.heavy_at_or_above
        assert body["shift_id"] == "afternoon"

        rows = _overrides(database_url)
        assert len(rows) == 1
        assert rows[0]["kind"] == "release_held"
        assert rows[0]["band"] == "heavy"
        assert rows[0]["load_ratio"] == pytest.approx(body["load_ratio"])
        assert rows[0]["on_date"] == NOW.date()
        assert rows[0]["user_id"] == "sup-1"

    def test_releasing_without_a_reason_is_refused(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)
        held = world["refs"]["held"]

        for body in ({"reason": ""}, {"reason": " \n "}, {}):
            response = client.post(f"/dispatch/held/{held}/release", json=body)
            assert response.status_code == 422, response.text

        assert _overrides(database_url) == []
        assert held in {one["ref"] for one in client.get("/dispatch/round").json()["held"]}

    def test_a_technician_may_not_release_work(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """ADR-024's table, checked at the endpoint rather than by hiding a
        button (invariant 6) - and the refusal is in the access log."""
        _signed_in(client, Role.TECHNICIAN)

        response = client.post(
            f"/dispatch/held/{world['refs']['held']}/release", json={"reason": "I want it"}
        )

        assert response.status_code == 403
        assert _overrides(database_url) == []
        with connect(database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT allowed FROM access_log WHERE action = 'release_held_work_order'")
            assert cur.fetchall() == [(False,)]

    def test_releasing_what_the_gate_is_not_holding_is_a_conflict(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """The urgent ticket was released by the round itself. Recording an
        override against it would put a decision in the log that decided
        nothing."""
        _signed_in(client, Role.SUPERVISOR)

        response = client.post(
            f"/dispatch/held/{world['refs']['urgent']}/release", json={"reason": "again"}
        )

        assert response.status_code == 409
        assert _overrides(database_url) == []

    def test_releasing_twice_is_a_conflict_rather_than_a_second_record(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)
        held = world["refs"]["held"]

        first = client.post(f"/dispatch/held/{held}/release", json={"reason": "line is stopping"})
        second = client.post(f"/dispatch/held/{held}/release", json={"reason": "again"})

        assert first.status_code == 201
        assert second.status_code == 409
        assert "ถูกปล่อยไปแล้ว" in second.json()["detail"]
        assert len(_overrides(database_url)) == 1

    def test_a_ticket_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)
        response = client.post("/dispatch/held/WO-999999/release", json={"reason": "no"})
        assert response.status_code == 404

"""The two read paths ADR-005 asks for, over HTTP.

`reason` and `priority_reason` answer different questions asked by different
people (ADR-041), and until this slice the second had no reader at all: a
supervisor whose work did not appear could not tell a system that was holding it
from a system that had lost it.

The three tests that matter:

  * `TestTheGateExplainsItself::test_a_held_ticket_says_so_rather_than_vanishing`
    - the failure this slice exists to prevent, and the one that ends with the
      scheduler being overruled and then abandoned (principle 3).
  * `TestTheTicketExplainsItself::test_a_prediction_reads_differently_from_a_detection`
    - ADR-020. A technician decides differently about a machine that is already
      wrong and one that is not yet, so the two must not read alike.
  * `TestTheGateExplainsItself::test_the_sentence_quotes_quantities_not_scores`
    - ADR-045 §1 says the normalised terms are a within-round comparison and
      must not be presented as magnitudes. This is that rule where a person
      would actually see it broken.
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
    FindingRef,
    MachineId,
    MachineModel,
    Role,
    RuleId,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    SymptomCode,
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
    """One technician on the afternoon shift, and three tickets: two the shift
    can take and one it cannot."""
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    refs: dict[str, str] = {}

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        # Ninety minutes of technician against three sixty-minute jobs: the
        # shift is over the heavy boundary, so the gate has something to hold.
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
        refs["quiet"] = orders.from_report(
            conn,
            machine_id=BUFFERED,
            machine_model=R2000,
            severity=Severity.LOW,
            reported_by=UserId("sup-1"),
            description="weeping seal",
        ).ref
        refs["predicted"] = orders.from_finding(
            conn,
            Finding(
                machine_id=BUFFERED,
                component=ComponentLabel("belt_motor"),
                symptom_code=SymptomCode("SYM-014"),
                severity=Severity.HIGH,
                rule_id=RuleId("R-motor-temp-high/trend"),
                detected_at=NOW,
                evidence={"trend": True},
                kind=FindingKind.PREDICTED,
                eta=NOW + timedelta(hours=6),
                eta_confidence=timedelta(hours=2),
            ),
            finding_ref=FindingRef("F-000001"),
            machine_model=R2000,
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


class TestTheGateExplainsItself:
    def test_a_held_ticket_says_so_rather_than_vanishing(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """The whole point of the slice. A supervisor whose work does not appear
        must be able to tell a system that is holding it from one that lost it
        (principle 3, ADR-011)."""
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/dispatch/round").json()

        assert body["band"] == "heavy"
        held = {one["ref"]: one["why"] for one in body["held"]}
        assert world["refs"]["quiet"] in held
        # And it says which of the gate's rules held it, in the numbers a
        # supervisor can act on.
        assert "low" in held[world["refs"]["quiet"]]
        assert "%" in held[world["refs"]["quiet"]]

    def test_the_summary_is_the_sentence_adr_011_asked_for(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/dispatch/round").json()

        assert "load" in body["summary"]
        assert "held back" in body["summary"]
        assert body["load_ratio"] is not None
        assert body["capacity_minutes"] == 90

    def test_the_sentence_quotes_quantities_not_scores(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-045 §1: the normalised terms are a comparison within one round and
        must not be read as magnitudes. What a technician is shown is production
        units and minutes, which are true whatever else is in the queue."""
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/dispatch/round").json()
        placed = body["placed"]

        assert placed, "the shift should have released something"
        one = placed[0]
        assert one["priority_reason"]
        assert "1.0" not in one["priority_reason"]
        # The figures behind the sentence come back beside it.
        assert one["downtime_units"] >= 0.0
        assert "waited_minutes" in one

    def test_a_technician_may_read_it_too(self, client: TestClient) -> None:
        """Hiding the gate's behaviour from the people it schedules is how a
        scheduler stops being believed."""
        _signed_in(client, Role.TECHNICIAN)
        assert client.get("/dispatch/round").status_code == 200

    def test_reading_the_round_writes_nothing(
        self, client: TestClient, world: dict[str, Any], database_url: str
    ) -> None:
        """ADR-050. The report is computed, and the API is not a process that
        assigns anybody to anything (ADR-026)."""
        _signed_in(client, Role.SUPERVISOR)
        client.get("/dispatch/round")

        with connect(database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM work_order WHERE status <> 'queued'")
            assert cur.fetchone()[0] == 0  # type: ignore[index]


class TestTheTicketExplainsItself:
    def test_a_prediction_reads_differently_from_a_detection(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """ADR-020: a person decides differently about a machine that is already
        wrong and one that is not yet, and the interval is never dropped."""
        _signed_in(client, Role.TECHNICIAN)
        refs = world["refs"]

        predicted = client.get(f"/work-orders/{refs['predicted']}").json()
        reported = client.get(f"/work-orders/{refs['urgent']}").json()

        assert "expected to reach the threshold" in predicted["reason"]
        assert "give or take 2 hours" in predicted["reason"]
        assert "expected to reach" not in reported["reason"]

    def test_a_ticket_nobody_has_ranked_says_nothing_rather_than_guessing(
        self, client: TestClient, world: dict[str, Any]
    ) -> None:
        """No round has run against this database, so no ticket has been ranked.
        An empty `priority_reason` is the truth; a sentence invented on read
        would describe a queue nothing had decided about."""
        _signed_in(client, Role.TECHNICIAN)

        body = client.get(f"/work-orders/{world['refs']['urgent']}").json()

        assert body["priority_reason"] == ""
        assert body["priority_score"] == 0.0
        assert body["reason"]

    def test_a_ticket_that_is_not_there_is_a_404(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)
        assert client.get("/work-orders/WO-999999").status_code == 404

    def test_signing_in_is_required(self, client: TestClient, world: dict[str, Any]) -> None:
        assert client.get("/dispatch/round").status_code == 401
        assert client.get(f"/work-orders/{world['refs']['urgent']}").status_code == 401

"""Reading the confirmation record back, through HTTP (ADR-075, #81).

`tests/dispatch/test_what_the_confirmations_say.py` covers the arithmetic
against proposals written out by hand. This file covers the four things that
only exist once a database and a request are involved:

  * **a rejection's words survive the round trip.** The reason is the half of the
    record a person can act on, and a report that summarised it - or a column
    that truncated it - would leave the counts and lose the finding.
  * **the window is the caller's, and it is bounded on `proposed_at`.** The
    question is what a shift lead was asked during a stretch of time; a proposal
    answered after the window closed still belongs to the shift it was asked
    about.
  * **pending proposals are in the record.** Dropping them would make a report
    written mid-shift look like a shift lead who had answered everything.
  * **who may read it.** ADR-075 §6: this is a report about how often somebody's
    decisions were overruled, and it is read by the people who would act on it.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
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
    MachineId,
    MachineModel,
    Role,
    Severity,
    ShiftId,
    UserId,
)
from pdm.dispatch import Band
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.proposals import Proposal, ProposalState
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)  # 15:00 in Bangkok: the afternoon shift
TODAY = date(2026, 3, 3)
AFTERNOON = ShiftId("afternoon")
BOTTLENECK = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
PASSWORD = "correct horse battery staple"
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
TECH = UserId("tech-1")
SUP = UserId("sup-1")
PEOPLE = {
    Role.TECHNICIAN: (TECH, "Somchai"),
    Role.SUPERVISOR: (SUP, "Anan"),
    Role.ENGINEER: (UserId("eng-1"), "Pim"),
}
CREW = (Assignee(user=TECH, role=AssigneeRole.PRIMARY),)

# The words a shift lead actually types. Kept as one string and asserted whole:
# what this report is for is the half a count cannot carry (ADR-075 §3).
BECAUSE = "ana is on the line stop at st-03, not free until 16:00"


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
    """Four proposals, one of each ending, written straight onto the record.

    Written rather than produced by four rounds: what is under test here is the
    reading, and driving the world into an expiry and a rejection through the
    scheduler would make this file a test of `DispatchRounds` with the report as
    an afterthought - which is the test `tests/dispatch/test_the_confirmation_gate.py`
    already is.
    """
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(clock, fallback_minutes=FALLBACK)
    refs: dict[str, str] = {}

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, dispatch_proposal, ticket_delivery, work_order_override, "
            "finding, job, shift_assignment, technician, access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        for name in ("confirmed", "rejected", "expired", "pending", "yesterday"):
            refs[name] = orders.from_report(
                conn,
                machine_id=BOTTLENECK,
                machine_model=R2000,
                severity=Severity.HIGH,
                reported_by=SUP,
                description=f"grinding noise ({name})",
                # Five separate jobs on one machine, which is what this fixture
                # is for. A report is refused while that machine has work open
                # unless the reporter says it is something else (ADR-077 §3), and
                # here it is: five proposals with five different ends.
                distinct_from=list(refs.values()),
            ).ref

        def ask(ref: str, *, at: datetime, band: Band = Band.NORMAL) -> None:
            dispatch_repo.propose(
                conn,
                Proposal(
                    work_order_ref=ref,
                    proposed_at=at,
                    assignees=CREW,
                    priority_score=7.5,
                    priority_reason="high severity at the bottleneck",
                    band=band,
                    load_ratio=0.4,
                    shift_id=AFTERNOON,
                    on_date=TODAY,
                ),
            )

        ask(refs["confirmed"], at=NOW)
        ask(refs["rejected"], at=NOW + timedelta(minutes=1), band=Band.HEAVY)
        ask(refs["expired"], at=NOW + timedelta(minutes=2))
        ask(refs["pending"], at=NOW + timedelta(minutes=3))
        # Asked yesterday and answered today: the row that tells a window bounded
        # on `proposed_at` apart from one bounded on `decided_at`.
        ask(refs["yesterday"], at=NOW - timedelta(days=1))

        dispatch_repo.settle_proposal(
            conn,
            refs["confirmed"],
            state=ProposalState.CONFIRMED,
            at=NOW + timedelta(minutes=4),
            by=SUP,
            role=Role.SUPERVISOR,
        )
        dispatch_repo.settle_proposal(
            conn,
            refs["rejected"],
            state=ProposalState.REJECTED,
            at=NOW + timedelta(minutes=9),
            by=SUP,
            role=Role.SUPERVISOR,
            reason=BECAUSE,
        )
        dispatch_repo.settle_proposal(
            conn,
            refs["expired"],
            state=ProposalState.EXPIRED,
            at=NOW + timedelta(minutes=32),
        )
        dispatch_repo.settle_proposal(
            conn,
            refs["yesterday"],
            state=ProposalState.CONFIRMED,
            at=NOW + timedelta(minutes=5),
            by=SUP,
            role=Role.SUPERVISOR,
        )
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


class TestWhatTheRecordSays:
    def test_the_four_endings_come_back_counted_apart(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        report = client.get("/dispatch/confirmations").json()

        assert report["overall"]["proposed"] == 5
        assert report["overall"]["confirmed"] == 2
        assert report["overall"]["rejected"] == 1
        assert report["overall"]["expired"] == 1
        assert report["overall"]["pending"] == 1

    def test_a_rejection_comes_back_with_its_words_whole(self, client: TestClient) -> None:
        """The reason is why this report exists at all: a count says the shift
        lead disagreed and the words say what about (ADR-071 §8)."""
        _signed_in(client, Role.SUPERVISOR)

        (rejection,) = client.get("/dispatch/confirmations").json()["rejections"]

        assert rejection["reason"] == BECAUSE
        assert rejection["band"] == "heavy"
        assert rejection["shift_id"] == "afternoon"
        assert rejection["decided_by"] == str(SUP)
        assert rejection["minutes_to_decide"] == pytest.approx(8.0)

    def test_the_expiry_is_listed_and_not_only_counted(self, client: TestClient) -> None:
        """As loudly as the rejection. A confirmation step nobody reaches is the
        strongest argument there is for `automatic`, and a bare count of it is
        one nobody can check."""
        _signed_in(client, Role.SUPERVISOR)

        (expiry,) = client.get("/dispatch/confirmations").json()["expiries"]

        assert expiry["work_order_ref"] != ""
        assert expiry["waited_minutes"] == pytest.approx(30.0)
        assert expiry["priority_reason"] != ""

    def test_the_sweep_is_not_counted_as_a_persons_decision(self, client: TestClient) -> None:
        """Over today's questions, two were answered - in 4 minutes and in 8 -
        and one expiry waited half an hour. Counted as a decision, the expiry
        would report the expiry setting back as a measurement of how long a
        shift lead takes."""
        _signed_in(client, Role.SUPERVISOR)

        today = client.get("/dispatch/confirmations", params={"since": NOW.isoformat()}).json()[
            "decision_time"
        ]

        assert today["answered"] == 2
        assert today["longest_minutes"] == pytest.approx(8.0)
        assert today["median_minutes"] == pytest.approx(6.0)

    def test_a_pending_proposal_is_in_the_record(self, client: TestClient) -> None:
        """Otherwise a report written in the middle of a shift describes a shift
        lead who answered everything they were asked."""
        _signed_in(client, Role.SUPERVISOR)

        report = client.get("/dispatch/confirmations").json()

        assert report["overall"]["pending"] == 1
        assert report["overall"]["settled"] == 4

    def test_it_says_what_it_cannot_say(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        assert "automatic" in client.get("/dispatch/confirmations").json()["limitation"]


class TestTheWindowIsTheCallers:
    def test_since_bounds_on_when_the_question_was_asked(self, client: TestClient) -> None:
        """Yesterday's proposal was answered four minutes after today's was, and
        it belongs to yesterday: the report answers what a shift lead was asked
        during a stretch of time."""
        _signed_in(client, Role.SUPERVISOR)

        whole = client.get("/dispatch/confirmations").json()
        today = client.get("/dispatch/confirmations", params={"since": NOW.isoformat()}).json()

        assert whole["overall"]["confirmed"] == 2
        assert today["overall"]["confirmed"] == 1
        assert today["overall"]["proposed"] == 4

    def test_until_excludes_what_was_asked_after_it(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        early = client.get(
            "/dispatch/confirmations",
            params={"since": NOW.isoformat(), "until": (NOW + timedelta(minutes=2)).isoformat()},
        ).json()

        assert early["overall"]["proposed"] == 2
        assert early["overall"]["expired"] == 0

    def test_an_empty_window_reports_absence_rather_than_agreement(
        self, client: TestClient
    ) -> None:
        """Zero confirmations out of zero answers is not agreement and not
        disagreement, and a screen that rendered it as 0% would say the shift
        lead never agrees with the scheduler (principle 5)."""
        _signed_in(client, Role.SUPERVISOR)

        empty = client.get(
            "/dispatch/confirmations", params={"since": (NOW + timedelta(days=7)).isoformat()}
        ).json()

        assert empty["overall"]["proposed"] == 0
        assert empty["overall"]["confirmed_share"] is None
        assert empty["decision_time"]["median_minutes"] is None


class TestWhoMayReadIt:
    def test_the_engineer_may(self, client: TestClient) -> None:
        """The person who would take it to the maintenance department with the
        switch in hand (ADR-075 §6)."""
        _signed_in(client, Role.ENGINEER)

        assert client.get("/dispatch/confirmations").status_code == 200

    def test_a_technician_may_not(self, client: TestClient) -> None:
        """A technician reads the proposals - ADR-005's reason - and not the
        record of how often their shift lead was overruled by a queue."""
        _signed_in(client, Role.TECHNICIAN)

        assert client.get("/dispatch/confirmations").status_code == 403

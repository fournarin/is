"""Machine health, as a supervisor reads it (slice 15.2).

`assess()` has had a measurement behind it since slice 15.1 and no way into the
room. The specification here is ADR-072, ADR-076 and ADR-081 rather than the
handler, and the domain's own tests already hold every figure - so what these
assert is only what the reader adds:

  * **two lists, and they disagree.** A machine that has failed most often and a
    machine with the worst thing standing open right now are different machines,
    and a response that could not show that would be the blended number ADR-072
    exists to refuse;
  * **a zero from an empty table is not a fact.** There is no `pm_task` table
    yet, so every `pm_overdue` is zero because nothing was asked. The response
    says which of the two that is (ADR-081 section 2);
  * **the caveat arrives once**, not once per machine, and the span arrives with
    the rates it belongs to.
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

from pdm.api.overview import PM_NOT_EVERY_MACHINE, PM_STANDING_IS_ABSENT
from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    FindingStatus,
    MachineId,
    MachineModel,
    PMTaskRef,
    Role,
    RuleId,
    Severity,
    SymptomCode,
    UserId,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.health import AGE_AGAINST_ITS_CLASS_IS_ABSENT
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.triggers import repo as triggers
from pdm.work import WorkOrders
from pdm.work import repo as work
from pdm.work.repo import PmTaskDefinition

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
R2000 = MachineModel("R-2000iC")

# The machines of `config/plant.yaml`, named rather than invented, and one that
# the layout does not know about (ADR-048).
OFTEN = MachineId("MC-012")  # three failures over the span
ONCE = MachineId("MC-001")  # one, and a cancelled order that is not history
FALSE_ALARMS = MachineId("MC-004")  # closed finding nothing
STANDING = MachineId("MC-018")  # nothing closed, one critical Finding open
GONE = MachineId("MC-999")  # records mention it, `plant.yaml` does not
# The machines `plant.yaml` holds, which is what the reader asks about.
KNOWN_MACHINES = (ONCE, FALSE_ALARMS, OFTEN, STANDING)

PASSWORD = "correct horse battery staple"
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
}

SPAN_STARTS = NOW - timedelta(days=300)


def finding(
    machine_id: MachineId,
    *,
    severity: Severity,
    rule_id: str,
    status: FindingStatus = FindingStatus.OPEN,
) -> Finding:
    return Finding(
        machine_id=machine_id,
        component=ComponentLabel("spindle_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=severity,
        rule_id=RuleId(rule_id),
        detected_at=NOW - timedelta(minutes=30),
        evidence={"value": 92.0, "threshold": 85.0},
        kind=FindingKind.DETECTED,
        status=status,
    )


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
def world(database_url: str, clock: SimulatedClock) -> Iterator[ConnectionPool]:
    """Three hundred days of history, ending with one machine shouting now.

    Every order is created and then closed at a chosen moment, because
    `closed_at` is what the observed span is measured from and a fixture that
    let it default would measure a span of zero.
    """
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(
        clock, fallback_minutes={str(R2000): {severity: 60 for severity in Severity}}
    )

    ended: list[tuple[MachineId, datetime, WorkOrderStatus, WorkOutcome]] = [
        (OFTEN, SPAN_STARTS, WorkOrderStatus.CLOSED, WorkOutcome.FIXED),
        (ONCE, NOW - timedelta(days=200), WorkOrderStatus.CLOSED, WorkOutcome.FIXED),
        (OFTEN, NOW - timedelta(days=120), WorkOrderStatus.CLOSED, WorkOutcome.FIXED),
        (GONE, NOW - timedelta(days=60), WorkOrderStatus.CLOSED, WorkOutcome.FIXED),
        (
            FALSE_ALARMS,
            NOW - timedelta(days=50),
            WorkOrderStatus.CLOSED,
            WorkOutcome.NO_PROBLEM_FOUND,
        ),
        # Cancelled, not closed: the world overtook it and the machine never
        # finished having the failure (ADR-044 section 6).
        (ONCE, NOW - timedelta(days=30), WorkOrderStatus.CANCELLED, WorkOutcome.NO_PROBLEM_FOUND),
        (OFTEN, NOW - timedelta(days=10), WorkOrderStatus.CLOSED, WorkOutcome.FIXED),
    ]

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, work_order_override, finding, job, pm_task, "
            "shift_assignment, technician, access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        for machine_id, closed_at, status, outcome in ended:
            issued = orders.from_report(
                conn,
                machine_id=machine_id,
                machine_model=R2000,
                severity=Severity.HIGH,
                reported_by=UserId("sup-1"),
                description="seeded history",
            )
            assert work.close(conn, issued.ref, status=status, outcome=outcome, now=closed_at)

        # What is standing open right now, on a machine with no history at all.
        triggers.raise_finding(conn, finding(STANDING, severity=Severity.CRITICAL, rule_id="R-hot"))
        triggers.raise_finding(conn, finding(GONE, severity=Severity.LOW, rule_id="R-gone"))
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield pool
    finally:
        pool.close()


@pytest.fixture
def client(world: ConnectionPool, clock: SimulatedClock, tmp_path: Path) -> Iterator[TestClient]:
    from pdm.api.app import create_app

    app = create_app(
        pool=world,
        library=DocumentLibrary(FilesystemObjectStore(tmp_path / "store"), clock),
        clock=clock,
        config_dir=Path("config"),
    )
    with TestClient(app) as test_client:
        yield test_client


def _signed_in(client: TestClient, role: Role) -> TestClient:
    user, _ = PEOPLE[role]
    assert (
        client.post("/sessions", json={"user": str(user), "password": PASSWORD}).status_code == 201
    )
    return client


def _read(client: TestClient, role: Role = Role.SUPERVISOR) -> dict[str, Any]:
    _signed_in(client, role)
    response = client.get("/overview/health")
    assert response.status_code == 200, response.text
    return dict(response.json())


@pytest.mark.db
class TestTwoOrderingsAndNeverOne:
    def test_the_two_lists_hold_the_same_machines_in_different_orders(
        self, client: TestClient
    ) -> None:
        """The whole of ADR-072 section 2 in one assertion.

        If these ever came back identical the screen could show one list without
        losing anything, and the argument for two would be over.
        """
        body = _read(client)

        by_history = [row["machine_id"] for row in body["by_history"]]
        by_now = [row["machine_id"] for row in body["by_now"]]

        assert sorted(by_history) == sorted(by_now)
        assert by_history != by_now
        assert by_history[0] == str(OFTEN), (
            "three failures over the span is the most of any machine"
        )
        assert by_now[0] == str(STANDING), (
            "a critical Finding open now, on a machine with no history"
        )

    def test_no_figure_anywhere_blends_the_two(self, client: TestClient) -> None:
        body = _read(client)

        for row in body["by_history"] + body["by_now"]:
            assert set(row) == {"machine_id", "history", "now"}
            assert "score" not in row["history"]
            assert "score" not in row["now"]
        assert not any(key in body for key in ("score", "ranking", "worst", "overall"))

    def test_every_row_carries_the_sentence_the_backend_wrote(self, client: TestClient) -> None:
        """The reason is the domain's, not one assembled from the fields beside
        it - a second voice explaining the same number is ADR-063's refusal."""
        body = _read(client)

        for row in body["by_history"]:
            assert row["history"]["reason"].strip()
            assert row["now"]["reason"].strip()
        first = next(row for row in body["by_history"] if row["machine_id"] == str(OFTEN))
        assert str(OFTEN) in first["history"]["reason"]


@pytest.mark.db
class TestWhatTheReadingCannotSay:
    def test_the_pm_counts_arrive_with_the_sentence_saying_nothing_was_asked(
        self, client: TestClient
    ) -> None:
        """With no task registered, every machine reads "0 overdue", which is a
        claim drawn from an empty set (ADR-081 section 2, ADR-083 section 6)."""
        body = _read(client)

        assert PM_STANDING_IS_ABSENT in body["absent"]
        assert all(row["history"]["pm_overdue"] == 0 for row in body["by_history"])
        assert all(row["history"]["pm_completed"] == 0 for row in body["by_history"])

    def test_the_age_caveat_arrives_once_and_not_once_per_machine(self, client: TestClient) -> None:
        body = _read(client)

        assert body["absent"].count(AGE_AGAINST_ITS_CLASS_IS_ABSENT) == 1
        assert len(body["by_history"]) > 1
        # Still on every reading, because a reading handed to something that is
        # not this screen has to arrive with it.
        assert all(
            AGE_AGAINST_ITS_CLASS_IS_ABSENT in row["history"]["absent"]
            for row in body["by_history"]
        )

    def test_a_registered_task_is_counted_and_the_machines_without_one_are_named(
        self, client: TestClient, database_url: str, clock: SimulatedClock
    ) -> None:
        """The zero means two different things and the screen says which. A
        machine with a schedule and nothing due reads zero; a machine with no
        schedule reads zero because nobody asked (ADR-083 section 6)."""
        with connect(database_url) as conn:
            work.register_pm_tasks(
                conn,
                [
                    PmTaskDefinition(
                        pm_task_ref=PMTaskRef("pm-often-belt"),
                        machine_id=OFTEN,
                        symptom_code=SymptomCode("PM-toothed-belt"),
                        interval=timedelta(hours=8000),
                    )
                ],
                now=clock.now() - timedelta(days=2),
            )
            conn.commit()

        body = _read(client)

        counted = next(row for row in body["by_history"] if row["machine_id"] == str(OFTEN))
        assert counted["history"]["pm_overdue"] == 1
        assert PM_STANDING_IS_ABSENT not in body["absent"]
        named = next(line for line in body["absent"] if line.startswith("preventive maintenance"))
        assert str(ONCE) in named
        assert str(OFTEN) not in named
        assert named == PM_NOT_EVERY_MACHINE.format(
            machines=", ".join(sorted(str(one) for one in KNOWN_MACHINES if one != OFTEN))
        )

    def test_the_absences_are_in_the_order_they_were_written(self, client: TestClient) -> None:
        body = _read(client)

        assert body["absent"] == [AGE_AGAINST_ITS_CLASS_IS_ABSENT, PM_STANDING_IS_ABSENT]


@pytest.mark.db
class TestTheSpanTravelsWithTheRates:
    def test_the_response_names_the_window_every_rate_was_counted_over(
        self, client: TestClient
    ) -> None:
        body = _read(client)

        assert body["observed_from"] is not None
        assert body["observed_days"] == pytest.approx(300.0, abs=0.01)
        # The same window as the readings, because a panel that named a
        # different one would be a second answer about the same numbers.
        assert all(
            row["history"]["observed_days"] == pytest.approx(body["observed_days"])
            for row in body["by_history"]
        )

    def test_the_span_starts_at_the_earliest_closed_order(self, client: TestClient) -> None:
        body = _read(client)

        assert body["observed_from"].startswith(SPAN_STARTS.date().isoformat())
        assert body["observed_to"].startswith(NOW.date().isoformat())

    def test_a_machine_with_no_records_of_its_own_is_still_counted_over_the_shared_span(
        self, client: TestClient
    ) -> None:
        """`MC-018` has closed nothing, and the span is not its own: every
        machine is counted over the same window, so its rate is a real zero
        rather than an absence (ADR-076 section 4)."""
        body = _read(client)

        standing = next(row for row in body["by_now"] if row["machine_id"] == str(STANDING))
        assert standing["history"]["closed_orders"] == 0
        assert standing["history"]["failures_per_100_days"] == 0.0
        assert standing["history"]["observed_days"] == pytest.approx(body["observed_days"])
        assert standing["now"]["highest_severity"] == "critical"


@pytest.mark.db
class TestWhatIsCountedAndWhatIsNot:
    def test_a_cancelled_order_is_not_a_failure_the_machine_finished_having(
        self, client: TestClient
    ) -> None:
        """`MC-001` has two ended orders and one of them was cancelled."""
        body = _read(client)

        once = next(row for row in body["by_history"] if row["machine_id"] == str(ONCE))
        assert once["history"]["closed_orders"] == 1
        assert once["history"]["failures"] == 1

    def test_an_order_that_found_nothing_is_counted_as_a_false_alarm(
        self, client: TestClient
    ) -> None:
        body = _read(client)

        quiet = next(row for row in body["by_history"] if row["machine_id"] == str(FALSE_ALARMS))
        assert quiet["history"]["false_alarms"] == 1
        assert quiet["history"]["failures"] == 0

    def test_the_false_alarm_count_does_not_lift_a_machine_up_the_history_list(
        self, client: TestClient
    ) -> None:
        """ADR-076 section 3: displayed, and never a key. A machine somebody was
        sent to for nothing has a rule problem, not a machine problem."""
        body = _read(client)

        order = [row["machine_id"] for row in body["by_history"]]
        assert order.index(str(OFTEN)) < order.index(str(FALSE_ALARMS))


@pytest.mark.db
class TestMachinesTheLayoutForgot:
    def test_a_machine_the_records_mention_and_plant_yaml_does_not_is_named(
        self, client: TestClient
    ) -> None:
        body = _read(client)

        assert body["unplaced_machines"] == [str(GONE)]

    def test_it_is_in_neither_ordering(self, client: TestClient) -> None:
        """Reported rather than ranked. `assess()` is asked about the plant's
        machines, and a row for one the layout does not know would be a row
        nobody can act on from this screen (ADR-048)."""
        body = _read(client)

        assert str(GONE) not in [row["machine_id"] for row in body["by_history"]]
        assert str(GONE) not in [row["machine_id"] for row in body["by_now"]]


@pytest.mark.db
class TestWhoMayRead:
    def test_a_supervisor_and_an_engineer_may(self, client: TestClient) -> None:
        for role in (Role.SUPERVISOR, Role.ENGINEER):
            _signed_in(client, role)
            assert client.get("/overview/health").status_code == 200

    def test_a_technician_may_not(self, client: TestClient) -> None:
        _signed_in(client, Role.TECHNICIAN)

        assert client.get("/overview/health").status_code == 403

    def test_a_signed_out_visitor_may_not(self, client: TestClient) -> None:
        assert client.get("/overview/health").status_code == 401

"""The two loops, over HTTP, for the first time (ADR-087).

`CLAUDE.md` and the ADRs are the specification here, not the code. Three things
are checked that no test of `propose()` on its own can reach:

- **Invariant 11 through the real path.** ADR-022 forbids any loop from proposing
  that a safety-linked threshold be loosened. The refusal has been tested by
  calling the function with `safety_critical=True`; what had never been shown is
  that a rule marked `safety_critical` in `config/rules.yaml` reaches it that
  way. Until this test the flag was a field whose name matched a parameter, and
  `scripts/check_config_is_read.py` said so in its own docstring.
- **Nothing here writes.** ADR-022's sentence is that every loop proposes rather
  than changes, and ADR-087 keeps that by giving the loops no write route at
  all. Reading the proposals leaves the playbook exactly as it was, and the
  router carries no method that could do otherwise.
- **Invariant 6 at the endpoint**, for the two roles that may not read this at
  all - a refusal, not a hidden link.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.api import loops
from pdm.api.app import create_app
from pdm.contracts import (
    ComponentLabel,
    DocumentId,
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
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import repo as playbooks
from pdm.triggers import repo as triggers
from pdm.work import repo as work

START = datetime(2026, 5, 4, 8, 0, tzinfo=UTC)
R2000IC = MachineModel("R-2000iC")

# Priced at thirty minutes, and its closed jobs all took sixty. ADR-022's cap
# means one cycle may ask for thirty-six and no more, which is the case worth
# having on screen: the loop wanted to move further than it was allowed to.
SYM = SymptomCode("SYM-014")
CURRENT_MINUTES = 30
REAL_MINUTES = 60

# The rule behind SYM-014 in config/rules.yaml: fires above 85.0, not
# safety-linked. Its neighbour fires below 1.0 and is.
TEMP_RULE = RuleId("R-motor-temp-high")
INTERLOCK_RULE = RuleId("R-safety-interlock-open")

PASSWORD = "correct horse battery staple"
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
    Role.OPERATOR: (UserId("op-1"), "Malee"),
}


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


def _approve_a_playbook(
    conn: Connection[Any], document_id: DocumentId, *, symptom_code: SymptomCode
) -> None:
    playbooks.save_approved(
        conn,
        Playbook(
            symptom_code=symptom_code,
            machine_model=R2000IC,
            steps=(
                PlaybookStep(
                    text="Retighten the motor mount bolts to 42 Nm.",
                    source_doc=document_id,
                    page=4,
                    confidence=0.8,
                ),
            ),
            tools=("torque wrench 5-60 Nm",),
            estimated_minutes=CURRENT_MINUTES,
            required_skill=SkillId("robot_mechanical"),
            source_doc=document_id,
            page=4,
            status=PlaybookStatus.APPROVED,
            approved_by=UserId("eng-1"),
            approved_at=START,
            approver_role=Role.ENGINEER,
        ),
        approved_by=UserId("eng-1"),
        approved_at=START,
        approver_role=Role.ENGINEER,
    )


def _closed_against_the_playbook(conn: Connection[Any], *, index: int, minutes: int) -> None:
    """A finished job priced from the playbook, with no Finding behind it.

    Reported work rather than condition work, so Loop 1's evidence here cannot
    be confused with Loop 2's: the duration is what a repair took, and no rule
    raised it (ADR-010).
    """
    work.issue(
        conn,
        WorkOrder(
            origin=WorkOrderOrigin.MANUAL,
            machine_id=MachineId(f"MC-{index:03d}"),
            severity=Severity.MEDIUM,
            playbook_ref=f"{SYM}/{R2000IC}",  # type: ignore[arg-type]
            estimated_minutes=CURRENT_MINUTES,
            reason="reported by the operator on the morning shift",
            status=WorkOrderStatus.CLOSED,
            work_segments=(
                WorkSegment(
                    user=UserId("tech-1"),
                    started_at=START,
                    ended_at=START + timedelta(minutes=minutes),
                ),
            ),
            outcome=WorkOutcome.FIXED,
        ),
        now=START,
    )


def _closed_behind_a_rule(
    conn: Connection[Any],
    *,
    index: int,
    rule_id: RuleId,
    symptom_code: SymptomCode,
    metric_name: str,
    threshold: float,
    value: float,
    outcome: WorkOutcome,
) -> None:
    """One firing of one rule on one machine, and the job it became.

    A machine of its own per firing, because ADR-023's suppression key is
    (machine_id, rule_id): ten firings of one rule on one machine would be one
    Finding and one observation, which is the property Loop 2 depends on.
    """
    machine = MachineId(f"MC-{index:03d}")
    finding_ref = str(
        triggers.raise_finding(
            conn,
            Finding(
                machine_id=machine,
                component=ComponentLabel("belt_motor"),
                symptom_code=symptom_code,
                severity=Severity.HIGH,
                rule_id=rule_id,
                detected_at=START,
                evidence={"metric_name": metric_name, "threshold": threshold, "value": value},
                kind=FindingKind.DETECTED,
            ),
        )
    )
    work.issue(
        conn,
        WorkOrder(
            origin=WorkOrderOrigin.CONDITION,
            finding_ref=finding_ref,  # type: ignore[arg-type]
            machine_id=machine,
            severity=Severity.HIGH,
            estimated_minutes=CURRENT_MINUTES,
            reason="over threshold for 20 minutes",
            status=WorkOrderStatus.CLOSED,
            work_segments=(
                WorkSegment(
                    user=UserId("tech-1"), started_at=START, ended_at=START + timedelta(minutes=20)
                ),
            ),
            outcome=outcome,
        ),
        now=START,
    )


@pytest.fixture
def setup(database_url: str, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Four accounts, one approved playbook, and the closed work behind two rules.

    The numbers are chosen so that each loop has something to say and the reader
    can check the arithmetic with a pencil, which is the property ADR-066 and
    ADR-073 both claim for their proposals.
    """
    clock = SimulatedClock(START)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    auth = Authentication(LocalAccounts(), clock)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE job, work_order, finding, playbook_proposal, playbook, access_log, "
            "session, account, chunk, document_page, document CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)
        document = library.add(
            conn,
            content=b"%PDF-1.7 a manual",
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000IC,
            title="R-2000iC Maintenance Manual",
            uploaded_by=UserId("op-1"),
        )
        _approve_a_playbook(conn, document.document_id, symptom_code=SYM)

        # Six finished jobs at sixty minutes against an estimate of thirty.
        for index in range(6):
            _closed_against_the_playbook(conn, index=index, minutes=REAL_MINUTES)

        # Ten closed orders behind the temperature rule: seven confirmed faults,
        # the mildest reading 100.0, and three false alarms below it. The
        # separating threshold is 88.0, and 85.0 + 10% leaves room to reach it.
        readings: list[tuple[float, WorkOutcome]] = [
            (86.0, WorkOutcome.NO_PROBLEM_FOUND),
            (87.0, WorkOutcome.NO_PROBLEM_FOUND),
            (88.0, WorkOutcome.NO_PROBLEM_FOUND),
        ] + [(100.0 + offset, WorkOutcome.FIXED) for offset in range(7)]
        for index, (value, outcome) in enumerate(readings, start=100):
            _closed_behind_a_rule(
                conn,
                index=index,
                rule_id=TEMP_RULE,
                symptom_code=SYM,
                metric_name="motor_temp_c",
                threshold=85.0,
                value=value,
                outcome=outcome,
            )

        # And two behind the safety-linked one, one of them a false alarm, so the
        # refusal is not merely the absence of evidence.
        for index, outcome in enumerate(
            [WorkOutcome.NO_PROBLEM_FOUND, WorkOutcome.FIXED], start=200
        ):
            _closed_behind_a_rule(
                conn,
                index=index,
                rule_id=INTERLOCK_RULE,
                symptom_code=SymptomCode("SYM-002"),
                metric_name="interlock_closed",
                threshold=1.0,
                value=0.0,
                outcome=outcome,
            )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "library": library, "clock": clock}
    finally:
        pool.close()


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    app = create_app(pool=setup["pool"], library=setup["library"], clock=setup["clock"])
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[Any]]:
    connection = connect(database_url)
    try:
        yield connection
    finally:
        connection.close()


def _log_in(client: TestClient, role: Role) -> None:
    user, _ = PEOPLE[role]
    assert client.post("/sessions", json={"user": user, "password": PASSWORD}).status_code == 201


def _line_for(rows: list[dict[str, Any]], rule_id: str) -> dict[str, Any]:
    matching = [row for row in rows if row["rule_id"] == rule_id]
    assert len(matching) == 1, f"{rule_id} should appear exactly once, got {len(matching)}"
    return matching[0]


@pytest.mark.db
class TestTheSafetyLinkedRuleIsRefusedThroughTheRealPath:
    """Invariant 11, with the flag coming from `config/rules.yaml` (ADR-022)."""

    def test_the_refusal_names_safety_critical(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get("/loops/thresholds")

        assert response.status_code == 200
        line = _line_for(response.json(), INTERLOCK_RULE)
        assert line["safety_critical"] is True
        assert line["proposal"] is None
        assert line["refusal"]["cause"] == "safety_critical"

    def test_and_it_is_refused_although_it_has_false_alarms_behind_it(
        self, client: TestClient
    ) -> None:
        """The refusal must not be "no evidence" wearing another name.

        There is a false alarm behind this rule and a confirmed fault at the
        same reading, which for any other rule is the input to a proposal.
        """
        _log_in(client, Role.ENGINEER)

        line = _line_for(client.get("/loops/thresholds").json(), INTERLOCK_RULE)

        assert line["refusal"]["false_alarms"] >= 1
        assert "ไม่เสนอให้ผ่อนเกณฑ์" in line["refusal"]["reason"]

    def test_the_value_that_reaches_the_loop_is_the_one_in_the_file(
        self, client: TestClient
    ) -> None:
        """The other half of the same point, from the configured side.

        A rule the file marks `safety_critical: false` is proposed about. If the
        flag were never carried, both rules would come back the same way and the
        test above would pass on a constant.
        """
        _log_in(client, Role.ENGINEER)

        rows = client.get("/loops/thresholds").json()

        assert _line_for(rows, TEMP_RULE)["safety_critical"] is False
        assert _line_for(rows, TEMP_RULE)["proposal"] is not None


@pytest.mark.db
class TestWhatTheFalseAlarmsPropose:
    def test_the_separating_threshold_reaches_the_screen(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        proposal = _line_for(client.get("/loops/thresholds").json(), TEMP_RULE)["proposal"]

        assert proposal["current_threshold"] == 85.0
        assert proposal["proposed_threshold"] == 88.0
        assert proposal["false_alarms"] == 3
        assert proposal["faults_found"] == 7
        assert len(proposal["would_not_have_fired"]) == 3
        assert len(proposal["still_fires_on"]) == 7

    def test_the_one_sidedness_of_the_evidence_travels_with_it(self, client: TestClient) -> None:
        """ADR-073 section 6: the caveat is on the record, not only in the ADR.

        A reviewer reads a number on a screen, and a limitation that lives in a
        document is absent at the moment it matters.
        """
        _log_in(client, Role.ENGINEER)

        proposal = _line_for(client.get("/loops/thresholds").json(), TEMP_RULE)["proposal"]

        assert "can never say it is too loose" in proposal["limitation"]

    def test_a_rule_with_no_closed_work_says_so_rather_than_vanishing(
        self, client: TestClient
    ) -> None:
        """Principle 5. An absent row reads as a rule nobody had to think about."""
        _log_in(client, Role.ENGINEER)

        line = _line_for(client.get("/loops/thresholds").json(), "R-fan-rpm-low")

        assert line["proposal"] is None
        assert line["refusal"]["cause"] == "below_floor"
        assert line["refusal"]["observations"] == 0

    def test_every_configured_rule_appears_exactly_once(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        rows = client.get("/loops/thresholds").json()

        assert sorted(row["rule_id"] for row in rows) == [
            "R-cycle-time-drift",
            "R-fan-rpm-low",
            "R-motor-temp-high",
            "R-safety-interlock-open",
            "R-servo-current-high",
        ]


@pytest.mark.db
class TestWhatTheFinishedJobsSay:
    def test_the_median_is_proposed_within_the_cap(self, client: TestClient) -> None:
        """Six jobs at sixty against an estimate of thirty: ADR-022 allows 36."""
        _log_in(client, Role.ENGINEER)

        response = client.get("/loops/estimates")

        assert response.status_code == 200
        line = next(row for row in response.json() if row["symptom_code"] == SYM)
        assert line["current_minutes"] == CURRENT_MINUTES
        assert line["proposal"]["median_minutes"] == REAL_MINUTES
        assert line["proposal"]["proposed_minutes"] == 36
        assert line["proposal"]["capped"] is True
        assert line["proposal"]["observations"] == 6

    def test_the_evidence_is_the_orders_it_was_computed_from(self, client: TestClient) -> None:
        """ADR-022 asks for the jobs behind the middle, not only the middle."""
        _log_in(client, Role.ENGINEER)

        line = next(row for row in client.get("/loops/estimates").json() if row["proposal"])

        assert len(line["proposal"]["evidence"]) == 6
        assert line["closed_orders"] == 6


@pytest.mark.db
class TestTheLoopsChangeNothing:
    """ADR-022's sentence, checked rather than trusted."""

    def test_reading_the_proposals_leaves_the_playbook_as_it_was(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        client.get("/loops/estimates")
        client.get("/loops/thresholds")

        row = conn.execute(
            "SELECT estimated_minutes, revision FROM playbook WHERE symptom_code = %s", (SYM,)
        ).fetchone()
        assert row == (CURRENT_MINUTES, 1)


@pytest.mark.db
def _closed_with_a_note(
    conn: Connection[Any], *, index: int, note: str | None, closed: bool = True
) -> None:
    work.issue(
        conn,
        WorkOrder(
            origin=WorkOrderOrigin.MANUAL,
            machine_id=MachineId(f"MC-{index:03d}"),
            severity=Severity.MEDIUM,
            playbook_ref=f"{SYM}/{R2000IC}",  # type: ignore[arg-type]
            estimated_minutes=CURRENT_MINUTES,
            reason="reported by the operator",
            status=WorkOrderStatus.CLOSED if closed else WorkOrderStatus.QUEUED,
            outcome=WorkOutcome.FIXED if closed else None,
            technician_feedback=note,
        ),
        now=START + timedelta(minutes=index),
    )
    if closed:
        conn.execute(
            "UPDATE work_order SET closed_at = %s WHERE machine_id = %s",
            (START + timedelta(minutes=index), f"MC-{index:03d}"),
        )


class TestWhatTheTechniciansWrote:
    """ADR-117: the note written at close reaches the engineer who owns the steps."""

    def test_a_closing_note_is_listed_with_its_symptom_newest_first(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        _closed_with_a_note(conn, index=901, note="ขั้น 3 ต้องใช้ลูกบ็อกซ์ 13 มม. ไม่ใช่ 10")
        _closed_with_a_note(conn, index=902, note="  ฝาครอบแน่นมาก ใช้เวลาถอดนาน  ")
        conn.commit()
        _log_in(client, Role.ENGINEER)

        rows = [
            row
            for row in client.get("/loops/notes").json()["notes"]
            if row["machine_id"] >= "MC-901"
        ]

        assert [row["machine_id"] for row in rows] == ["MC-902", "MC-901"]
        assert rows[0]["note"] == "ฝาครอบแน่นมาก ใช้เวลาถอดนาน"
        assert rows[1]["symptom_code"] == SYM

    def test_blank_notes_and_open_jobs_are_not_listed(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        _closed_with_a_note(conn, index=903, note="   ")
        _closed_with_a_note(conn, index=904, note=None)
        _closed_with_a_note(conn, index=905, note="ยังทำไม่เสร็จ", closed=False)
        conn.commit()
        _log_in(client, Role.ENGINEER)

        machines = {row["machine_id"] for row in client.get("/loops/notes").json()["notes"]}

        assert not machines & {"MC-903", "MC-904", "MC-905"}


class TestWhoMayLook:
    """Invariant 6 at the endpoint, not by hiding a link."""

    @pytest.mark.parametrize("path", ["/loops/estimates", "/loops/thresholds", "/loops/notes"])
    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.OPERATOR])
    def test_the_endpoint_refuses_the_two_roles_that_decide_nothing_here(
        self, client: TestClient, role: Role, path: str
    ) -> None:
        _log_in(client, role)

        assert client.get(path).status_code == 403

    @pytest.mark.parametrize("path", ["/loops/estimates", "/loops/thresholds", "/loops/notes"])
    def test_a_shift_lead_may_read_what_they_may_not_decide(
        self, client: TestClient, path: str
    ) -> None:
        """ADR-064's argument: somebody who cannot see a queue cannot ask why it
        is not moving. Approving these is still an engineer's, and there is no
        route that approves them at all."""
        _log_in(client, Role.SUPERVISOR)

        assert client.get(path).status_code == 200

    @pytest.mark.parametrize("path", ["/loops/estimates", "/loops/thresholds", "/loops/notes"])
    def test_the_refusal_is_in_the_access_log(
        self, client: TestClient, conn: Connection[Any], path: str
    ) -> None:
        _log_in(client, Role.TECHNICIAN)

        client.get(path)

        row = conn.execute(
            "SELECT user_id, allowed FROM access_log WHERE action LIKE 'read_%_proposals' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row == ("tech-1", False)


class TestThereIsNoWayToWriteEither:
    """The structural half of ADR-087 section 3, and it needs no database.

    A loop that proposes rather than changes is a property of what the routes
    are, not of what the handlers happen to do today. Loop 1's number carries an
    engineer's approval and Loop 2's lives in a file; a write route here would be
    an approval with no approver, so there is none to find.
    """

    def test_the_router_exposes_reads_and_nothing_else(self) -> None:
        for route in loops.router.routes:
            assert isinstance(route, APIRoute)
            assert route.methods is not None
            assert route.methods <= {"GET", "HEAD"}, f"{route.path} can be written to"

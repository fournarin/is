"""The review queue over HTTP, and invariant 6 where it is specified.

design.md 12 puts it in one sentence: *only an engineer may approve - checked at
the endpoint, not by hiding a button*. So the test that matters here is the one
that signs in as each of the other three roles and posts to the approval route
anyway, which is what somebody who found the URL would do.

The access log is checked too. ADR-019 wants the refusals in it more than the
successes: "who read this manual" is the obvious question and "who tried to
approve a playbook and could not" is the one asked after an incident.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import DocumentId, MachineModel, PlaybookStep, Role, SkillId, SymptomCode, UserId
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import ProposalOrigin
from pdm.playbooks import repo as playbooks

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
R2000IC = MachineModel("R-2000iC")
SYM = SymptomCode("SYM-014")
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


@pytest.fixture
def setup(database_url: str, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Four accounts, one manual, one pending draft in the queue."""
    clock = SimulatedClock(START)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    auth = Authentication(LocalAccounts(), clock)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE job, playbook_proposal, playbook, access_log, session, account, "
            "chunk, document_page, document CASCADE"
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
        proposal = playbooks.add_proposal(
            conn,
            symptom_code=SYM,
            machine_model=R2000IC,
            origin=ProposalOrigin.DRAFTED,
            outcome="repair",
            steps=(
                PlaybookStep(
                    text="Retighten the motor mount bolts to 42 Nm.",
                    source_doc=document.document_id,
                    page=4,
                    confidence=0.8,
                ),
            ),
            tools=("torque wrench 5-60 Nm",),
            proposed_skill=SkillId("robot_mechanical"),
            proposed_minutes=45,
            rejected=(),
            reason="1 step from page 4 of the R-2000iC manual",
            created_at=START,
            created_by=None,
        )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {
            "pool": pool,
            "library": library,
            "clock": clock,
            "proposal_id": proposal.proposal_id,
            "document_id": document.document_id,
        }
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


class TestOnlyAnEngineerMayApprove:
    """Invariant 6, at the endpoint, for every role that is not an engineer."""

    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.SUPERVISOR, Role.OPERATOR])
    def test_the_endpoint_refuses(
        self, client: TestClient, setup: dict[str, Any], role: Role
    ) -> None:
        _log_in(client, role)

        response = client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        assert response.status_code == 403

    def test_and_the_proposal_is_still_pending_afterwards(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.SUPERVISOR)

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        pending = playbooks.proposal(conn, setup["proposal_id"])
        assert pending is not None and pending.status.value == "pending"
        assert playbooks.get(conn, SYM, R2000IC) is None

    def test_the_refusal_is_in_the_access_log(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """ADR-019: the entry that matters most is the one that was refused."""
        _log_in(client, Role.OPERATOR)

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        row = conn.execute(
            "SELECT user_id, role, allowed FROM access_log "
            "WHERE action = 'approve_playbook' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row == ("op-1", "operator", False)

    def test_an_engineer_may(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        assert response.status_code == 200
        assert response.json()["revision"] == 1
        assert response.json()["approved_by"] == "eng-1"
        served = playbooks.get(conn, SYM, R2000IC)
        assert served is not None


class TestTheQueueOverHttp:
    def test_a_supervisor_may_see_the_queue_without_being_able_to_act_on_it(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """Seeing is not authority. A supervisor who cannot see the queue cannot
        ask why it is not moving, which is their job."""
        _log_in(client, Role.SUPERVISOR)

        listed = client.get("/playbooks/queue")
        acted = client.post(f"/playbooks/queue/{setup['proposal_id']}/dismiss", json={"note": "no"})

        assert listed.status_code == 200
        assert [item["proposal_id"] for item in listed.json()] == [setup["proposal_id"]]
        assert acted.status_code == 403

    def test_a_technician_cannot_read_the_queue(self, client: TestClient) -> None:
        _log_in(client, Role.TECHNICIAN)

        assert client.get("/playbooks/queue").status_code == 403

    def test_nobody_reads_it_without_signing_in(self, client: TestClient) -> None:
        assert client.get("/playbooks/queue").status_code == 401

    def test_the_detail_view_shows_what_the_gate_refused(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """A draft that lost three steps to the figure gate is a different thing
        from one that never had them (ADR-037), and only a person can tell
        whether the manual is wrong or the backend is."""
        with connect(os.environ["DATABASE_URL"]) as writer:
            withheld = playbooks.add_proposal(
                writer,
                symptom_code=SymptomCode("SYM-021"),
                machine_model=R2000IC,
                origin=ProposalOrigin.DRAFTED,
                outcome="withheld",
                steps=(),
                tools=(),
                proposed_skill=None,
                proposed_minutes=None,
                rejected=(
                    {
                        "text": "Retighten the motor mount bolts to 33 Nm.",
                        "reason": "figure_not_in_evidence",
                        "figures_not_in_evidence": ["33"],
                    },
                ),
                reason="1 of 4 proposed steps failed the checks in ADR-037",
                created_at=START,
                created_by=None,
            )
            writer.commit()
        _log_in(client, Role.ENGINEER)

        response = client.get(f"/playbooks/queue/{withheld.proposal_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["outcome"] == "withheld"
        assert body["steps"] == []
        assert body["rejected"][0]["figures_not_in_evidence"] == ["33"]

    def test_approving_something_that_is_not_there(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        assert client.post("/playbooks/queue/99999/approve", json={}).status_code == 409

    def test_approving_the_same_proposal_twice_conflicts(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        again = client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        assert again.status_code == 409

    def test_a_dismissal_without_a_note_is_refused_by_the_schema(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(f"/playbooks/queue/{setup['proposal_id']}/dismiss", json={})

        assert response.status_code == 422


class TestWhatTheEngineerHasToFillIn:
    def test_a_proposal_with_no_duration_asks_rather_than_inventing_one(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """ADR-037 section 8, over HTTP: 422 and a sentence saying which field."""
        with connect(os.environ["DATABASE_URL"]) as writer:
            incomplete = playbooks.add_proposal(
                writer,
                symptom_code=SymptomCode("SYM-047"),
                machine_model=R2000IC,
                origin=ProposalOrigin.DRAFTED,
                outcome="repair",
                steps=(
                    PlaybookStep(
                        text="Remove the four fan mounting screws torqued to 3 Nm.",
                        source_doc=DocumentId(setup["document_id"]),
                        page=5,
                        confidence=0.7,
                    ),
                ),
                tools=(),
                proposed_skill=SkillId("electrical"),
                proposed_minutes=None,
                rejected=(),
                reason="the page states no duration",
                created_at=START,
                created_by=None,
            )
            writer.commit()
        _log_in(client, Role.ENGINEER)

        refused = client.post(f"/playbooks/queue/{incomplete.proposal_id}/approve", json={})
        accepted = client.post(
            f"/playbooks/queue/{incomplete.proposal_id}/approve",
            json={"estimated_minutes": 25},
        )

        assert refused.status_code == 422
        assert "no duration" in refused.json()["detail"]
        assert accepted.status_code == 200


class TestWhatTheCodeReviewFound:
    def test_a_note_of_nothing_but_spaces_is_a_422_not_a_500(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """It clears the schema's min_length and is still not a reason."""
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/dismiss", json={"note": "   "}
        )

        assert response.status_code == 422

    def test_a_negative_limit_is_refused_before_it_reaches_the_database(
        self, client: TestClient
    ) -> None:
        _log_in(client, Role.ENGINEER)

        assert client.get("/playbooks/queue?limit=-1").status_code == 422
        assert client.get("/playbooks/queue?limit=100000").status_code == 422

    def test_a_skill_outside_the_plant_vocabulary_is_refused(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """Invariant 13 over HTTP. The app loads plant.yaml at boot, so the
        endpoint knows which labels exist without asking the database."""
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"required_skill": "robot_mechnical"},
        )

        assert response.status_code == 422
        assert "not one of the skills" in response.json()["detail"]

    def test_the_approver_can_say_it_takes_two_people(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"required_technicians": 2},
        )

        assert response.status_code == 200
        served = playbooks.get(conn, SYM, R2000IC)
        assert served is not None and served[0].required_technicians == 2

    def test_the_approver_can_give_each_step_in_thai(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """ADR-095: stored on the step, beside the manual's words it renders."""
        _log_in(client, Role.ENGINEER)
        pending = client.get(f"/playbooks/queue/{setup['proposal_id']}").json()
        english = [step["text"] for step in pending["steps"]]
        # Each rendering carries exactly the figures of the step it renders, each
        # with the unit the step gives it (ADR-108).
        quantity = r"\d[\d,]*(?:\.\d+)?(?:\s*(?:degrees Celsius|Nm|mm|N|rpm|minutes?|seconds?|%))?"
        thai = ["ขั้นที่แปลแล้ว " + " ".join(re.findall(quantity, text)) for text in english]

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"thai_steps": thai},
        )

        assert response.status_code == 200, response.text
        served = playbooks.get(conn, SYM, R2000IC)
        assert served is not None
        assert [step.text_th for step in served[0].steps] == thai
        assert [step.text for step in served[0].steps] == english

    def test_a_thai_step_with_a_different_figure_is_refused(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        pending = client.get(f"/playbooks/queue/{setup['proposal_id']}").json()
        thai = ["" for _ in pending["steps"]]
        thai[0] = "ค่าที่ไม่มีในต้นฉบับ 9999"

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"thai_steps": thai},
        )

        assert response.status_code == 422
        assert "ตัวเลขในคำแปลไม่ตรงกับต้นฉบับ" in response.json()["detail"]
        assert playbooks.get(conn, SYM, R2000IC) is None

    def test_the_approver_can_give_each_tool_in_thai_and_pick_the_skill_by_name(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """ADR-130: the tools beside the manual's words, and the skill offered as
        the plant names it rather than typed as an id."""
        _log_in(client, Role.ENGINEER)
        pending = client.get(f"/playbooks/queue/{setup['proposal_id']}").json()
        assert {"skill": "robot_mechanical", "name": "ช่างกลหุ่นยนต์"} in pending["skills"]
        tools = pending["tools"]
        if not tools:
            pytest.skip("this fixture's draft lists no tools")
        thai = ["" for _ in tools]
        thai[0] = "เครื่องมือ " + " ".join(re.findall(r"\d[\d.\-]*\s*(?:Nm|mm|N)?", tools[0]))

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"thai_tools": thai},
        )

        assert response.status_code == 200, response.text
        served = playbooks.get(conn, SYM, R2000IC)
        assert served is not None
        assert served[0].tools_th == tuple(thai)
        assert served[0].tools == tuple(tools)


class TestAskingForADraft:
    """The other half of the gap: nothing used to enqueue anything."""

    def test_an_engineer_queues_a_drafting_job(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(
            "/playbooks/drafts",
            json={
                "symptom_code": "SYM-021",
                "machine_model": "R-2000iC",
                "question": "axis 1 current above 12.5 A",
            },
        )

        assert response.status_code == 202
        row = conn.execute(
            "SELECT kind, job_class, payload, status FROM job ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row is not None
        assert row[0] == "draft"
        assert row[1] == "authoring"
        assert row[2]["question"] == "axis 1 current above 12.5 A"
        assert row[3] == "queued"

    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.SUPERVISOR, Role.OPERATOR])
    def test_nobody_else_may_fill_the_queue_the_engineer_has_to_empty(
        self, client: TestClient, conn: Connection[Any], role: Role
    ) -> None:
        _log_in(client, role)

        response = client.post(
            "/playbooks/drafts",
            json={
                "symptom_code": "SYM-021",
                "machine_model": "R-2000iC",
                "question": "axis 1 current above 12.5 A",
            },
        )

        assert response.status_code == 403
        assert conn.execute("SELECT count(*) FROM job").fetchone() == (0,)

    def test_a_request_with_no_question_is_refused_by_the_schema(self, client: TestClient) -> None:
        """SYM-021 retrieves nothing; the sentence is what retrieves the page."""
        _log_in(client, Role.ENGINEER)

        response = client.post(
            "/playbooks/drafts",
            json={"symptom_code": "SYM-021", "machine_model": "R-2000iC", "question": ""},
        )

        assert response.status_code == 422

    def test_asking_twice_gets_the_first_job_back_rather_than_a_second_one(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """ADR-040: each press costs a pass on the one GPU, and a 409 would
        teach people to press again to find out."""
        _log_in(client, Role.ENGINEER)
        body = {
            "symptom_code": "SYM-021",
            "machine_model": "R-2000iC",
            "question": "axis 1 current above 12.5 A",
        }

        first = client.post("/playbooks/drafts", json=body)
        second = client.post("/playbooks/drafts", json={**body, "question": "asked again"})

        assert first.json()["job"] == second.json()["job"]
        assert second.json()["queued_already"] is True
        assert conn.execute("SELECT count(*) FROM job WHERE kind = 'draft'").fetchone() == (1,)

    def test_a_different_symptom_is_a_different_job(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        client.post(
            "/playbooks/drafts",
            json={"symptom_code": "SYM-021", "machine_model": "R-2000iC", "question": "one"},
        )
        # Not SYM-014: the queue already holds a draft of that one, which is the
        # test below rather than this one.
        client.post(
            "/playbooks/drafts",
            json={"symptom_code": "SYM-047", "machine_model": "R-2000iC", "question": "two"},
        )

        assert conn.execute("SELECT count(*) FROM job WHERE kind = 'draft'").fetchone() == (2,)

    def test_a_draft_already_waiting_for_review_answers_the_ask(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """The screen hides the button once a draft is waiting; this is the same
        rule at the endpoint, which `/docs` and curl also reach. A second draft
        would sit beside the first in a queue that merges nothing."""
        _log_in(client, Role.ENGINEER)

        response = client.post(
            "/playbooks/drafts",
            json={
                "symptom_code": str(SYM),
                "machine_model": str(R2000IC),
                "question": "asked while one is already waiting",
            },
        )

        assert response.status_code == 202
        assert response.json()["awaiting_review"] is True
        assert response.json()["proposal"] == setup["proposal_id"]
        assert conn.execute("SELECT count(*) FROM job WHERE kind = 'draft'").fetchone() == (0,)

    def test_a_question_of_only_spaces_is_refused(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(
            "/playbooks/drafts",
            json={"symptom_code": "SYM-021", "machine_model": "R-2000iC", "question": "   "},
        )

        assert response.status_code == 422


class TestEnergyMarksAtApproval:
    """REQ-H-05, ADR-137 B5: a playbook whose energy marks would put a hand in a
    machine that can start is not approved, whatever the reviewer clicks."""

    def test_a_restore_step_that_also_runs_the_machine_is_not_approved(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        from pdm.contracts import IsolationPoint, StepKind

        cp3 = IsolationPoint(point_id="CP-3", label="breaker CP-3", energy="electrical")
        doc = DocumentId(setup["document_id"])

        def marked(text: str, kind: StepKind) -> PlaybookStep:
            return PlaybookStep(
                text=text,
                source_doc=doc,
                page=2,
                confidence=0.8,
                kind=kind,
                isolation_points=(cp3,),
            )

        proposal = playbooks.add_proposal(
            conn,
            symptom_code=SymptomCode("SYM-021"),
            machine_model=R2000IC,
            origin=ProposalOrigin.DRAFTED,
            outcome="repair",
            steps=(
                marked("Open breaker CP-3 and apply a personal lock.", StepKind.ISOLATION),
                marked("Verify zero energy at CP-3.", StepKind.VERIFY),
                marked("Refit the guard, remove locks, and run the axis.", StepKind.RESTORE),
            ),
            tools=(),
            proposed_skill=SkillId("robot_mechanical"),
            proposed_minutes=45,
            rejected=(),
            reason="a combined restore step",
            created_at=START,
            created_by=None,
        )
        conn.commit()
        _log_in(client, Role.ENGINEER)

        response = client.post(f"/playbooks/queue/{proposal.proposal_id}/approve", json={})

        assert response.status_code == 422
        assert "เดินเครื่องในขั้นเดียว" in response.json()["detail"]
        assert playbooks.get(conn, SymptomCode("SYM-021"), R2000IC) is None

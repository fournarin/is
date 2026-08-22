"""What the review screen needs from the API, and what it may never be given.

Slice 10.2's argument is that ADR-003 stands or falls on this screen: the whole
design rests on an engineer approving every playbook before a technician sees it,
and approval that is slow or blind is a rubber stamp. So the tests here are about
the four things that make it neither - the evidence beside the draft, the
reviewer's correction with the drafter's citation still attached, the fourth
decision (send it back), and the fact that the time a review took is recorded
without a clock ever reaching the screen (ADR-064).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.contracts import MachineModel, PlaybookStep, Role, SkillId, SymptomCode, UserId
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import ProposalOrigin
from pdm.playbooks import repo as playbooks
from pdm.retrieval import repo as index
from pdm.retrieval.domain import Chunk, IndexedPage, PageOutcome

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")
SYM = SymptomCode("SYM-014")
PASSWORD = "correct horse battery staple"
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
    Role.OPERATOR: (UserId("op-1"), "Malee"),
}

PAGE_142 = (
    "Stop the robot using the emergency stop button, then apply lockout per the "
    "site procedure. Isolate breaker CP-3 before opening any cover."
)


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def setup(database_url: str, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """Two manuals, one indexed page, one drafted proposal and one objection.

    The draft cites the R-2000iC manual twice and the M-710iC manual once, which
    is the case the screen exists to catch: authoring is tuned for recall
    (ADR-015), so a draft mixing two documents is an ordinary outcome and the
    step-level citation is the only place it shows.
    """
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
        manual = library.add(
            conn,
            content=b"%PDF-1.7 the R-2000iC manual",
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000IC,
            title="R-2000iC Maintenance Manual",
            uploaded_by=UserId("op-1"),
        )
        other = library.add(
            conn,
            content=b"%PDF-1.7 the M-710iC manual",
            filename="m-710ic.pdf",
            content_type="application/pdf",
            machine_model=M710IC,
            title="M-710iC Maintenance Manual",
            uploaded_by=UserId("op-1"),
        )
        index.replace_pages(
            conn,
            manual.document_id,
            [
                IndexedPage(
                    document_id=manual.document_id,
                    page=142,
                    outcome=PageOutcome.TEXT,
                    characters=len(PAGE_142),
                ),
                # A scan: in the index, and with nothing to show. The screen has
                # to say which of the two it is (principle 5).
                IndexedPage(
                    document_id=manual.document_id,
                    page=143,
                    outcome=PageOutcome.NO_TEXT,
                    characters=0,
                ),
            ],
        )
        index.insert_chunks(
            conn,
            [Chunk(document_id=manual.document_id, page=142, ordinal=0, text=PAGE_142)],
        )
        drafted = playbooks.add_proposal(
            conn,
            symptom_code=SYM,
            machine_model=R2000IC,
            origin=ProposalOrigin.DRAFTED,
            outcome="repair",
            steps=(
                PlaybookStep(
                    text="Stop the robot using the emergency stop button",
                    source_doc=manual.document_id,
                    page=142,
                    confidence=0.9,
                ),
                PlaybookStep(
                    text="Isolate breaker CP-3 before opening any cover.",
                    source_doc=manual.document_id,
                    page=142,
                    confidence=0.8,
                ),
                PlaybookStep(
                    text="Remove the fan cover.",
                    source_doc=other.document_id,
                    page=88,
                    confidence=0.4,
                ),
            ),
            tools=("torque wrench 5-60 Nm",),
            proposed_skill=SkillId("robot_mechanical"),
            proposed_minutes=45,
            rejected=(),
            reason="3 steps from the R-2000iC manual",
            created_at=START,
            created_by=None,
        )
        objection = playbooks.add_proposal(
            conn,
            symptom_code=SymptomCode("SYM-031"),
            machine_model=R2000IC,
            origin=ProposalOrigin.TECHNICIAN,
            outcome="objection",
            steps=(),
            tools=(),
            proposed_skill=None,
            proposed_minutes=None,
            rejected=(),
            reason="step 4 sets the tension before the belt is refitted",
            created_at=START,
            created_by=UserId("tech-1"),
        )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {
            "pool": pool,
            "library": library,
            "clock": clock,
            "proposal_id": drafted.proposal_id,
            "objection_id": objection.proposal_id,
            "document_id": manual.document_id,
            "other_document_id": other.document_id,
            "steps": drafted.steps,
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


class TestTheEvidenceBesideTheDraft:
    """Draft on the left, the page it came from on the right, one screen."""

    def test_the_page_arrives_as_text_with_the_manual_it_belongs_to(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(f"/documents/{setup['document_id']}/pages/142")

        assert response.status_code == 200
        body = response.json()
        assert body["text"] == PAGE_142
        assert body["machine_model"] == R2000IC
        assert body["title"] == "R-2000iC Maintenance Manual"
        assert body["outcome"] == "text"
        assert body["withdrawn"] is False

    def test_the_step_from_another_model_carries_that_models_manual(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """The line ADR-015 does not relax. A candidate drafted from another
        model's manual has to be labelled, and the label is only possible
        because the evidence says which model the document is for - which has to
        hold whether or not there is any text beside it."""
        _log_in(client, Role.ENGINEER)

        response = client.get(f"/documents/{setup['other_document_id']}/pages/88")

        assert response.status_code == 200
        body = response.json()
        assert body["machine_model"] == M710IC
        # Nothing was ever ingested from this manual. That is a third answer,
        # distinct from a scan and from a damaged page, and the reviewer is owed
        # it rather than a blank panel (principle 5).
        assert body["outcome"] == "not_indexed"
        assert body["text"] is None

    def test_a_document_that_does_not_exist_is_still_a_404(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        assert client.get(f"/documents/{'c' * 64}/pages/1").status_code == 404

    def test_a_scan_says_it_is_a_scan_rather_than_showing_an_empty_panel(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        body = client.get(f"/documents/{setup['document_id']}/pages/143").json()

        assert body["outcome"] == "no_text"
        assert body["text"] is None

    def test_reading_a_page_needs_a_session_and_is_logged(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """Same material as the file route, same control (ADR-019)."""
        signed_out = client.get(f"/documents/{setup['document_id']}/pages/142")
        _log_in(client, Role.TECHNICIAN)
        client.get(f"/documents/{setup['document_id']}/pages/142")

        assert signed_out.status_code == 401
        row = conn.execute(
            "SELECT user_id, allowed FROM access_log WHERE action = 'read_page_text' "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row == ("tech-1", True)


class TestEditAndApprove:
    def test_the_reviewers_words_are_served_with_the_drafters_citation(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        rewritten = [
            "Stop the robot using the emergency stop button.",
            "Isolate breaker CP-3 and apply your personal lock before opening any cover.",
            "Remove the fan cover.",
        ]

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve", json={"steps": rewritten}
        )

        assert response.status_code == 200
        served = playbooks.get(conn, SYM, R2000IC)
        assert served is not None
        playbook, _ = served
        assert [step.text for step in playbook.steps] == rewritten
        # The provenance is the drafter's, on every step, including the two the
        # reviewer rewrote (invariant 4, ADR-064).
        assert [step.page for step in playbook.steps] == [142, 142, 88]
        assert playbook.steps[2].source_doc == setup["other_document_id"]

    def test_the_difference_is_stored_where_it_can_be_read_back(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """The playbook table is overwritten on the next approval (ADR-018), so
        what a person changed has to live on the proposal or nowhere."""
        _log_in(client, Role.ENGINEER)
        rewritten = [
            setup["steps"][0].text,
            "Isolate breaker CP-3 and apply your personal lock before opening any cover.",
            setup["steps"][2].text,
        ]

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={"steps": rewritten})

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None
        assert len(decided.edits) == 1
        assert decided.edits[0].index == 1
        assert decided.edits[0].before == setup["steps"][1].text
        assert decided.edits[0].after == rewritten[1]
        assert decided.decided_by == "eng-1"

    def test_approving_untouched_records_no_edit(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """The edit rate is only worth anything if "approved as drafted" is
        distinguishable from "approved after rewriting every step"."""
        _log_in(client, Role.ENGINEER)

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None and decided.edits == ()

    def test_a_step_cannot_be_dropped_on_the_way_through(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"steps": ["Stop the robot.", "Remove the fan cover."]},
        )

        assert response.status_code == 422
        still = playbooks.proposal(conn, setup["proposal_id"])
        assert still is not None and still.status.value == "pending"
        assert playbooks.get(conn, SYM, R2000IC) is None

    def test_a_blank_step_is_refused_before_anything_is_claimed(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/approve",
            json={"steps": ["Stop the robot.", "   ", "Remove the fan cover."]},
        )

        assert response.status_code == 422
        still = playbooks.proposal(conn, setup["proposal_id"])
        assert still is not None and still.status.value == "pending"


class TestSendingADraftBack:
    def test_the_note_becomes_the_question_the_next_draft_is_asked(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        note = "this is the belt procedure, not the motor one - draft from page 96"

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": note}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "sent_back"
        job = conn.execute(
            "SELECT payload FROM job WHERE kind = 'draft' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert job is not None
        assert job[0]["question"] == note
        assert job[0]["symptom_code"] == SYM

    def test_the_refusal_and_the_request_are_one_transaction(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """ADR-017 in the small: a refusal recorded without the job that answers
        it leaves a symptom with nothing to serve and nothing coming."""
        _log_in(client, Role.ENGINEER)

        client.post(
            f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": "wrong page"}
        )

        decided = playbooks.proposal(conn, setup["proposal_id"])
        queued = conn.execute("SELECT count(*) FROM job WHERE kind = 'draft'").fetchone()
        assert decided is not None and decided.status.value == "sent_back"
        assert decided.decision_note == "wrong page"
        assert queued == (1,)

    def test_sending_the_same_draft_back_twice_is_refused(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        client.post(
            f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": "wrong page"}
        )

        again = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": "still wrong"}
        )

        assert again.status_code == 409

    def test_a_technicians_objection_cannot_be_sent_back_to_a_drafter(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """It came from somebody standing at the machine (ADR-038 section 4).
        Answering it with a drafting job files the model's opinion as a reply."""
        _log_in(client, Role.ENGINEER)

        response = client.post(
            f"/playbooks/queue/{setup['objection_id']}/send-back", json={"note": "redraft it"}
        )

        assert response.status_code == 422
        still = playbooks.proposal(conn, setup["objection_id"])
        assert still is not None and still.status.value == "pending"

    def test_an_empty_note_is_refused(self, client: TestClient, setup: dict[str, Any]) -> None:
        _log_in(client, Role.ENGINEER)

        assert (
            client.post(
                f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": "   "}
            ).status_code
            == 422
        )

    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.SUPERVISOR, Role.OPERATOR])
    def test_only_an_engineer_may_send_a_draft_back(
        self, client: TestClient, setup: dict[str, Any], role: Role
    ) -> None:
        _log_in(client, role)

        response = client.post(
            f"/playbooks/queue/{setup['proposal_id']}/send-back", json={"note": "wrong page"}
        )

        assert response.status_code == 403


class TestTheTimeIsRecordedAndNeverShown:
    def test_opening_the_detail_stamps_when_it_was_opened(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        client.get(f"/playbooks/queue/{setup['proposal_id']}")

        opened = playbooks.proposal(conn, setup["proposal_id"])
        assert opened is not None and opened.opened_at == START

    def test_the_detail_carries_no_clock_for_a_screen_to_render(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """A visible timer pressures somebody reviewing safety-critical text into
        hurrying, which buys a better number and a worse review. The screen
        cannot show what the API does not send (ADR-064)."""
        _log_in(client, Role.ENGINEER)

        body = client.get(f"/playbooks/queue/{setup['proposal_id']}").json()

        assert "opened_at" not in body
        assert "review_seconds" not in body

    def test_the_decision_records_how_long_it_took(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        client.get(f"/playbooks/queue/{setup['proposal_id']}")
        setup["clock"].advance(timedelta(seconds=95))

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None and decided.review_seconds == 95

    def test_reopening_measures_the_sitting_the_decision_was_made_in(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """Opened on Monday, opened again on Thursday and decided in two minutes
        is a two-minute review, not a three-day one."""
        _log_in(client, Role.ENGINEER)
        client.get(f"/playbooks/queue/{setup['proposal_id']}")
        setup["clock"].advance(timedelta(days=3))
        # The session from Monday is long gone: 12 hours (ADR-036), which is
        # itself part of why a review is a sitting rather than a span of days.
        _log_in(client, Role.ENGINEER)
        client.get(f"/playbooks/queue/{setup['proposal_id']}")
        setup["clock"].advance(timedelta(seconds=120))

        client.post(f"/playbooks/queue/{setup['proposal_id']}/dismiss", json={"note": "duplicate"})

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None and decided.review_seconds == 120

    def test_a_decision_made_without_opening_it_says_so_rather_than_reading_zero(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        """Null is the honest answer: nobody looked at the evidence panel, which
        is exactly the thing ADR-003 asks this screen to make visible."""
        _log_in(client, Role.ENGINEER)

        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None and decided.review_seconds is None

    def test_reading_a_decided_proposal_does_not_restate_when_it_was_opened(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)
        client.get(f"/playbooks/queue/{setup['proposal_id']}")
        setup["clock"].advance(timedelta(seconds=60))
        client.post(f"/playbooks/queue/{setup['proposal_id']}/approve", json={})
        setup["clock"].advance(timedelta(days=1))

        client.get(f"/playbooks/queue/{setup['proposal_id']}")

        decided = playbooks.proposal(conn, setup["proposal_id"])
        assert decided is not None and decided.opened_at == START
        assert decided.review_seconds == 60

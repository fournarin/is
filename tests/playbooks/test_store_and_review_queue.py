"""The playbook store, against a real PostgreSQL (ADR-031, ADR-038).

Three invariants live or die here and each has its own class below:

  * **3** - a draft is never served at runtime, not even when there is nothing
    else to give the technician;
  * **4** - every step in an approved playbook carries its source and page;
  * **6** - only an engineer may approve, and the refusal happens at the
    endpoint rather than by hiding a button (the endpoint half is in
    `tests/api/`; this file covers the service, which the worker and the seed
    script call and which no endpoint stands in front of).

The interesting cases are the ones where the system has nothing good to offer:
no playbook, a flagged playbook, a proposal with no steps. Those are the paths
that first execute in front of a technician if a test does not reach them.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect, errors
from psycopg.types.json import Jsonb

from pdm.contracts import (
    DocumentId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.platform.auth import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import PlaybookStore, ProposalOrigin
from pdm.playbooks import repo as playbooks
from pdm.playbooks.repo import NothingToApply
from pdm.playbooks.service import NotAnEngineer

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
R2000IC = MachineModel("R-2000iC")
SYM = SymptomCode("SYM-014")
ENGINEER = UserId("eng-1")
TECHNICIAN = UserId("tech-1")
SKILL = SkillId("robot_mechanical")


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE playbook_proposal, playbook, chunk, document_page, document, "
            "access_log, session, account CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(START)


@pytest.fixture
def store(clock: SimulatedClock) -> PlaybookStore:
    return PlaybookStore(clock)


@pytest.fixture
def people(conn: Connection[Any], clock: SimulatedClock) -> None:
    """An engineer and a technician, because approvals reference real accounts.

    A foreign key rather than a free-text name: an approved playbook that names
    somebody the system has never heard of is not evidence of anything (ADR-024).
    """
    auth = Authentication(LocalAccounts(), clock)
    auth.create_account(
        conn, user=ENGINEER, display_name="An Engineer", role=Role.ENGINEER, password="x" * 12
    )
    auth.create_account(
        conn, user=TECHNICIAN, display_name="A Technician", role=Role.TECHNICIAN, password="y" * 12
    )


@pytest.fixture
def manual(conn: Connection[Any], tmp_path: Path, clock: SimulatedClock) -> DocumentId:
    """A document row, because a playbook's citation is a foreign key."""
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    document = library.add(
        conn,
        content=b"%PDF-1.4 a manual",
        filename="r-2000ic.pdf",
        content_type="application/pdf",
        machine_model=R2000IC,
        title="R-2000iC Maintenance Manual",
        uploaded_by=UserId("op-1"),
        edition="Edition 3",
    )
    return document.document_id


def _steps(manual: DocumentId, *texts: str) -> tuple[PlaybookStep, ...]:
    return tuple(
        PlaybookStep(text=text, source_doc=manual, page=4, confidence=0.8) for text in texts
    )


def _file_a_draft(
    conn: Connection[Any],
    manual: DocumentId,
    *,
    steps: tuple[PlaybookStep, ...] | None = None,
    outcome: str = "repair",
    reason: str = "6 steps from page 4",
    minutes: int | None = 45,
    skill: SkillId | None = SKILL,
    at: datetime = START,
) -> int:
    proposal = playbooks.add_proposal(
        conn,
        symptom_code=SYM,
        machine_model=R2000IC,
        origin=ProposalOrigin.DRAFTED,
        outcome=outcome,
        steps=_steps(manual, "Isolate the cell.", "Remove the belt guard.")
        if steps is None
        else steps,
        tools=("torque wrench 5-60 Nm",),
        proposed_skill=skill,
        proposed_minutes=minutes,
        rejected=(),
        reason=reason,
        created_at=at,
        created_by=None,
    )
    return proposal.proposal_id


class TestNothingUnapprovedIsEverServed:
    """Invariant 3, which this schema makes structural (ADR-038)."""

    def test_a_pending_proposal_is_not_a_playbook(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId
    ) -> None:
        _file_a_draft(conn, manual)

        assert store.serve(conn, SYM, R2000IC) is None

    def test_the_served_table_refuses_a_draft_outright(
        self, conn: Connection[Any], manual: DocumentId, people: None
    ) -> None:
        """The other half: even asked directly, the row cannot be written.

        `PlaybookDraft.into_playbook` produces a `draft` object for the review
        screen to render. If that object could be saved, invariant 3 would be one
        careless call away from failing.
        """
        draft = Playbook(
            symptom_code=SYM,
            machine_model=R2000IC,
            steps=_steps(manual, "Isolate the cell."),
            estimated_minutes=45,
            required_skill=SKILL,
            source_doc=manual,
            page=4,
            status=PlaybookStatus.DRAFT,
        )
        with pytest.raises(ValueError, match="no draft rows"):
            playbooks.save_approved(
                conn, draft, approved_by=ENGINEER, approved_at=START, approver_role=Role.ENGINEER
            )

    def test_the_table_itself_refuses_a_draft_whoever_writes_it(
        self, conn: Connection[Any], manual: DocumentId, people: None
    ) -> None:
        """The third half, and the one that does not depend on a code path.

        `save_approved` refusing a draft is a rule in Python, which holds for
        callers that go through it. The seed scripts, a migration, a repair
        session with `psql` open and a production incident in progress - none of
        them do. This asserts what the CHECK constraint does: the `draft` status
        is a state the served table cannot hold at all, which is what ADR-038
        claims and what makes invariant 3 structural rather than remembered.

        It is written as raw SQL on purpose. Going through the repo would test
        the repo again; the point here is the database refusing an INSERT that
        no Python in this repository would make.
        """
        with pytest.raises(errors.CheckViolation), conn.transaction():
            conn.execute(
                """
                INSERT INTO playbook (
                    symptom_code, machine_model, steps, estimated_minutes,
                    required_skill, source_doc, page, cited_documents,
                    status, approved_by, approved_at, approver_role
                )
                VALUES (%s, %s, %s, 45, %s, %s, 4, %s,
                        'draft', %s, %s, 'engineer')
                """,
                (
                    SYM,
                    R2000IC,
                    Jsonb([{"text": "Isolate the cell.", "source_doc": manual, "page": 4}]),
                    SKILL,
                    manual,
                    [manual],
                    ENGINEER,
                    START,
                ),
            )

    def test_the_same_insert_succeeds_once_the_status_is_approved(
        self, conn: Connection[Any], manual: DocumentId, people: None
    ) -> None:
        """Otherwise the refusal above could be about anything.

        A typo in a column name, a missing foreign key, a constraint on some
        other field: all of them would raise, and the test above would pass
        while proving nothing about `status`. This is the same statement with
        one word changed.
        """
        conn.execute(
            """
            INSERT INTO playbook (
                symptom_code, machine_model, steps, estimated_minutes,
                required_skill, source_doc, page, cited_documents,
                status, approved_by, approved_at, approver_role
            )
            VALUES (%s, %s, %s, 45, %s, %s, 4, %s,
                    'approved', %s, %s, 'engineer')
            """,
            (
                SYM,
                R2000IC,
                Jsonb([{"text": "Isolate the cell.", "source_doc": manual, "page": 4}]),
                SKILL,
                manual,
                [manual],
                ENGINEER,
                START,
            ),
        )

        with conn.cursor() as cur:
            cur.execute("SELECT status FROM playbook WHERE symptom_code = %s", (SYM,))
            assert cur.fetchall() == [("approved",)]

    def test_a_symptom_with_no_playbook_answers_nothing_rather_than_something_close(
        self, conn: Connection[Any], store: PlaybookStore
    ) -> None:
        assert store.serve(conn, SymptomCode("SYM-031"), R2000IC) is None


class TestOnlyAnEngineerApproves:
    """Invariant 6, at the service. The endpoint half is in tests/api/."""

    def test_a_technician_is_refused(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)

        with pytest.raises(NotAnEngineer):
            store.approve(conn, proposal_id, approver=TECHNICIAN, approver_role=Role.TECHNICIAN)

    def test_the_refusal_leaves_the_queue_and_the_table_untouched(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """The check runs before anything is written, not after.

        A refusal that had already applied the proposal would leave the row
        approved and the queue closed, with only the exception to say otherwise.
        """
        proposal_id = _file_a_draft(conn, manual)

        with pytest.raises(NotAnEngineer):
            store.approve(conn, proposal_id, approver=TECHNICIAN, approver_role=Role.TECHNICIAN)

        assert store.serve(conn, SYM, R2000IC) is None
        assert [item.proposal_id for item in store.review_queue(conn)] == [proposal_id]

    def test_a_supervisor_is_refused_too(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-024 gives a supervisor authority over scheduling, not over
        content. The two are different questions and this is the one where a
        wrong answer is a torque figure."""
        proposal_id = _file_a_draft(conn, manual)

        with pytest.raises(NotAnEngineer):
            store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.SUPERVISOR)


class TestApprovalWritesTheRowAndClosesTheProposal:
    def test_the_playbook_becomes_servable(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)

        approved = store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        assert approved.status is PlaybookStatus.APPROVED
        assert approved.revision == 1
        served = store.serve(conn, SYM, R2000IC)
        assert served is not None
        assert served.warning is None
        assert served.is_current

    def test_the_approval_records_who_when_and_as_what(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-024: the role held at the moment of approval, not the current one."""
        proposal_id = _file_a_draft(conn, manual)

        approved = store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        assert approved.approved_by == ENGINEER
        assert approved.approved_at == START
        assert approved.approver_role is Role.ENGINEER

    def test_approving_twice_over_the_same_pair_increments_the_revision(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-018: approval overwrites, there is no chain and no supersedes."""
        first = _file_a_draft(conn, manual)
        store.approve(conn, first, approver=ENGINEER, approver_role=Role.ENGINEER)

        second = _file_a_draft(conn, manual, reason="a second look")
        again = store.approve(conn, second, approver=ENGINEER, approver_role=Role.ENGINEER)

        assert again.revision == 2

    def test_the_same_proposal_cannot_be_approved_twice(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)
        store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        with pytest.raises(NothingToApply):
            store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)


class TestWhatCannotBeApproved:
    def test_a_withheld_draft_has_nothing_to_apply(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """It is in the queue so a person sees it, and it is not a playbook.

        ADR-037 withholds the whole draft when a step fails the gate; the row
        exists so the reviewer learns the backend is fabricating, not so that
        somebody can press approve on an empty procedure.
        """
        proposal_id = _file_a_draft(
            conn, manual, steps=(), outcome="withheld", reason="1 of 4 steps failed the gate"
        )

        with pytest.raises(NothingToApply, match="0 step"):
            store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

    def test_a_proposal_stating_no_duration_needs_the_engineer_to_supply_one(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-037 section 8: no figure is invented on the way in.

        `estimated_minutes` is what the scheduler computes with. A default here
        would carry the authority of the manual and the provenance of nothing.
        """
        proposal_id = _file_a_draft(conn, manual, minutes=None)

        with pytest.raises(ValueError, match="no duration"):
            store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

    def test_and_accepts_it_when_the_engineer_does(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual, minutes=None)

        approved = store.approve(
            conn,
            proposal_id,
            approver=ENGINEER,
            approver_role=Role.ENGINEER,
            estimated_minutes=50,
        )

        assert approved.estimated_minutes == 50


class TestTheQueue:
    def test_both_origins_arrive_in_one_list(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """design.md 4: one queue, because one engineer opens one box."""
        _file_a_draft(conn, manual)
        playbooks.add_proposal(
            conn,
            symptom_code=SYM,
            machine_model=R2000IC,
            origin=ProposalOrigin.TECHNICIAN,
            outcome="objection",
            steps=_steps(manual, "The guard bolts are M8 on this cell, not M6."),
            tools=(),
            proposed_skill=None,
            proposed_minutes=None,
            rejected=(),
            reason="reported from the floor",
            created_at=START + timedelta(hours=1),
            created_by=TECHNICIAN,
        )

        queue = store.review_queue(conn)

        assert [item.origin for item in queue] == [
            ProposalOrigin.DRAFTED,
            ProposalOrigin.TECHNICIAN,
        ]

    def test_the_oldest_is_first_so_the_bottom_is_reachable(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId
    ) -> None:
        recent = _file_a_draft(conn, manual, at=START + timedelta(days=1))
        old = _file_a_draft(conn, manual, at=START - timedelta(days=20))

        assert [item.proposal_id for item in store.review_queue(conn)] == [old, recent]

    def test_approving_one_does_not_close_the_technicians_objection(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-038 section 4, and the reason it is written down.

        A re-draft that quietly dismissed the objection would lose the one report
        in this system that came from somebody standing at the machine.
        """
        objection = playbooks.add_proposal(
            conn,
            symptom_code=SYM,
            machine_model=R2000IC,
            origin=ProposalOrigin.TECHNICIAN,
            outcome="objection",
            steps=_steps(manual, "The guard bolts are M8 on this cell."),
            tools=(),
            proposed_skill=None,
            proposed_minutes=None,
            rejected=(),
            reason="reported from the floor",
            created_at=START,
            created_by=TECHNICIAN,
        )
        redraft = _file_a_draft(conn, manual, at=START + timedelta(days=1))

        store.approve(conn, redraft, approver=ENGINEER, approver_role=Role.ENGINEER)

        still_pending = [item.proposal_id for item in store.review_queue(conn)]
        assert still_pending == [objection.proposal_id]

    def test_a_dismissal_has_to_say_why(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)

        with pytest.raises(ValueError, match="say why"):
            store.dismiss(
                conn, proposal_id, decided_by=ENGINEER, decided_role=Role.ENGINEER, note="  "
            )

    def test_a_dismissed_proposal_is_kept_with_its_reason(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """Nothing is deleted (ADR-038 section 6).

        In aggregate these are the only signal that a backend has started
        fabricating, and individually they answer "why does this symptom still
        have no playbook when three people have looked at it".
        """
        proposal_id = _file_a_draft(conn, manual)

        store.dismiss(
            conn,
            proposal_id,
            decided_by=ENGINEER,
            decided_role=Role.ENGINEER,
            note="drafted from the overview page, not the procedure",
        )

        kept = playbooks.proposal(conn, proposal_id)
        assert kept is not None
        assert kept.status.value == "dismissed"
        assert kept.decision_note is not None and "overview" in kept.decision_note
        assert kept.decided_by == ENGINEER
        assert store.review_queue(conn) == []


class TestWhenTheManualIsReplaced:
    """ADR-018: still served, with a warning, until somebody re-approves."""

    def test_every_playbook_citing_it_is_flagged(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)
        store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        touched = playbooks.flag_for_review(conn, manual, reason="Edition 4 replaced Edition 3")

        assert touched == [SYM]

    def test_a_flagged_playbook_is_still_served_and_says_so(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """A technician with an out-of-date procedure is better off than one with
        none - but only if the screen tells them which they have."""
        proposal_id = _file_a_draft(conn, manual)
        store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)
        playbooks.flag_for_review(conn, manual, reason="Edition 4 replaced Edition 3")

        served = store.serve(conn, SYM, R2000IC)

        assert served is not None
        assert not served.is_current
        assert served.warning == "Edition 4 replaced Edition 3"

    def test_a_playbook_citing_a_different_manual_is_left_alone(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        proposal_id = _file_a_draft(conn, manual)
        store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        touched = playbooks.flag_for_review(
            conn, DocumentId("f" * 64), reason="something else was replaced"
        )

        assert touched == []
        served = store.serve(conn, SYM, R2000IC)
        assert served is not None and served.is_current

    def test_re_approving_clears_the_warning(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        first = _file_a_draft(conn, manual)
        store.approve(conn, first, approver=ENGINEER, approver_role=Role.ENGINEER)
        playbooks.flag_for_review(conn, manual, reason="Edition 4 replaced Edition 3")

        second = _file_a_draft(conn, manual, reason="drafted from the new edition")
        store.approve(conn, second, approver=ENGINEER, approver_role=Role.ENGINEER)

        served = store.serve(conn, SYM, R2000IC)
        assert served is not None
        assert served.is_current
        assert served.warning is None


class TestWhatTheCodeReviewFound:
    """Four cases that passed every earlier test and were wrong anyway."""

    def test_a_skill_the_plant_does_not_declare_is_refused_at_approval(
        self, conn: Connection[Any], clock: SimulatedClock, manual: DocumentId, people: None
    ) -> None:
        """Invariant 13, on the other way in.

        `Drafting` drops a label the config does not know; approval is where a
        person types one, and a typo there is an approved playbook dispatch can
        never assign to anybody.
        """
        store = PlaybookStore(clock, skills={"robot_mechanical", "electrical"})
        proposal_id = _file_a_draft(conn, manual, skill=None)

        with pytest.raises(ValueError, match="not one of the skills"):
            store.approve(
                conn,
                proposal_id,
                approver=ENGINEER,
                approver_role=Role.ENGINEER,
                required_skill=SkillId("robot_mechnical"),
            )

    def test_the_proposal_is_claimed_before_the_playbook_is_written(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """Order matters because the API commits on an HTTPException.

        Two engineers approving the same proposal: the loser gets a 409, and the
        transaction it arrived in still commits so the access log survives. With
        the write first, the loser's overwrite - a revision bump under their name
        - would have committed with it.
        """
        proposal_id = _file_a_draft(conn, manual)
        store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)
        first = playbooks.get(conn, SYM, R2000IC)

        with pytest.raises(NothingToApply):
            store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        after = playbooks.get(conn, SYM, R2000IC)
        assert first is not None and after is not None
        assert after[0].revision == first[0].revision

    def test_the_playbook_is_filed_under_the_manual_most_of_its_steps_came_from(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """Not under whatever the first step happens to cite.

        "Isolate the cell following the procedure on page 2" is an ordinary first
        step and it points at the safety section, not at the repair.
        """
        steps = (
            PlaybookStep(text="Isolate the cell.", source_doc=manual, page=2, confidence=0.6),
            PlaybookStep(text="Remove the belt guard.", source_doc=manual, page=4, confidence=0.8),
            PlaybookStep(text="Reset the tension.", source_doc=manual, page=4, confidence=0.8),
        )
        proposal_id = _file_a_draft(conn, manual, steps=steps)

        approved = store.approve(conn, proposal_id, approver=ENGINEER, approver_role=Role.ENGINEER)

        assert approved.page == 4

    def test_a_two_person_job_is_recorded_as_one(
        self, conn: Connection[Any], store: PlaybookStore, manual: DocumentId, people: None
    ) -> None:
        """ADR-025: omitting this makes load_ratio read low and the gate release
        more work than there are people for. Nothing drafts it, so the approver
        is the only person who can say."""
        proposal_id = _file_a_draft(conn, manual)

        approved = store.approve(
            conn,
            proposal_id,
            approver=ENGINEER,
            approver_role=Role.ENGINEER,
            required_technicians=2,
        )

        assert approved.required_technicians == 2

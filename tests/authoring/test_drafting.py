"""Drafting end to end on the corpus, against a real PostgreSQL (ADR-031).

The unit tests next door prove the gate can fail. This one proves the pipeline
runs: retrieval offers pages, the backend picks spans, the gate checks them, and
what comes out cites a page of a manual that is in the library.

The dense half here is `FakeEmbedder` with hand-declared vectors, as in the
hybrid search tests. That is enough to exercise the plumbing and is **not** a
measurement: the figures that get quoted come from `scripts/measure_drafting.py`
with the real model, and are written down in `docs/drafting-baseline.md`.

One test below pins a failure rather than a success. It is marked as such.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from fixtures.corpus import CORPUS, AbsentSymptom, Answer, DocumentedOnly
from pdm.authoring.drafting import (
    DraftOutcome,
    DraftResult,
    RejectionReason,
    assemble,
)
from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import DocumentId, MachineModel, SymptomCode, UserId
from pdm.contracts.wording import figures
from pdm.llm.domain import DraftRequest, Proposal, ProposalKind, ProposedStep
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import ProposalOrigin
from pdm.playbooks import repo as playbooks
from pdm.retrieval.embedding import FakeEmbedder
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import InMemoryVectorIndex

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
OPERATOR = UserId("op-1")
R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")

CONFIG = load_config(Path("config"))
AUTHORING, _ = profiles_from(CONFIG.policy.retrieval)

# Keyed on headings and on the answer key's own questions, so the meaning half
# has an opinion instead of a hash. Both manuals carry the belt heading, which is
# the point: the wrong model's page is as close as the right one, and only the
# model filter keeps it out of the draft.
_BELT = [1.0, 0.0, 0.0, 0.0]
_FAN = [0.0, 1.0, 0.0, 0.0]
_INTERLOCK = [0.0, 0.0, 1.0, 0.0]
_SERVO = [0.0, 0.0, 0.0, 1.0]

DECLARED = {
    "Belt motor overheating": _BELT,
    "belt motor running above 85 degrees": _BELT,
    "Cooling fan - speed below specification": _FAN,
    "cabinet fan slower than 1200 rpm": _FAN,
    "Safety interlocks": _INTERLOCK,
    "interlock reported open": _INTERLOCK,
    "Servo axis 1 - current above specification": _SERVO,
    "axis 1 current above 12.5 A": _SERVO,
}


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE playbook_proposal, playbook, chunk, document_page, document CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def drafting(conn: Connection[Any], tmp_path: Path) -> Drafting:
    """Both manuals of the corpus, ingested into both halves of the index."""
    hybrid = HybridSearch(FakeEmbedder(dimensions=4, declared=DECLARED), InMemoryVectorIndex())
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), SimulatedClock(START))
    ingest = Ingest(library, hybrid)

    for document in CORPUS.documents:
        row = library.add(
            conn,
            content=document.path.read_bytes(),
            filename=document.filename,
            content_type="application/pdf",
            machine_model=document.machine_model,
            title=document.title,
            uploaded_by=OPERATOR,
            edition=document.edition,
        )
        ingest.run(conn, row.document_id)

    return Drafting(hybrid, ExtractiveDrafter(), profile=AUTHORING, skills=CONFIG.skills)


class _AlwaysCitesTheOtherModel:
    """A backend that reaches for the neighbouring manual on purpose."""

    def __init__(self, document_id: DocumentId) -> None:
        self.document_id = document_id

    def propose(self, request: DraftRequest) -> Proposal:
        return Proposal(
            kind=ProposalKind.REPAIR,
            steps=(
                ProposedStep(
                    text="Retighten the motor mount bolts to 28 Nm.",
                    cites=(self.document_id, 4),
                ),
            ),
        )


def _draft(drafting: Drafting, conn: Connection[Any], symptom: str) -> DraftResult:
    """Draft the symptom using the question the answer key wrote for it."""
    entries: list[Answer | DocumentedOnly | AbsentSymptom] = [
        *CORPUS.covered,
        *CORPUS.documented_without_procedure,
        *CORPUS.absent,
    ]
    for entry in entries:
        if entry.symptom_code == symptom:
            return drafting.run(
                conn,
                symptom_code=SymptomCode(symptom),
                machine_model=entry.machine_model,
                question=entry.queries.en,
            )
    raise AssertionError(f"{symptom} is not in the answer key")


class TestARepairProcedureBecomesADraft:
    @pytest.mark.parametrize("symptom", ["SYM-014", "SYM-021", "SYM-047"])
    def test_it_drafts_from_the_page_the_answer_key_names(
        self, drafting: Drafting, conn: Connection[Any], symptom: str
    ) -> None:
        """All three, when the meaning half points at the right page.

        The declared vectors here do what a reranker would, which is why this
        passes on all three while the real model gets one of the three
        (`docs/drafting-baseline.md`). The contrast is the finding: with the
        right page in front of it the drafter is right, so what the measurement
        exposes is a ranking failure and not a drafting one.
        """
        result = _draft(drafting, conn, symptom)
        answer = CORPUS.answer(SymptomCode(symptom))

        assert result.outcome is DraftOutcome.REPAIR
        assert result.draft is not None
        assert {step.page for step in result.draft.steps} == set(answer.answer_pages)

    def test_the_draft_carries_the_tools_skill_and_duration_off_the_page(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-047")
        answer = CORPUS.answer(SymptomCode("SYM-047"))

        assert result.draft is not None
        assert result.draft.proposed_minutes == answer.estimated_minutes
        assert result.draft.proposed_skill == answer.required_skill
        assert result.draft.tools == answer.tools

    def test_the_draft_becomes_a_playbook_with_per_step_provenance(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-047")
        assert result.draft is not None

        playbook = result.draft.into_playbook()
        assert playbook.status is not None
        assert all(step.source_doc and step.page for step in playbook.steps)
        assert playbook.source_doc == CORPUS.document(M710IC).sha256


class TestEveryFigureInEveryDraftCameOffThePageItCites:
    """Invariant 5, end to end rather than on hand-written text."""

    @pytest.mark.parametrize("symptom", ["SYM-014", "SYM-021", "SYM-047", "SYM-002"])
    def test_no_step_carries_a_figure_its_page_does_not(
        self, drafting: Drafting, conn: Connection[Any], symptom: str
    ) -> None:
        result = _draft(drafting, conn, symptom)
        assert result.draft is not None

        pages = {
            (evidence.document_id, evidence.page): evidence.text
            for evidence in result.draft.cross_model_candidates
        }
        for step in result.draft.steps:
            # Read the page back out of the index rather than trusting the
            # draft: the point is that the citation resolves to text that
            # contains the figures, not that the drafter thought so.
            row = conn.execute(
                "SELECT string_agg(text, ' ' ORDER BY ordinal) FROM chunk "
                "WHERE document_id = %s AND page = %s",
                (step.source_doc, step.page),
            ).fetchone()
            assert row is not None and row[0] is not None
            pages[(step.source_doc, step.page)] = row[0]
            assert figures(step.text) <= figures(row[0])


class TestThePageThatPrescribesNothing:
    def test_the_interlock_page_drafts_as_diagnostic(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-002")

        assert result.outcome is DraftOutcome.DIAGNOSTIC
        assert result.draft is not None
        assert {step.page for step in result.draft.steps} == {11}

    def test_the_prohibition_survives_into_the_draft(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-002")
        assert result.draft is not None
        assert any("prohibited" in step.text for step in result.draft.steps)


class TestTheOtherModelsManual:
    def test_no_step_ever_cites_a_manual_for_a_different_model(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        """ADR-015's one line, on the corpus built to break it.

        Both manuals document belt-motor overheating with the same heading and
        different torque figures, so the meaning half rates them equally close.
        """
        wanted = CORPUS.document(R2000IC).sha256
        result = _draft(drafting, conn, "SYM-014")

        assert result.draft is not None
        assert {step.source_doc for step in result.draft.steps} == {wanted}

    def test_the_backend_is_never_shown_the_other_models_pages(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        """Where the rule is actually enforced, proved by trying to break it.

        A backend that asks for the other manual's page gets `not offered` rather
        than `wrong model`, and the difference is the whole point: the service
        never put that page in the request, so no backend can cite it whatever it
        decides. Asserting the drafted pages instead proves nothing here, because
        the extractive backend filters by model as well - both would have to be
        removed before that test noticed.
        """
        other = CORPUS.document(M710IC).sha256
        drafting.drafter = _AlwaysCitesTheOtherModel(other)

        result = _draft(drafting, conn, "SYM-014")

        assert result.outcome is DraftOutcome.WITHHELD
        assert result.rejected[0].reason is RejectionReason.EVIDENCE_NOT_OFFERED

    def test_the_other_models_pages_are_kept_beside_the_draft_not_dropped(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-014")

        assert result.draft is not None
        assert result.draft.cross_model_candidates
        assert all(
            candidate.machine_model == M710IC for candidate in result.draft.cross_model_candidates
        )


class TestTheSymptomNothingInTheCorpusDocuments:
    """SYM-031: the corpus says nothing about cycle time.

    Until ADR-089 this class pinned a failure: drafting produced a repair draft
    off the cabinet-fan page at a fused score of 0.95, because reciprocal rank
    fusion knows positions and not distances. It was written to fail the day
    the gap closed, and it did. What closed it is not a relevance score but
    the question: it asks about 62 seconds and no page states 62, so no page
    answers it.
    """

    def test_an_absent_symptom_asked_with_its_figure_is_not_found(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-031")

        assert result.outcome is DraftOutcome.NOT_FOUND
        assert result.draft is None

    def test_asked_without_a_figure_it_still_drafts_today(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        """The part of the gap that is still open, pinned as a gap.

        With no figure in the question nothing can tell "the manuals do not
        cover this" from "they cover it badly" (`docs/drafting-baseline.md`).
        The draft is at least real text off a real page of the right model,
        which a reviewer can reject in seconds. When a relevance magnitude
        exists this fails, and somebody has to come back and decide.
        """
        result = drafting.run(
            conn,
            symptom_code=SymptomCode("SYM-031"),
            machine_model=M710IC,
            question="cycle time is drifting upwards",
        )

        assert result.outcome is not DraftOutcome.NOT_FOUND
        assert result.draft is not None
        assert all(step.source_doc == CORPUS.document(M710IC).sha256 for step in result.draft.steps)


class TestFilingTheResultForReview:
    """The step that connects slice 3.5 to the queue (ADR-038)."""

    def test_a_repair_draft_arrives_in_the_queue_with_its_steps(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        result = _draft(drafting, conn, "SYM-047")

        filed = drafting.file(conn, result, now=START)

        assert filed.origin is ProposalOrigin.DRAFTED
        assert filed.outcome == "repair"
        assert len(filed.steps) == len(result.draft.steps if result.draft else ())
        assert filed.created_by is None

    def test_an_outcome_with_no_steps_is_filed_too(
        self, drafting: Drafting, conn: Connection[Any]
    ) -> None:
        """A silence in the queue and a gap in the manuals look identical from
        the outside, and only one of them is somebody's job to fix."""
        result = assemble(
            DraftRequest(
                symptom_code=SymptomCode("SYM-031"),
                machine_model=M710IC,
                question="cycle time drifting above 62 seconds",
                evidence=(),
            ),
            Proposal(kind=ProposalKind.NOTHING, steps=()),
        )

        filed = drafting.file(conn, result, now=START)

        assert filed.outcome == "not_found"
        assert filed.steps == ()
        assert filed.reason
        assert [item.proposal_id for item in playbooks.queue(conn)] == [filed.proposal_id]

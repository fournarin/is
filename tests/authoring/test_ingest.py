"""Ingest and sparse search, against a real PostgreSQL (ADR-031).

The generated tsvector column, `websearch_to_tsquery` and `ts_rank_cd` are the
whole of the sparse half, and none of them exists in a substitute database - so
testing this anywhere else would be testing a different system.

The tests that matter are the ones using the corpus's answer key. It was written
in slice 3.0, before any of this existed, which is what makes "the right page
came back" a result rather than a description of the output.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

import pytest
from psycopg import Connection, connect

from fixtures.corpus import CORPUS, Answer
from pdm.authoring.service import Ingest, IngestReport, UnknownDocument
from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.retrieval import repo as index
from pdm.retrieval.domain import PageOutcome

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
OPERATOR = UserId("op-1")


def _blank_pdf() -> bytes:
    """A valid one-page PDF with nothing written on it.

    What a scan looks like to a text parser: a real page that extracts to an
    empty string. Hand-writing the PDF bytes produced a file pypdf rejected
    outright, which tests the wrong thing - an unreadable file and a readable
    file with no text are different cases with different answers.
    """
    from fpdf import FPDF

    pdf = FPDF()
    pdf.add_page()
    return bytes(pdf.output())


SCANNED = _blank_pdf()


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE chunk, document_page, document CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(FilesystemObjectStore(tmp_path), SimulatedClock(START))


@pytest.fixture
def ingest(library: DocumentLibrary) -> Ingest:
    return Ingest(library)


def _load_corpus(library: DocumentLibrary, conn: Connection[Any]) -> dict[str, DocumentId]:
    """Every manual in the corpus, registered under its real content hash."""
    loaded: dict[str, DocumentId] = {}
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
        assert row.document_id == document.sha256, "the manifest hash is the document id"
        loaded[document.machine_model] = row.document_id
    return loaded


class TestIngestingTheCorpus:
    def test_every_page_is_read_and_chunked(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        ids = _load_corpus(library, conn)

        for document in CORPUS.documents:
            report = ingest.run(conn, ids[document.machine_model])

            assert report.pages == document.pages
            assert report.is_fully_readable
            assert report.coverage == 1.0
            assert report.pages_needing_ocr == ()
            assert report.chunks >= document.pages

    def test_re_ingesting_replaces_rather_than_duplicates(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """A parser change has to be safe to apply. Adding beside the old chunks
        would leave a search returning two versions of the same page with no way
        to tell which is current."""
        ids = _load_corpus(library, conn)
        document_id = ids["R-2000iC"]

        first = ingest.run(conn, document_id)
        second = ingest.run(conn, document_id)

        assert first.chunks == second.chunks
        assert len(index.pages_of(conn, document_id)) == first.pages

    def test_an_unknown_document_is_refused(self, ingest: Ingest, conn: Connection[Any]) -> None:
        with pytest.raises(UnknownDocument):
            ingest.run(conn, DocumentId("0" * 64))


class TestAPageThatGivesNothing:
    def test_a_scan_ingests_to_zero_chunks_and_says_so(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """The case ADR-034 point 3 exists for, and the one that decides what
        happens when the plant's real manuals arrive. Coverage of 0.0 with the
        page listed is a manual somebody can act on; silence would have been a
        manual the system claims to have indexed."""
        document = library.add(
            conn,
            content=SCANNED,
            filename="scan.pdf",
            content_type="application/pdf",
            machine_model=MachineModel("R-2000iC"),
            title="A scanned manual",
            uploaded_by=OPERATOR,
        )

        report = ingest.run(conn, document.document_id)

        assert report.pages == 1
        assert report.chunks == 0
        assert report.coverage == 0.0
        assert not report.is_fully_readable
        assert report.pages_needing_ocr == (1,)
        assert index.needing_ocr(conn, document.document_id) == [1]

    def test_the_page_is_recorded_even_though_it_has_no_chunks(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        document = library.add(
            conn,
            content=SCANNED,
            filename="scan.pdf",
            content_type="application/pdf",
            machine_model=MachineModel("R-2000iC"),
            title="A scanned manual",
            uploaded_by=OPERATOR,
        )
        ingest.run(conn, document.document_id)

        pages = index.pages_of(conn, document.document_id)
        assert [page.outcome for page in pages] == [PageOutcome.NO_TEXT]
        assert index.coverage(conn, document.document_id) == (0, 1)


class TestSearchFindsWhatTheAnswerKeySays:
    """The sparse baseline, measured against the key written in slice 3.0.

    Ranks are asserted exactly rather than as "somewhere in the top few". They
    are the number 3.3 has to improve on, and a test that accepts any position
    in the top eight would let hybrid retrieval be declared better without
    anything having changed.
    """

    # Measured, not hoped for. SYM-014 sits at 2 because page 3 - the overview -
    # repeats the question's words ("motor running above 85 degrees") while
    # page 4 is the procedure that answers it. That is precisely the failure
    # reranking exists to fix, and it belongs in a test rather than in a note.
    ENGLISH_RANK: ClassVar[dict[str, int]] = {"SYM-014": 2, "SYM-021": 1, "SYM-047": 1}

    # The same query in Thai. Not zero, which is the surprise: the figures in a
    # technical question survive tokenisation, and on this corpus every symptom
    # is defined by a threshold. It is the numerals doing the work, not the
    # language, and it collapses on any question without one (ADR-034).
    THAI_RANK: ClassVar[dict[str, int]] = {"SYM-014": 2, "SYM-021": 1, "SYM-047": 1}

    @pytest.fixture(autouse=True)
    def corpus_in_the_index(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        for document_id in _load_corpus(library, conn).values():
            ingest.run(conn, document_id)

    @staticmethod
    def _rank_of_answer(hits: list[Any], answer: Answer) -> int | None:
        for position, hit in enumerate(hits, start=1):
            if hit.chunk.page in answer.answer_pages:
                return position
        return None

    @pytest.mark.parametrize("answer", CORPUS.covered, ids=lambda a: a.symptom_code)
    def test_the_english_query_ranks_the_answer_page_where_it_was_measured(
        self, conn: Connection[Any], answer: Answer
    ) -> None:
        hits = index.search(conn, answer.queries.en, machine_model=answer.machine_model)

        assert self._rank_of_answer(hits, answer) == self.ENGLISH_RANK[answer.symptom_code]

    @pytest.mark.parametrize("answer", CORPUS.covered, ids=lambda a: a.symptom_code)
    def test_a_thai_query_gets_there_on_the_numbers_alone(
        self, conn: Connection[Any], answer: Answer
    ) -> None:
        """ADR-034 point 4. The sparse half does not understand the question; it
        matches the figures in it. Recorded so that "sparse handles Thai" is not
        read into this later - a Thai question with no number in it finds
        nothing, and the cross-lingual job stays the embedding model's."""
        hits = index.search(conn, answer.queries.th, machine_model=answer.machine_model)

        assert self._rank_of_answer(hits, answer) == self.THAI_RANK[answer.symptom_code]

    def test_a_thai_question_without_a_number_finds_nothing(self, conn: Connection[Any]) -> None:
        """The other half of the same point, and the one that shows the first
        result is not comprehension."""
        assert index.search(conn, "สายพานหลวมต้องทำอย่างไร") == []

    def test_one_missing_word_no_longer_removes_the_answer(self, conn: Connection[Any]) -> None:
        """Under AND semantics this returned nothing at all: the question says
        "slower", the page says "below". ADR-015 puts recall first at authoring,
        so terms are joined with OR."""
        hits = index.search(
            conn, "cabinet fan slower than 1200 rpm", machine_model=MachineModel("M-710iC")
        )

        assert hits and hits[0].chunk.page == 5

    def test_a_search_can_cross_models_and_can_be_told_not_to(self, conn: Connection[Any]) -> None:
        """ADR-015: authoring should see the candidate from the wrong manual so
        a reviewer can be shown it and reject it. Runtime must not serve one."""
        query = "belt motor overheating procedure"

        everywhere = index.search(conn, query)
        one_model = index.search(conn, query, machine_model=MachineModel("R-2000iC"))

        assert {hit.machine_model for hit in everywhere} == {"R-2000iC", "M-710iC"}
        assert {hit.machine_model for hit in one_model} == {"R-2000iC"}

    def test_a_hit_says_which_manual_it_came_from(self, conn: Connection[Any]) -> None:
        """The review screen has to make "this is from the other model"
        impossible to miss, and a hit that knows only its document id cannot say
        so (ADR-015)."""
        hit = index.search(conn, "cabinet fan below 1200 rpm")[0]

        assert hit.title
        assert hit.machine_model
        assert hit.score > 0

    def test_the_declared_gap_is_a_matter_of_score_not_emptiness(
        self, conn: Connection[Any]
    ) -> None:
        """The gap from slice 3.0, reached for the first time - and it does not
        behave the way the plan assumed.

        With terms joined by OR a search is almost never empty, so the symptom
        the manual says nothing about still returns pages. What separates them
        is the score: an order of magnitude below a symptom the manual
        documents. "Not found - ask an engineer" is therefore a threshold
        decision, which is what the profiles in policy.yaml are for, applied
        after fusion where the scores are comparable (ADR-034).
        """
        absent = CORPUS.absent[0]
        documented = CORPUS.covered[0]

        noise = index.search(conn, absent.queries.en, machine_model=absent.machine_model)
        answer = index.search(conn, documented.queries.en, machine_model=documented.machine_model)

        assert noise, "OR semantics mean this is not empty, which is the point"
        assert answer[0].score > noise[0].score * 5


class TestWithdrawingTakesAManualOutOfTheIndex:
    def test_the_chunks_go_and_the_file_stays(
        self, ingest: Ingest, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """design.md section 5: removed from the index for real, file kept,
        because playbook_snapshot cites its pages (ADR-019)."""
        ids = _load_corpus(library, conn)
        document_id = ids["R-2000iC"]
        report = ingest.run(conn, document_id)

        document = library.get(conn, document_id)
        assert document is not None
        removed = ingest.withdraw(conn, document)
        library.withdraw(conn, document_id)

        assert removed == report.chunks
        assert index.pages_of(conn, document_id) == []
        assert index.search(conn, "belt motor overheating") == []
        assert library.is_intact(document)
        with library.open(document) as handle:
            assert handle.read()[:4] == b"%PDF"


def test_the_report_reads_as_a_fraction_of_the_manual() -> None:
    """Coverage travels with every retrieval figure measured on real manuals,
    so the number has to be right on its own (ADR-034)."""
    report = IngestReport(
        document_id=DocumentId("a" * 64),
        pages=200,
        pages_with_text=83,
        chunks=210,
        pages_needing_ocr=tuple(range(84, 201)),
    )

    assert report.coverage == pytest.approx(0.415)
    assert not report.is_fully_readable

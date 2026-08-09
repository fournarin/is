"""Hybrid search and its two profiles, against a real PostgreSQL (ADR-015, ADR-035).

The embedder here is fake and the vectors are declared by hand. That is
deliberate and it bounds what these tests can claim: they show that both halves
are consulted, that the profiles behave differently, and that the pieces are
wired to each other. They show **nothing** about whether the real model
understands a Thai question about a belt motor - that is a measurement, it needs
the model, and it lives in `docs/retrieval-baseline.md`.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.authoring.service import Ingest
from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.retrieval import repo
from pdm.retrieval.embedding import FakeEmbedder
from pdm.retrieval.service import AUTHORING, RUNTIME, HybridSearch, Profile
from pdm.retrieval.vectors import InMemoryVectorIndex

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
OPERATOR = UserId("op-1")
R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")


def _manual(title: str, pages: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    for body in pages:
        pdf.add_page()
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 6, f"{title}\n\n{body}")
    return bytes(pdf.output())


# Two pages per manual, each about one subject, so a declared vector can put the
# meaning half's answer somewhere the word half would never reach.
R2000IC_PAGES = [
    "Belt tension. Measure deflection at the midpoint of the longest span and "
    "reset the tension if it lies outside the range given for this model.",
    "Hydraulic pump. The clamp pump maintains pressure in the accumulator and "
    "loses a little over a long idle period.",
]
M710IC_PAGES = [
    "Cabinet fan. A fan that has slowed no longer moves enough air and is "
    "replaced rather than cleaned once the bearing has begun to fail.",
    "Intake filter. The filter is cleaned monthly and its condition cannot be "
    "judged from the fan reading.",
]


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
def loaded(conn: Connection[Any], tmp_path: Path) -> HybridSearch:
    """Both manuals ingested, with hand-written vectors for the dense half.

    "loose drive belt" is declared close to the belt page and nothing else, so
    a query the word half cannot match still has one right answer - which is the
    shape of the case the real model exists for.
    """
    belt = [1.0, 0.0, 0.0, 0.0]
    pump = [0.0, 1.0, 0.0, 0.0]
    fan = [0.0, 0.0, 1.0, 0.0]
    filter_page = [0.0, 0.0, 0.0, 1.0]

    embedder = FakeEmbedder(
        dimensions=4,
        declared={
            **{page: vector for page, vector in zip(R2000IC_PAGES, [belt, pump], strict=True)},
            **{page: vector for page, vector in zip(M710IC_PAGES, [fan, filter_page], strict=True)},
            "loose drive belt": belt,
            "หลวม": belt,
        },
    )
    hybrid = HybridSearch(embedder, InMemoryVectorIndex())

    library = DocumentLibrary(FilesystemObjectStore(tmp_path), SimulatedClock(START))
    ingest = Ingest(library)
    for title, pages, model in (
        ("R-2000iC Manual", R2000IC_PAGES, R2000IC),
        ("M-710iC Manual", M710IC_PAGES, M710IC),
    ):
        document = library.add(
            conn,
            content=_manual(title, pages),
            filename=f"{model}.pdf",
            content_type="application/pdf",
            machine_model=model,
            title=title,
            uploaded_by=OPERATOR,
        )
        ingest.run(conn, document.document_id)
        hybrid.index_document(
            document.document_id, repo.chunks_of(conn, document.document_id), model
        )
    return hybrid


class TestBothHalvesAreConsulted:
    def test_a_query_the_word_half_cannot_match_is_still_answered(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """The reason the dense half exists. "หลวม" shares no lexeme with an
        English manual, so the word half returns nothing at all (ADR-034), and
        the result comes entirely from meaning."""
        assert repo.search(conn, "หลวม", machine_model=R2000IC) == []

        found = loaded.search(conn, "หลวม", machine_model=R2000IC)

        assert found
        assert found[0].chunk.page == 1
        assert found[0].ranks[0] is None  # the word half did not find it
        assert found[0].ranks[1] == 1

    def test_a_hit_both_halves_found_records_both_ranks(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        found = loaded.search(conn, "loose drive belt", machine_model=R2000IC)

        assert found[0].found_by_both
        assert found[0].ranks == (1, 1)
        assert found[0].score == pytest.approx(1.0)

    def test_results_carry_the_manual_they_came_from(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """The review screen must make "this is the other model" impossible to
        miss, and neither half knows the title on its own (ADR-015)."""
        found = loaded.search(conn, "loose drive belt", machine_model=R2000IC)

        assert found[0].title == "R-2000iC Manual"
        assert found[0].machine_model == R2000IC


class TestTheTwoProfilesDiffer:
    def test_runtime_refuses_to_search_across_machine_models(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """The one line ADR-015 does not move. A lockout procedure from a
        neighbouring model reads correctly line by line and is wrong in the
        order the interlocks release."""
        with pytest.raises(ValueError, match="across machine models"):
            loaded.search(conn, "loose drive belt", profile=RUNTIME)

    def test_authoring_may_see_the_other_manual(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """So the reviewer can be shown the wrong-model candidate and reject it,
        which is a judgement they can only make if they see it."""
        found = loaded.search(conn, "fan filter cleaned monthly", profile=AUTHORING)

        assert {hit.machine_model for hit in found} >= {M710IC}

    def test_the_two_profiles_answer_the_same_query_differently(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """The whole of ADR-015 in one comparison.

        Only the meaning half finds this one, so it scores 0.5 - a hit worth
        offering to a reviewer who will glance at it and worth withholding from
        a technician who will act on it. Nobody stands between the system and
        the technician at runtime, so a page that only looks relevant is the
        expensive mistake there; at authoring the expensive mistake is the page
        nobody was shown.
        """
        careful = Profile(candidates=4, min_score=0.9, abstain=True, same_model_only=True)
        thorough = Profile(candidates=4, min_score=0.9, abstain=False, same_model_only=False)

        assert loaded.search(conn, "หลวม", machine_model=R2000IC, profile=careful) == []
        assert loaded.search(conn, "หลวม", machine_model=R2000IC, profile=thorough)

    def test_a_hit_only_one_half_found_scores_half(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """What the threshold is applied to. Half the maximum is the score of a
        page one half ranked first and the other did not see at all, which is
        exactly the judgement the two profiles differ on."""
        found = loaded.search(conn, "หลวม", machine_model=R2000IC)

        assert found[0].score == pytest.approx(0.5)

    def test_the_number_of_candidates_comes_from_the_profile(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        one = Profile(candidates=1, min_score=0.0, abstain=False, same_model_only=False)

        assert len(loaded.search(conn, "belt pump fan filter", profile=one)) == 1


class TestKeepingTheIndexInStep:
    def test_re_indexing_a_document_replaces_its_vectors(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """Point ids are derived from the chunk's identity, not allocated, so a
        second ingest overwrites rather than accumulating a copy beside the
        first (ADR-035)."""
        document_id = repo.documents_of(
            conn,
            [
                hit.chunk.document_id
                for hit in loaded.search(conn, "loose drive belt", machine_model=R2000IC)
            ],
        )
        (only,) = document_id.keys()

        before = loaded.search(conn, "loose drive belt", machine_model=R2000IC)
        loaded.index_document(only, repo.chunks_of(conn, only), R2000IC)
        after = loaded.search(conn, "loose drive belt", machine_model=R2000IC)

        assert [hit.chunk.key for hit in before] == [hit.chunk.key for hit in after]

    def test_dropping_a_document_takes_its_vectors_with_it(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        found = loaded.search(conn, "loose drive belt", machine_model=R2000IC)
        document_id = DocumentId(found[0].chunk.document_id)

        loaded.drop_document(document_id)

        assert loaded.search(conn, "หลวม", machine_model=R2000IC) == []

    def test_a_vector_with_no_chunk_behind_it_is_skipped(
        self, loaded: HybridSearch, conn: Connection[Any]
    ) -> None:
        """The accepted cost of two stores (ADR-035). PostgreSQL is written
        first, so the reachable inconsistency is a chunk with no vector - but if
        the reverse ever happens, a dangling key must not become a result with
        no text."""
        found = loaded.search(conn, "loose drive belt", machine_model=R2000IC)
        document_id = DocumentId(found[0].chunk.document_id)

        with conn.cursor() as cur:
            cur.execute("DELETE FROM chunk WHERE document_id = %s", (document_id,))

        assert loaded.search(conn, "หลวม", machine_model=R2000IC) == []

"""The two authoring handlers, end to end through the queue (ADR-039).

A drafting job goes in and a proposal comes out of the review queue, with the
job marked done in the same transaction. That chain - queue, retrieval, backend,
gate, queue again - is four slices joined together, and until now nothing ran it
from one end to the other.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from fixtures.corpus import CORPUS
from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import MachineModel, SymptomCode, UserId
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import repo as playbooks
from pdm.retrieval.embedding import FakeEmbedder
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import InMemoryVectorIndex
from pdm.workers.authoring.handlers import draft_handler, ingest_handler
from pdm.workers.loop import Worker

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
M710IC = MachineModel("M-710iC")
TIMING = ClassTiming(heartbeat_seconds=30, dead_after_seconds=900)
CONFIG = load_config(Path("config"))


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[Any]]:
    connection = connect(database_url)
    try:
        connection.execute(
            "TRUNCATE job, playbook_proposal, playbook, chunk, document_page, document CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def pool(database_url: str) -> Iterator[ConnectionPool[Connection[Any]]]:
    made = ConnectionPool(database_url, min_size=2, max_size=4, open=True)
    try:
        yield made
    finally:
        made.close()


@pytest.fixture
def worker(conn: Connection[Any], pool: ConnectionPool[Connection[Any]], tmp_path: Path) -> Worker:
    """A worker wired the way `__main__` wires it, with the fake embedder."""
    clock = SimulatedClock(START)
    hybrid = HybridSearch(FakeEmbedder(dimensions=4), InMemoryVectorIndex())
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    authoring_profile, _ = profiles_from(CONFIG.policy.retrieval)

    ingest = Ingest(library, hybrid)
    drafting = Drafting(
        hybrid, ExtractiveDrafter(), profile=authoring_profile, skills=CONFIG.skills
    )

    for document in CORPUS.documents:
        library.add(
            conn,
            content=document.path.read_bytes(),
            filename=document.filename,
            content_type="application/pdf",
            machine_model=document.machine_model,
            title=document.title,
            uploaded_by=UserId("op-1"),
            edition=document.edition,
        )
    conn.commit()

    return Worker(
        queue=JobQueue(job_class=JobClass.AUTHORING, worker="worker-1", timing=TIMING, clock=clock),
        pool=pool,
        clock=clock,
        handlers={
            JobKind.INGEST.value: ingest_handler(ingest),
            JobKind.DRAFT.value: draft_handler(drafting, clock),
        },
    )


def _enqueue(conn: Connection[Any], kind: JobKind, payload: dict[str, object]) -> None:
    JobQueue(
        job_class=JobClass.AUTHORING,
        worker="enqueuer",
        timing=TIMING,
        clock=SimulatedClock(START),
    ).enqueue(conn, kind=kind, payload=payload)
    conn.commit()


class TestTheIngestJob:
    def test_a_manual_in_the_library_becomes_searchable(
        self, conn: Connection[Any], worker: Worker
    ) -> None:
        document = CORPUS.document(M710IC)
        _enqueue(conn, JobKind.INGEST, {"document_id": document.sha256})

        assert worker.run_one() is True

        chunks = conn.execute(
            "SELECT count(*) FROM chunk WHERE document_id = %s", (document.sha256,)
        ).fetchone()
        assert chunks is not None and chunks[0] > 0

    def test_a_payload_naming_no_document_fails_the_job_with_a_readable_reason(
        self, conn: Connection[Any], worker: Worker
    ) -> None:
        """Not a KeyError. The row is read minutes after it was written, by a
        process that did not write it, and "KeyError: 'document_id'" is not a
        sentence anybody can act on."""
        _enqueue(conn, JobKind.INGEST, {"documentid": "a" * 64})

        worker.run_one()

        error = conn.execute("SELECT last_error FROM job").fetchone()
        assert error is not None
        assert "BadPayload" in error[0]


class TestTheDraftJob:
    def test_a_symptom_becomes_a_proposal_in_the_review_queue(
        self, conn: Connection[Any], worker: Worker
    ) -> None:
        answer = CORPUS.answer(SymptomCode("SYM-047"))
        _enqueue(conn, JobKind.INGEST, {"document_id": CORPUS.document(M710IC).sha256})
        worker.run_one()
        _enqueue(
            conn,
            JobKind.DRAFT,
            {
                "symptom_code": answer.symptom_code,
                "machine_model": answer.machine_model,
                "question": answer.queries.en,
            },
        )

        assert worker.run_one() is True

        queued = playbooks.queue(conn)
        assert [item.symptom_code for item in queued] == [answer.symptom_code]
        assert queued[0].created_at == START

    def test_the_proposal_and_the_finished_job_commit_together(
        self, conn: Connection[Any], worker: Worker
    ) -> None:
        """ADR-017, through the whole chain: read from a different connection
        after the loop returns, both are there or neither is."""
        answer = CORPUS.answer(SymptomCode("SYM-047"))
        _enqueue(conn, JobKind.INGEST, {"document_id": CORPUS.document(M710IC).sha256})
        worker.run_one()
        _enqueue(
            conn,
            JobKind.DRAFT,
            {
                "symptom_code": answer.symptom_code,
                "machine_model": answer.machine_model,
                "question": answer.queries.en,
            },
        )
        worker.run_one()

        statuses = [row[0] for row in conn.execute("SELECT status FROM job ORDER BY id").fetchall()]
        assert statuses == ["done", "done"]
        assert len(playbooks.queue(conn)) == 1

    def test_a_job_with_no_question_is_refused_before_anything_is_retrieved(
        self, conn: Connection[Any], worker: Worker
    ) -> None:
        _enqueue(conn, JobKind.DRAFT, {"symptom_code": "SYM-047", "machine_model": "M-710iC"})

        worker.run_one()

        error = conn.execute("SELECT last_error FROM job").fetchone()
        assert error is not None and "BadPayload" in error[0]
        assert playbooks.queue(conn) == []

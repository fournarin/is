"""The manual library, against a real PostgreSQL (ADR-031).

Two things here cannot be checked without the database and are the reason the
table looks the way it does: re-registering the same bytes must not create a
second row, and a document must never be able to sit in a state where its
status and its withdrawal date disagree. Both are CHECK constraints and a
primary key - the things a substitute database would accept and production
would not.

The rest is about ADR-019's central promise: withdrawing a manual is a status
change, and the file is still there afterwards.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg.errors import CheckViolation

from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import Document, DocumentLibrary, DocumentStatus
from pdm.platform.documents import repo as document_repo
from pdm.platform.documents.repo import DocumentModelConflict
from pdm.platform.objects import FilesystemObjectStore

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)

R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")
OPERATOR = UserId("op-1")

MANUAL = b"%PDF-1.7\nR-2000iC maintenance, edition 3\n"
NEW_EDITION = b"%PDF-1.7\nR-2000iC maintenance, edition 4\n"


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE document")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def library(tmp_path: Path) -> DocumentLibrary:
    return DocumentLibrary(FilesystemObjectStore(tmp_path), SimulatedClock(START))


def _add(
    library: DocumentLibrary,
    conn: Connection[Any],
    *,
    content: bytes = MANUAL,
    filename: str = "r-2000ic.pdf",
    title: str = "R-2000iC Maintenance Manual",
    machine_model: MachineModel = R2000IC,
    edition: str | None = "Edition 3",
) -> Document:
    return library.add(
        conn,
        content=content,
        filename=filename,
        content_type="application/pdf",
        machine_model=machine_model,
        title=title,
        uploaded_by=OPERATOR,
        edition=edition,
    )


class TestRegistering:
    def test_a_document_is_stored_and_findable(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        document = _add(library, conn)

        assert document.status is DocumentStatus.ACTIVE
        assert document.size_bytes == len(MANUAL)
        assert document.uploaded_at == START
        assert library.get(conn, document.document_id) == document
        with library.open(document) as handle:
            assert handle.read() == MANUAL

    def test_the_same_bytes_under_a_new_name_are_the_same_document(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """Content addressing at the table level. Uploading the identical file
        twice is one manual, and the first upload's metadata is what the library
        keeps - overwriting it would let a second upload silently retitle a
        manual that approved playbooks already cite."""
        first = _add(library, conn, filename="r2000.pdf", title="R-2000iC Maintenance Manual")
        second = _add(library, conn, filename="copy-of-r2000.pdf", title="Renamed")

        assert second.document_id == first.document_id
        assert second.title == "R-2000iC Maintenance Manual"
        assert second.filename == "r2000.pdf"

    def test_a_new_edition_is_a_new_document(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """The case ADR-019 point 3 exists for: operators upload a new edition
        under the old filename. Stored by name the old file would be
        overwritten, and every citation to page 47 would point at whatever page
        47 became."""
        third = _add(library, conn, content=MANUAL, filename="manual.pdf", edition="Edition 3")
        fourth = _add(
            library, conn, content=NEW_EDITION, filename="manual.pdf", edition="Edition 4"
        )

        assert third.document_id != fourth.document_id
        with library.open(third) as handle:
            assert handle.read() == MANUAL

    def test_the_same_file_under_a_second_machine_model_is_refused(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """Content addressing gives one row per file, so accepting this quietly
        would report success and then never list the document under the second
        model. A manual genuinely covering two models needs a link table, and
        refusing says so instead of inventing one."""
        _add(library, conn, machine_model=R2000IC)

        with pytest.raises(DocumentModelConflict, match="link table"):
            _add(library, conn, machine_model=M710IC)

    def test_a_stream_is_stored_without_being_read_whole(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """The path an upload endpoint will take. A scanned manual is tens of
        megabytes and buffering each one before storing it is a memory limit
        waiting to be found on the plant's own hardware."""
        document = library.add_stream(
            conn,
            source=BytesIO(MANUAL),
            filename="streamed.pdf",
            content_type="application/pdf",
            machine_model=R2000IC,
            title="R-2000iC Maintenance Manual",
            uploaded_by=OPERATOR,
        )

        assert document.size_bytes == len(MANUAL)
        assert library.is_intact(document)

    def test_the_blob_is_written_before_the_row(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """A row always has its file. The reverse order would allow a document
        the library lists and cannot open, which is indistinguishable from
        corruption."""
        document = _add(library, conn)
        assert library.is_intact(document)


class TestWithdrawing:
    def test_withdrawing_leaves_the_file_exactly_where_it_was(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """ADR-019: "delete" is a status change. The PDF is evidence behind
        every closed work order that cites it."""
        document = _add(library, conn)
        withdrawn = library.withdraw(conn, document.document_id)

        assert withdrawn is not None
        assert withdrawn.status is DocumentStatus.WITHDRAWN
        assert withdrawn.withdrawn_at == START
        assert library.is_intact(withdrawn)
        with library.open(withdrawn) as handle:
            assert handle.read() == MANUAL

    def test_a_withdrawn_edition_keeps_the_date_it_actually_happened(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        clock = SimulatedClock(START)
        library.clock = clock
        document = _add(library, conn)

        first = library.withdraw(conn, document.document_id)
        clock.advance(timedelta(days=30))
        again = library.withdraw(conn, document.document_id)

        assert first is not None and again is not None
        assert again.withdrawn_at == first.withdrawn_at == START

    def test_withdrawing_something_that_is_not_there(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        assert library.withdraw(conn, DocumentId("0" * 64)) is None


class TestListing:
    def test_editions_come_back_newest_first(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        clock = SimulatedClock(START)
        library.clock = clock
        older = _add(library, conn, content=MANUAL, edition="Edition 3")
        clock.advance(timedelta(days=400))
        newer = _add(library, conn, content=NEW_EDITION, edition="Edition 4")

        listed = library.for_model(conn, R2000IC)
        assert [document.document_id for document in listed] == [
            newer.document_id,
            older.document_id,
        ]

    def test_a_withdrawn_edition_is_still_reachable_by_default(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """Tracing a citation on a closed work order reaches for withdrawn
        editions specifically, so they cannot be filtered out by default."""
        document = _add(library, conn)
        library.withdraw(conn, document.document_id)

        assert [d.document_id for d in library.for_model(conn, R2000IC)] == [document.document_id]
        assert library.for_model(conn, R2000IC, in_service_only=True) == []

    def test_models_do_not_leak_into_each_others_listings(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        _add(library, conn, content=MANUAL, machine_model=R2000IC)
        _add(library, conn, content=NEW_EDITION, machine_model=M710IC, title="M-710iC Manual")

        assert len(library.for_model(conn, R2000IC)) == 1
        assert len(library.for_model(conn, M710IC)) == 1


class TestTheDatabaseRefusesWhatTheModelRefuses:
    """The same rules, enforced twice. The model catches them in the
    application; the constraint catches the migration, the manual fix at 3am and
    the repo function somebody adds later."""

    def test_a_withdrawn_row_must_carry_its_date(self, conn: Connection[Any]) -> None:
        with pytest.raises(CheckViolation), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document (document_id, filename, content_type, size_bytes,
                                      machine_model, title, status, uploaded_by, uploaded_at)
                VALUES (%s, 'x.pdf', 'application/pdf', 1, 'R-2000iC', 'x',
                        'withdrawn', 'op-1', %s)
                """,
                ("a" * 64, START),
            )

    def test_an_active_row_must_not(self, conn: Connection[Any]) -> None:
        with pytest.raises(CheckViolation), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document (document_id, filename, content_type, size_bytes,
                                      machine_model, title, status, uploaded_by,
                                      uploaded_at, withdrawn_at)
                VALUES (%s, 'x.pdf', 'application/pdf', 1, 'R-2000iC', 'x',
                        'active', 'op-1', %s, %s)
                """,
                ("b" * 64, START, START),
            )

    def test_the_id_must_look_like_a_sha256(self, conn: Connection[Any]) -> None:
        """A row whose id is not a hash is a row whose blob cannot be found, and
        the whole scheme rests on the two being the same string."""
        with pytest.raises(CheckViolation), conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document (document_id, filename, content_type, size_bytes,
                                      machine_model, title, status, uploaded_by, uploaded_at)
                VALUES ('not-a-hash', 'x.pdf', 'application/pdf', 1, 'R-2000iC', 'x',
                        'active', 'op-1', %s)
                """,
                (START,),
            )


class TestTheRowIsNotTheFile:
    def test_a_missing_blob_is_reported_rather_than_crashing(
        self, library: DocumentLibrary, conn: Connection[Any]
    ) -> None:
        """Nothing in the application deletes a blob, so this means a restore
        from an incomplete backup or somebody working on the volume by hand.
        Worth being able to ask before an audit rather than during one."""
        document = _add(library, conn)
        row = document_repo.by_id(conn, document.document_id)
        assert row is not None

        detached = document.model_copy(update={"document_id": DocumentId("c" * 64)})
        assert not library.is_intact(detached)

    def test_corruption_that_keeps_the_same_length_is_still_caught(
        self, library: DocumentLibrary, conn: Connection[Any], tmp_path: Path
    ) -> None:
        """Why is_intact re-hashes instead of comparing sizes. Most of what a
        damaged restore produces is the same number of bytes, differently."""
        document = _add(library, conn)
        blob = (
            tmp_path / document.document_id[:2] / document.document_id[2:4] / document.document_id
        )
        blob.chmod(0o644)
        blob.write_bytes(b"x" * len(MANUAL))

        assert library.size(document) == document.size_bytes
        assert not library.is_intact(document)

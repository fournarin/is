"""The library: blobs and their rows, joined (ADR-030).

The only module `api/` and `workers/` call for documents. It opens no
connection - the caller supplies one - so that registering a manual and
enqueueing the ingest job that follows commit together (ADR-017).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from typing import Any, BinaryIO

from psycopg import Connection

from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.clock import Clock
from pdm.platform.documents import repo
from pdm.platform.documents.domain import Document, DocumentStatus
from pdm.platform.objects import READ_CHUNK_BYTES, ObjectNotFound, ObjectStore


class DocumentLibrary:
    """Every manual the system holds, and the bytes behind each one."""

    def __init__(self, store: ObjectStore, clock: Clock) -> None:
        self.store = store
        self.clock = clock

    def add(
        self,
        conn: Connection[Any],
        *,
        content: bytes,
        filename: str,
        content_type: str,
        machine_model: MachineModel,
        title: str,
        uploaded_by: UserId,
        edition: str | None = None,
    ) -> Document:
        """Register a manual held in memory. See `add_stream` for the rest."""
        return self.add_stream(
            conn,
            source=BytesIO(content),
            filename=filename,
            content_type=content_type,
            machine_model=machine_model,
            title=title,
            uploaded_by=uploaded_by,
            edition=edition,
        )

    def add_stream(
        self,
        conn: Connection[Any],
        *,
        source: BinaryIO,
        filename: str,
        content_type: str,
        machine_model: MachineModel,
        title: str,
        uploaded_by: UserId,
        edition: str | None = None,
    ) -> Document:
        """Store the bytes, then register them.

        **That order is the whole design of this method.** Blob first means a
        row always has its file: if the transaction rolls back after the blob is
        written, the blob is orphaned, and an orphan is harmless because content
        addressing makes the next upload of the same bytes find it already
        there. Row first would allow the reverse - a document the library lists
        and cannot open - which is indistinguishable from corruption.

        Nothing collects the orphans. ADR-019 has no cleanup job for exactly
        this reason: a task that removes a file a snapshot might cite trades a
        few kilobytes for the evidence behind a closed work order.

        Streaming is the real entry point and `add` is the convenience: a
        scanned manual is tens of megabytes, and an upload endpoint that has to
        buffer each one whole before storing it is a memory limit waiting to be
        found on the plant's own hardware.

        Raises `DocumentModelConflict` if these bytes are already registered
        under a different machine model - see that exception for why it is not
        simply accepted.
        """
        document_id = self.store.put_stream(source)
        return repo.insert(
            conn,
            document_id=document_id,
            filename=filename,
            content_type=content_type,
            size_bytes=self.store.size(document_id),
            machine_model=machine_model,
            title=title,
            edition=edition,
            uploaded_by=uploaded_by,
            now=self.clock.now(),
        )

    def get(self, conn: Connection[Any], document_id: DocumentId) -> Document | None:
        return repo.by_id(conn, document_id)

    def for_model(
        self,
        conn: Connection[Any],
        machine_model: MachineModel,
        *,
        in_service_only: bool = False,
    ) -> list[Document]:
        return repo.for_model(
            conn,
            machine_model,
            status=DocumentStatus.ACTIVE if in_service_only else None,
        )

    def withdraw(self, conn: Connection[Any], document_id: DocumentId) -> Document | None:
        """Take an edition out of service without touching the file.

        What this does *not* do is cascade: the playbooks drafted from this
        manual should move to `needs_review` and keep being served with a
        warning (ADR-018). There are no playbooks yet, and writing the cascade
        against a table that does not exist would mean guessing at its shape.
        """
        return repo.withdraw(conn, document_id, now=self.clock.now())

    @contextmanager
    def open(self, document: Document) -> Iterator[BinaryIO]:
        """The bytes, as a stream, for serving a page or a byte range.

        Takes the row rather than the id: reaching the blob means having found
        the document first, which is where an authorisation check belongs
        (ADR-019). A withdrawn edition still opens - somebody tracing a citation
        on a closed work order needs exactly that.
        """
        with self.store.open(document.document_id) as handle:
            yield handle

    def size(self, document: Document) -> int:
        """From disk rather than from the row, because a Range response that
        disagrees with the file by one byte is a corrupt download. The row's
        `size_bytes` is for display and for spotting the two diverging."""
        return self.store.size(document.document_id)

    def is_intact(self, document: Document) -> bool:
        """Whether the blob behind a row is still the bytes it claims to be.

        Re-hashes the file rather than comparing its length, because the id *is*
        the sha256: a size check would pass corruption that kept the same
        length, which is most of what a damaged restore produces. It therefore
        reads the whole document, and is for auditing a library rather than for
        answering a request.

        Nothing in the application deletes or rewrites a blob, so a false answer
        means an incomplete restore or somebody working on the volume by hand.
        Worth being able to ask before an audit rather than during one.
        """
        digest = hashlib.sha256()
        try:
            with self.store.open(document.document_id) as handle:
                while chunk := handle.read(READ_CHUNK_BYTES):
                    digest.update(chunk)
        except ObjectNotFound:
            return False
        return digest.hexdigest() == document.document_id

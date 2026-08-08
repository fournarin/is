"""The library: blobs and their rows, joined (ADR-030).

The only module `api/` and `workers/` call for documents. It opens no
connection - the caller supplies one - so that registering a manual and
enqueueing the ingest job that follows commit together (ADR-017).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, BinaryIO

from psycopg import Connection

from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.clock import Clock
from pdm.platform.documents import repo
from pdm.platform.documents.domain import Document, DocumentStatus
from pdm.platform.objects import ObjectNotFound, ObjectStore


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
        """
        document_id = self.store.put(content)
        return repo.insert(
            conn,
            document_id=document_id,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content),
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
        """Whether the blob behind a row is still there.

        Nothing in the application deletes one, so a false answer means the
        volume was restored from an incomplete backup or somebody worked on it
        by hand. Worth being able to ask before an audit rather than during one.
        """
        try:
            return self.store.size(document.document_id) == document.size_bytes
        except ObjectNotFound:
            return False

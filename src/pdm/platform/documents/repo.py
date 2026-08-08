"""SQL for the document table. No business logic, no connections opened here.

Every function takes a connection first (ADR-031), so that registering a
document and whatever prompted it - an ingest job, a withdrawal that pushes
playbooks into review - commit together.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from pdm.contracts import DocumentId, MachineModel, UserId
from pdm.platform.documents.domain import Document, DocumentStatus

_COLUMNS = """
    document_id, filename, content_type, size_bytes, machine_model, title,
    edition, status, uploaded_by, uploaded_at, withdrawn_at
"""


class DocumentModelConflict(Exception):
    """These bytes are already registered for a different machine model."""


class DocumentRegistrationConflict(Exception):
    """The row conflicted on insert and this transaction cannot see it."""


def _to_document(row: dict[str, Any]) -> Document:
    return Document.model_validate(row)


def insert(
    conn: Connection[Any],
    *,
    document_id: DocumentId,
    filename: str,
    content_type: str,
    size_bytes: int,
    machine_model: MachineModel,
    title: str,
    edition: str | None,
    uploaded_by: UserId,
    now: datetime,
) -> Document:
    """Register a blob that is already on disk.

    `ON CONFLICT DO NOTHING` then re-read, rather than an upsert: the same bytes
    are the same document, and the first upload's metadata is what the library
    keeps. Overwriting it would let a second upload silently retitle a manual
    that approved playbooks already cite.

    Timestamps are passed in, never `DEFAULT now()`, which would read real time
    while the rest of the system runs on a simulated clock (ADR-028).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            INSERT INTO document (document_id, filename, content_type, size_bytes,
                                  machine_model, title, edition, status,
                                  uploaded_by, uploaded_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active', %s, %s)
            ON CONFLICT (document_id) DO NOTHING
            RETURNING {_COLUMNS}
            """,
            (
                document_id,
                filename,
                content_type,
                size_bytes,
                machine_model,
                title,
                edition,
                uploaded_by,
                now,
            ),
        )
        row = cur.fetchone()

    if row is not None:
        return _to_document(row)

    existing = by_id(conn, document_id)
    if existing is None:
        # The insert conflicted, so a row exists - unless this transaction
        # cannot see it, which under REPEATABLE READ is a snapshot older than
        # the concurrent commit that caused the conflict. Rare, real, and not an
        # assert: assertions strip under -O, and this function would then return
        # None from a signature that promises a Document.
        raise DocumentRegistrationConflict(document_id)

    if existing.machine_model != machine_model:
        # The same PDF registered for a second machine model. Accepting it
        # silently is the harmful option: the caller is told the document was
        # stored and it never appears in the new model's listing, because
        # content addressing gives one row per file.
        #
        # A manual genuinely covering two models needs a link table. Nothing in
        # the corpus is like that, so this refuses and says why rather than
        # inventing the table now.
        raise DocumentModelConflict(
            f"{document_id} is already registered for {existing.machine_model}, "
            f"not {machine_model}. One file is one document (ADR-019); a manual "
            f"covering two machine models needs a link table that does not exist."
        )

    return existing


def by_id(conn: Connection[Any], document_id: DocumentId) -> Document | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM document WHERE document_id = %s", (document_id,))
        row = cur.fetchone()
    return None if row is None else _to_document(row)


def for_model(
    conn: Connection[Any],
    machine_model: MachineModel,
    *,
    status: DocumentStatus | None = None,
) -> list[Document]:
    """Newest first. `status=None` includes withdrawn editions, which is what a
    citation on a closed work order has to be able to reach."""
    clauses = ["machine_model = %s"]
    parameters: list[object] = [machine_model]
    if status is not None:
        clauses.append("status = %s")
        parameters.append(status.value)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"SELECT {_COLUMNS} FROM document WHERE {' AND '.join(clauses)} "
            f"ORDER BY uploaded_at DESC, document_id",
            parameters,
        )
        rows = cur.fetchall()
    return [_to_document(row) for row in rows]


def withdraw(conn: Connection[Any], document_id: DocumentId, *, now: datetime) -> Document | None:
    """Take an edition out of service. The file is not touched (ADR-019).

    Returns None if there is no such document, and the row unchanged if it was
    already withdrawn - so a repeated withdrawal keeps the original date rather
    than moving it, because the first one is when it actually happened.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            UPDATE document
               SET status = 'withdrawn', withdrawn_at = %s
             WHERE document_id = %s AND status = 'active'
            RETURNING {_COLUMNS}
            """,
            (now, document_id),
        )
        row = cur.fetchone()

    return _to_document(row) if row is not None else by_id(conn, document_id)

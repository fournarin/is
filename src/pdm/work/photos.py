"""One photo kept with a reported fault (ADR-142).

The trial's technician asked to see what the operator saw before walking to the
machine. The screen shrinks the picture before it is sent; this module only
records which blob belongs to which report. The bytes live in the object store
(ADR-019), which never deletes, so a photo, once attached, is evidence like a
manual page.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict

from pdm.contracts import UserId

# A phone picture shrunk to 1600 px on its long side is well under this. A file
# above it was not shrunk, and storing it would keep a 5 MB picture per report.
MAX_BYTES = 2 * 1024 * 1024

# Magic bytes per type. Only what a phone camera or a canvas produces.
ALLOWED_TYPES = {
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
    "image/webp": b"RIFF",
}


class Photo(BaseModel):
    model_config = ConfigDict(frozen=True)

    work_order_ref: str
    blob_id: str
    content_type: str
    size_bytes: int
    taken_by: UserId
    taken_at: datetime


class AlreadyHasPhoto(ValueError):
    """One photo per report: a second would make "the photo" ambiguous."""


def attach(conn: Connection[Any], photo: Photo) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO work_order_photo
                (work_order_ref, blob_id, content_type, size_bytes, taken_by, taken_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (work_order_ref) DO NOTHING
            """,
            (
                photo.work_order_ref,
                photo.blob_id,
                photo.content_type,
                photo.size_bytes,
                photo.taken_by,
                photo.taken_at,
            ),
        )
        if cur.rowcount == 0:
            raise AlreadyHasPhoto(f"{photo.work_order_ref} มีรูปแนบอยู่แล้ว")


def of(conn: Connection[Any], work_order_ref: str) -> Photo | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM work_order_photo WHERE work_order_ref = %s", (work_order_ref,))
        row = cur.fetchone()
    return Photo(**row) if row else None


def refs_with_photos(conn: Connection[Any], refs: list[str]) -> set[str]:
    if not refs:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT work_order_ref FROM work_order_photo WHERE work_order_ref = ANY(%s)", (refs,)
        )
        return {str(row[0]) for row in cur.fetchall()}

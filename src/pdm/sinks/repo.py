"""SQL for the delivery record. No business logic, no connections opened here.

Every function takes a connection first (ADR-031), so that a round's placements
and the delivery rows they queue commit together - the same argument ADR-017
makes about a job and its result. A ticket queued for delivery by a round that
then rolled back would be a ticket nobody placed, waiting to be sent.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from pdm.contracts import WorkOrderRef


def queue(conn: Connection[Any], refs: Sequence[WorkOrderRef], *, at: datetime) -> int:
    """Say that these orders are due to leave. Returns how many were new.

    `ON CONFLICT DO NOTHING` is the whole of "once per round". A round replayed
    after a crash, or two rounds that both saw the same placement, find the row
    already there - and a ticket already delivered is not queued again by a
    later round noticing it (ADR-068).
    """
    if not refs:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO ticket_delivery (work_order_ref, state, attempts, queued_at)
            VALUES (%s, 'pending', 0, %s)
            ON CONFLICT (work_order_ref) DO NOTHING
            """,
            [(str(ref), at) for ref in refs],
        )
        return max(cur.rowcount, 0)


def outstanding(conn: Connection[Any], *, limit: int) -> list[WorkOrderRef]:
    """The tickets that still have to go out, oldest first.

    Both `pending` and `failed`, because a destination that refused a ticket
    last round is exactly what the next round is for. Ordered by `queued_at` so
    a destination that has been down for an hour drains in the order the work
    was decided rather than in whatever order the table happens to hold.

    `FOR UPDATE SKIP LOCKED` for the same reason the job queue uses it
    (ADR-017): only one worker runs rounds today, and a second one appearing
    must not mean the same ticket going out twice in the same minute.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT work_order_ref
              FROM ticket_delivery
             WHERE state <> 'delivered'
             ORDER BY queued_at
             LIMIT %s
               FOR UPDATE SKIP LOCKED
            """,
            (limit,),
        )
        return [WorkOrderRef(row[0]) for row in cur.fetchall()]


def record_delivered(
    conn: Connection[Any],
    work_order_ref: WorkOrderRef,
    *,
    destination: str,
    external_ref: str,
    at: datetime,
) -> None:
    """It arrived. `last_error` is cleared: what is true now is that it is there."""
    conn.execute(
        """
        UPDATE ticket_delivery
           SET state = 'delivered',
               destination = %s,
               external_ref = %s,
               attempts = attempts + 1,
               last_attempt_at = %s,
               delivered_at = %s,
               last_error = NULL
         WHERE work_order_ref = %s
        """,
        (destination, external_ref, at, at, str(work_order_ref)),
    )


def record_failed(
    conn: Connection[Any],
    work_order_ref: WorkOrderRef,
    *,
    destination: str,
    error: str,
    at: datetime,
) -> None:
    """It did not arrive, and the row says what was said about it.

    The order is untouched. A destination refusing a ticket is a fact about the
    destination, and un-placing the work because a CMMS was down would take a
    job away from a technician who can already see it (ADR-068).
    """
    conn.execute(
        """
        UPDATE ticket_delivery
           SET state = 'failed',
               destination = %s,
               attempts = attempts + 1,
               last_attempt_at = %s,
               last_error = %s
         WHERE work_order_ref = %s
        """,
        (destination, at, error, str(work_order_ref)),
    )


def state_of(conn: Connection[Any], work_order_ref: WorkOrderRef) -> dict[str, Any] | None:
    """One delivery row, for a test and for whoever asks why a ticket never arrived."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM ticket_delivery WHERE work_order_ref = %s", (str(work_order_ref),)
        )
        row = cur.fetchone()
    return dict(row) if row is not None else None

"""SQL for the job table. No business logic, no connections opened here.

Every function takes a connection as its first argument (ADR-031). That is what
makes ADR-017 true rather than merely intended: enqueueing a job and writing the
data it belongs to commit in one transaction, so there is no window in which a
playbook exists with no job, or a job reports success with no playbook. If these
functions opened their own connections, each would sit in its own transaction and
the entire class of bug ADR-017 set out to remove would come back while we still
believed it was gone.

Rows come back as dicts and are turned into Job objects immediately. Nothing
holding a connection escapes this module (ADR-031, invariant 10).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pdm.platform.jobs.domain import Job, JobClass, JobStatus

_COLUMNS = """
    id, job_class, kind, payload, status, attempts, max_attempts,
    available_at, created_at, claimed_by, claimed_at, heartbeat_at,
    finished_at, last_error
"""


def _to_job(row: dict[str, Any]) -> Job:
    return Job.model_validate(row)


def enqueue(
    conn: Connection[Any],
    *,
    job_class: JobClass,
    kind: str,
    payload: dict[str, object],
    now: datetime,
    available_at: datetime | None = None,
    max_attempts: int = 3,
) -> Job:
    """Insert a job. Timestamps are passed in, never taken from the database.

    `DEFAULT now()` would read the real clock even when the rest of the system is
    running on a simulated one, which is the single hole that would make
    SimulatedClock decorative (ADR-028).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            INSERT INTO job (job_class, kind, payload, status, available_at, created_at,
                             max_attempts)
            VALUES (%s, %s, %s, 'queued', %s, %s, %s)
            RETURNING {_COLUMNS}
            """,
            (job_class.value, kind, Jsonb(payload), available_at or now, now, max_attempts),
        )
        row = cur.fetchone()
    assert row is not None
    return _to_job(row)


def pending_of_kind(
    conn: Connection[Any], *, job_class: JobClass, kind: str, payload: dict[str, object]
) -> Job | None:
    """A job of this kind whose payload contains these keys, not yet finished.

    Containment rather than equality, so a draft already queued for a pair is
    found whatever question it carries (ADR-040 section 2). Used at the door to
    recognise the second press of a button, never inside a worker.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT {_COLUMNS} FROM job
             WHERE job_class = %s
               AND kind = %s
               AND status IN ('queued', 'running')
               AND payload @> %s
             ORDER BY id
             LIMIT 1
            """,
            (job_class.value, kind, Jsonb(payload)),
        )
        row = cur.fetchone()
    return _to_job(row) if row else None


def ever_of_kind(
    conn: Connection[Any], *, job_class: JobClass, kind: str, payload: dict[str, object]
) -> bool:
    """A job of this kind whose payload contains these keys, in any status."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM job WHERE job_class = %s AND kind = %s AND payload @> %s LIMIT 1",
            (job_class.value, kind, Jsonb(payload)),
        )
        return cur.fetchone() is not None


def claim(
    conn: Connection[Any],
    *,
    job_class: JobClass,
    worker: str,
    now: datetime,
) -> Job | None:
    """Take the next available job of one class, or return None.

    FOR UPDATE SKIP LOCKED is what lets several workers of the same class poll
    the same table without blocking each other or handing the same row to two of
    them (ADR-017).

    The `job_class = %s` filter is invariant 12: worker-runtime must never be
    able to pick up authoring work. It is a filter rather than a convention
    because the failure it prevents - a twenty-minute manual ingest running
    inside the worker that owns the dispatch tick - stops ticket dispatch for the
    whole plant and produces no error at all.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            UPDATE job SET
                status = 'running',
                claimed_by = %s,
                claimed_at = %s,
                heartbeat_at = %s,
                attempts = attempts + 1
            WHERE id = (
                SELECT id FROM job
                WHERE job_class = %s
                  AND status = 'queued'
                  AND available_at <= %s
                ORDER BY available_at, id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            RETURNING {_COLUMNS}
            """,
            (worker, now, now, job_class.value, now),
        )
        row = cur.fetchone()
    return _to_job(row) if row else None


def heartbeat(conn: Connection[Any], *, job_id: int, worker: str, now: datetime) -> bool:
    """Report that a worker is still alive on a job.

    Scoped to the claiming worker, so a beat from a process that was already
    reaped and replaced cannot resurrect its claim.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job SET heartbeat_at = %s "
            "WHERE id = %s AND claimed_by = %s AND status = 'running'",
            (now, job_id, worker),
        )
        return cur.rowcount == 1


def finish(conn: Connection[Any], *, job_id: int, worker: str, now: datetime) -> bool:
    """Mark the job done, if this worker still holds it.

    Scoped to the claimer, like the heartbeat and for the same reason. A worker
    the reaper gave up on may still be alive and finish minutes later; without
    the scope it would write `done` over a row a second worker is now running,
    and the second worker's result would land on a job already reported complete
    (ADR-039).

    False means the claim was lost. The work has still been committed - it is in
    the same transaction - and the caller logs it, because a job silently
    completed twice is worth seeing in the log even when both results agree.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE job SET status = 'done', finished_at = %s, last_error = NULL "
            "WHERE id = %s AND claimed_by = %s AND status = 'running'",
            (now, job_id, worker),
        )
        return cur.rowcount == 1


def fail(
    conn: Connection[Any],
    *,
    job_id: int,
    worker: str,
    error: str,
    now: datetime,
    retry_at: datetime | None,
) -> bool:
    """Either release the job for a later retry, or mark it failed for good.

    Scoped to the claiming worker, like `finish` and for the same reason: a
    worker the reaper gave up on is still running, and its eventual failure must
    not flip a row a second worker owns back to `queued` - which would draft the
    same symptom twice - or bury the second worker's progress under the first
    one's error.
    """
    with conn.cursor() as cur:
        if retry_at is None:
            cur.execute(
                "UPDATE job SET status = 'failed', finished_at = %s, last_error = %s "
                "WHERE id = %s AND claimed_by = %s AND status = 'running'",
                (now, error, job_id, worker),
            )
        else:
            cur.execute(
                """
                UPDATE job SET
                    status = 'queued', claimed_by = NULL, claimed_at = NULL,
                    heartbeat_at = NULL, available_at = %s, last_error = %s
                WHERE id = %s AND claimed_by = %s AND status = 'running'
                """,
                (retry_at, error, job_id, worker),
            )
        return cur.rowcount == 1


def reap(
    conn: Connection[Any],
    *,
    job_class: JobClass,
    dead_before: datetime,
) -> list[Job]:
    """Return jobs whose worker went silent to the queue.

    Without this the queue dies quietly: a worker killed mid-job leaves the row
    in `running` forever, and the work is neither done nor waiting. Nothing
    reports it, because from the outside a job that takes a long time and a job
    that will never finish look the same.

    A running job with no heartbeat is included: the worker died between claiming
    and its first beat.

    **Locked rows are skipped.** A job's whole handler runs inside the
    transaction that claimed it (ADR-017), which holds that row's lock for the
    duration - twenty minutes for a large manual. Without `SKIP LOCKED` this
    UPDATE waits behind it, so one healthy long-running job stalls the reaping of
    every genuinely dead job in its class. The rows this skips are the ones a
    live transaction is holding, which is the definition of a job still running
    (ADR-039).
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            UPDATE job SET
                -- A job that has used its attempts is not put back. Nothing else
                -- enforces the cap on this path: `fail` counts the attempts, and
                -- a job that kills its worker outright - an OOM on a large scan -
                -- never reaches `fail`. Re-queued unconditionally it would be
                -- claimed again, kill the worker again, and be reaped again, for
                -- as long as the worker is restarted (ADR-039).
                status = CASE WHEN attempts >= max_attempts THEN 'failed' ELSE 'queued' END,
                finished_at = CASE WHEN attempts >= max_attempts THEN %s ELSE NULL END,
                last_error = CASE
                    WHEN attempts >= max_attempts
                    THEN 'the worker went silent and the attempts are spent'
                    ELSE 'the worker went silent; returned to the queue'
                END,
                claimed_by = NULL, claimed_at = NULL, heartbeat_at = NULL
            WHERE id IN (
                SELECT id FROM job
                WHERE job_class = %s
                  AND status = 'running'
                  AND (heartbeat_at IS NULL OR heartbeat_at < %s)
                FOR UPDATE SKIP LOCKED
            )
            RETURNING {_COLUMNS}
            """,
            (dead_before, job_class.value, dead_before),
        )
        return [_to_job(row) for row in cur.fetchall()]


def get(conn: Connection[Any], job_id: int) -> Job | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM job WHERE id = %s", (job_id,))
        row = cur.fetchone()
    return _to_job(row) if row else None


def counts_by_status(conn: Connection[Any], job_class: JobClass) -> dict[JobStatus, int]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT status, count(*) FROM job WHERE job_class = %s GROUP BY status",
            (job_class.value,),
        )
        return {JobStatus(status): count for status, count in cur.fetchall()}

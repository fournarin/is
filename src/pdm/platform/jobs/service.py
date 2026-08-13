"""Joins the pure rules in domain.py to the SQL in repo.py (ADR-030).

The only module api/ and workers/ call. It never opens a connection either: the
caller supplies one, so that enqueueing a job and writing the data it belongs to
land in the same transaction (ADR-017).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from pdm.platform.clock import Clock
from pdm.platform.jobs import repo
from pdm.platform.jobs.domain import ClassTiming, Job, JobClass, retry_delay, should_retry


class JobQueue:
    """One class of work, one worker identity, one clock."""

    def __init__(
        self,
        *,
        job_class: JobClass,
        worker: str,
        timing: ClassTiming,
        clock: Clock,
    ) -> None:
        self.job_class = job_class
        self.worker = worker
        self.timing = timing
        self.clock = clock

    def enqueue(
        self,
        conn: Connection[Any],
        *,
        kind: str,
        payload: dict[str, object] | None = None,
        available_at: datetime | None = None,
        max_attempts: int = 3,
    ) -> Job:
        return repo.enqueue(
            conn,
            job_class=self.job_class,
            kind=kind,
            payload=payload or {},
            now=self.clock.now(),
            available_at=available_at,
            max_attempts=max_attempts,
        )

    def claim(self, conn: Connection[Any]) -> Job | None:
        """Take the next job of this queue's class, and no other (invariant 12)."""
        return repo.claim(conn, job_class=self.job_class, worker=self.worker, now=self.clock.now())

    def heartbeat(self, conn: Connection[Any], job: Job) -> bool:
        return repo.heartbeat(conn, job_id=job.id, worker=self.worker, now=self.clock.now())

    def finish(self, conn: Connection[Any], job: Job) -> bool:
        """True if this worker still held the claim (ADR-039)."""
        return repo.finish(conn, job_id=job.id, worker=self.worker, now=self.clock.now())

    def fail(self, conn: Connection[Any], job: Job, error: str) -> None:
        """Release for retry, or give up once the attempts are spent.

        `job.attempts` was already incremented by the claim, so it is the count
        of attempts made rather than attempts remaining.
        """
        now = self.clock.now()
        retry_at = (
            now + retry_delay(job.attempts)
            if should_retry(job.attempts, job.max_attempts)
            else None
        )
        repo.fail(conn, job_id=job.id, error=error, now=now, retry_at=retry_at)

    def reap(self, conn: Connection[Any]) -> list[Job]:
        """Return jobs abandoned by a dead worker to the queue.

        The threshold comes from this queue's own timing, which is why the two
        classes need separate ones: a value tight enough to catch a dead runtime
        job in under a minute would declare a twenty-minute ingest dead while it
        is still working (ADR-026).
        """
        now = self.clock.now()
        dead_before = now - __import__("datetime").timedelta(seconds=self.timing.dead_after_seconds)
        return repo.reap(conn, job_class=self.job_class, dead_before=dead_before)

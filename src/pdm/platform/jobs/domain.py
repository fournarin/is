"""Job queue decisions that need no database (ADR-030 layering).

Everything here is a pure function of its arguments. The SQL lives in repo.py and
the two are joined in service.py. The split is not decoration: it is what lets
the reaper's timing rules be tested exhaustively against a simulated clock in
milliseconds, instead of by waiting fifteen minutes for a real one.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class JobClass(StrEnum):
    """Which worker may run this job (ADR-026).

    The line is not "short work versus long work" but "is anybody waiting for
    it". A technician is standing in front of a machine waiting on runtime work;
    an engineer will look at an authoring result some time this afternoon. Those
    tolerate latency three orders of magnitude apart, so they cannot share a
    worker whatever the concurrency setting.
    """

    RUNTIME = "runtime"
    AUTHORING = "authoring"


class JobKind(StrEnum):
    """What a job asks for. The queue's vocabulary, not any worker's.

    Here rather than beside the handlers because both sides need it and they are
    not allowed to meet: the API enqueues and the worker claims, and when the API
    imported the handler module to learn the string, the import linter refused
    it - `api -> workers.authoring.handlers -> authoring.service -> llm` is a
    runtime module reaching the language model, which is invariant 1 and the most
    expensive rule in the system (ADR-003).

    A string a producer and a consumer both have to agree on is a contract, and
    contracts live where both can see them.
    """

    INGEST = "ingest"
    DRAFT = "draft"
    # Layer 1's pulse. Unlike the two above, nobody asks for it: the tick that
    # runs enqueues the next one in the same transaction, so the whole of the
    # trigger loop's schedule is a row anybody can SELECT (ADR-044 section 1).
    OBSERVE = "observe"
    # Layer 3's pulse, and the same shape as OBSERVE: the round that runs books
    # the next one in its own transaction, so the schedule is a row anybody can
    # SELECT rather than a timer inside a process (ADR-044 §1, ADR-045).
    DISPATCH = "dispatch"
    # The PM schedule's pulse, booked the same way and kept a chain of its own.
    # Sharing the dispatch job would mean a scan that failed rolled back the
    # round it travelled with, and one bad PM task would stop the plant being
    # scheduled at all (ADR-083 section 3, ADR-044 §3).
    PM_SCAN = "pm_scan"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    # Out of attempts. Stays in the table as evidence rather than disappearing.
    FAILED = "failed"


class Job(BaseModel):
    model_config = _FROZEN

    id: int
    job_class: JobClass
    kind: str
    payload: dict[str, object]
    status: JobStatus
    attempts: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    available_at: datetime
    created_at: datetime
    claimed_by: str | None = None
    claimed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None


class ClassTiming(BaseModel):
    """Heartbeat and death thresholds for one job class.

    Two sets exist because one cannot serve both (ADR-026). A threshold tight
    enough to notice a dead five-second runtime job within a minute would declare
    a twenty-minute manual ingest dead while it is still working, and a threshold
    loose enough for the ingest would leave the runtime queue stalled for the
    whole of that window.
    """

    model_config = _FROZEN

    heartbeat_seconds: int = Field(gt=0)
    dead_after_seconds: int = Field(gt=0)

    def is_dead(self, heartbeat_at: datetime | None, now: datetime) -> bool:
        """A job whose worker has gone silent for longer than the threshold.

        A running job with no heartbeat at all counts as dead: the worker died
        between claiming and its first beat, which is a real and otherwise
        invisible case.
        """
        if heartbeat_at is None:
            return True
        return now - heartbeat_at > timedelta(seconds=self.dead_after_seconds)


def retry_delay(attempts: int) -> timedelta:
    """Backoff before a failed job becomes claimable again.

    Exponential and capped. Without a delay a job that fails instantly - a
    malformed PDF, an unreachable model server - is retried as fast as the
    worker can loop, and one bad row saturates the queue for everything else.
    """
    seconds = min(60 * 2**attempts, 3600)
    return timedelta(seconds=seconds)


def should_retry(attempts: int, max_attempts: int) -> bool:
    return attempts < max_attempts

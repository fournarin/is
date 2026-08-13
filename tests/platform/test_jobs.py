"""Job queue behaviour, against a real PostgreSQL (ADR-031).

Never SQLite. What most needs testing here is exactly what SQLite does not have:
SKIP LOCKED, partial indexes, CHECK constraints. A substitute would give
confidence from tests that never touched the risky lines.

The clock is simulated throughout, so a fifteen-minute reaper threshold is
exercised in microseconds. Testing this against real time would mean either
waiting or lowering the thresholds until the test no longer resembles
production.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.platform.clock import SimulatedClock
from pdm.platform.jobs import ClassTiming, JobClass, JobQueue, JobStatus
from pdm.platform.jobs import repo as job_repo
from pdm.platform.jobs.domain import retry_delay, should_retry

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)

# ADR-026: the two classes cannot share a threshold. A value tight enough to
# catch a dead runtime job inside a minute would declare a twenty-minute ingest
# dead while it is still working.
RUNTIME_TIMING = ClassTiming(heartbeat_seconds=10, dead_after_seconds=60)
AUTHORING_TIMING = ClassTiming(heartbeat_seconds=30, dead_after_seconds=900)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE job RESTART IDENTITY")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(START)


def _queue(clock: SimulatedClock, job_class: JobClass, worker: str = "w1") -> JobQueue:
    timing = RUNTIME_TIMING if job_class is JobClass.RUNTIME else AUTHORING_TIMING
    return JobQueue(job_class=job_class, worker=worker, timing=timing, clock=clock)


class TestInvariant12:
    """worker-runtime must never pick up authoring work (ADR-026).

    The failure this prevents is silent and total: a twenty-minute manual ingest
    running inside the worker that owns the dispatch tick stops ticket dispatch
    for the whole plant, with no error anywhere.
    """

    def test_a_runtime_worker_never_sees_an_authoring_job(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        authoring = _queue(clock, JobClass.AUTHORING)
        runtime = _queue(clock, JobClass.RUNTIME)

        authoring.enqueue(conn, kind="ingest_manual", payload={"doc": "abc"})

        assert runtime.claim(conn) is None
        assert authoring.claim(conn) is not None

    def test_an_authoring_worker_never_sees_a_runtime_job(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        _queue(clock, JobClass.RUNTIME).enqueue(conn, kind="dispatch_tick")
        assert _queue(clock, JobClass.AUTHORING).claim(conn) is None

    def test_a_hundred_authoring_jobs_do_not_starve_the_runtime_queue(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The scenario ADR-026 was written for."""
        authoring = _queue(clock, JobClass.AUTHORING)
        for index in range(100):
            authoring.enqueue(conn, kind="ingest_manual", payload={"doc": str(index)})

        runtime = _queue(clock, JobClass.RUNTIME)
        runtime.enqueue(conn, kind="dispatch_tick")
        claimed = runtime.claim(conn)

        assert claimed is not None
        assert claimed.kind == "dispatch_tick"


class TestClaiming:
    def test_a_claim_returns_none_on_an_empty_queue(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        assert _queue(clock, JobClass.RUNTIME).claim(conn) is None

    def test_two_workers_never_receive_the_same_job(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """What SKIP LOCKED buys, and the reason these tests need real Postgres."""
        _queue(clock, JobClass.RUNTIME).enqueue(conn, kind="dispatch_tick")
        conn.commit()

        url = os.environ["DATABASE_URL"]
        with connect(url) as other:
            first = _queue(clock, JobClass.RUNTIME, worker="w1").claim(conn)
            second = _queue(clock, JobClass.RUNTIME, worker="w2").claim(other)
            conn.commit()
            other.commit()

        assert first is not None
        assert second is None

    def test_a_second_worker_skips_a_locked_row_and_takes_the_next(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """SKIP LOCKED rather than plain FOR UPDATE: the second worker must move
        on, not block behind the first."""
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="tick_a")
        queue.enqueue(conn, kind="tick_b")
        conn.commit()

        url = os.environ["DATABASE_URL"]
        with connect(url) as other:
            first = _queue(clock, JobClass.RUNTIME, worker="w1").claim(conn)
            second = _queue(clock, JobClass.RUNTIME, worker="w2").claim(other)
            conn.commit()
            other.commit()

        assert first is not None and second is not None
        assert {first.kind, second.kind} == {"tick_a", "tick_b"}

    def test_a_job_scheduled_for_later_is_not_claimed_yet(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick", available_at=START + timedelta(minutes=5))

        assert queue.claim(conn) is None
        clock.advance(timedelta(minutes=6))
        assert queue.claim(conn) is not None

    def test_claiming_records_the_worker_and_counts_the_attempt(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME, worker="worker-runtime-1")
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)

        assert job is not None
        assert job.claimed_by == "worker-runtime-1"
        assert job.status is JobStatus.RUNNING
        assert job.attempts == 1


class TestTimestampsComeFromTheClock:
    """ADR-028. No column has DEFAULT now(), and this is what proves it.

    If the database supplied any of these, a simulated run would mix two
    timelines and SimulatedClock would be decorative.
    """

    def test_created_at_is_the_simulated_time_not_the_real_one(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        job = _queue(clock, JobClass.RUNTIME).enqueue(conn, kind="dispatch_tick")
        assert job.created_at == START

    def test_advancing_the_clock_moves_the_timestamps(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        clock.advance(timedelta(days=30))
        job = _queue(clock, JobClass.RUNTIME).enqueue(conn, kind="dispatch_tick")
        assert job.created_at == START + timedelta(days=30)


class TestTheReaper:
    """A worker killed mid-job leaves a row in `running` forever otherwise.

    Nothing reports it, because from outside, a job that takes a long time and a
    job that will never finish look identical.
    """

    def test_a_silent_worker_loses_its_job(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)
        assert job is not None

        clock.advance(timedelta(seconds=61))
        reaped = queue.reap(conn)

        assert [item.id for item in reaped] == [job.id]
        assert queue.claim(conn) is not None

    def test_a_worker_that_keeps_beating_keeps_its_job(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)
        assert job is not None

        for _ in range(10):
            clock.advance(timedelta(seconds=10))
            assert queue.heartbeat(conn, job) is True

        assert queue.reap(conn) == []

    def test_the_two_classes_use_their_own_thresholds(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """The consequence ADR-026 called out. At five minutes the runtime job is
        long dead while the ingest is still perfectly healthy; one shared
        threshold would have to be wrong about one of them."""
        runtime = _queue(clock, JobClass.RUNTIME)
        authoring = _queue(clock, JobClass.AUTHORING)
        runtime.enqueue(conn, kind="dispatch_tick")
        authoring.enqueue(conn, kind="ingest_manual")
        assert runtime.claim(conn) is not None
        assert authoring.claim(conn) is not None

        clock.advance(timedelta(minutes=5))

        assert len(runtime.reap(conn)) == 1
        assert authoring.reap(conn) == []

    def test_a_worker_that_died_before_its_first_beat_is_still_reaped(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)
        assert job is not None
        conn.execute("UPDATE job SET heartbeat_at = NULL WHERE id = %s", (job.id,))

        clock.advance(timedelta(seconds=61))
        assert len(queue.reap(conn)) == 1

    def test_a_beat_from_a_replaced_worker_is_ignored(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        """Otherwise a process that was already reaped could resurrect its claim
        and two workers would run the same job."""
        first = _queue(clock, JobClass.RUNTIME, worker="w1")
        first.enqueue(conn, kind="dispatch_tick")
        job = first.claim(conn)
        assert job is not None

        clock.advance(timedelta(seconds=61))
        first.reap(conn)
        second = _queue(clock, JobClass.RUNTIME, worker="w2")
        assert second.claim(conn) is not None

        assert first.heartbeat(conn, job) is False


class TestFailureAndRetry:
    def test_a_failed_job_comes_back_after_a_delay(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)
        assert job is not None

        queue.fail(conn, job, "model server unreachable")

        assert queue.claim(conn) is None, "a failed job must not be retried immediately"
        clock.advance(retry_delay(1) + timedelta(seconds=1))
        assert queue.claim(conn) is not None

    def test_a_job_out_of_attempts_stops_being_retried(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick", max_attempts=2)

        job_id = 0
        for _ in range(2):
            job = queue.claim(conn)
            assert job is not None
            job_id = job.id
            queue.fail(conn, job, "broken input")
            clock.advance(retry_delay(job.attempts) + timedelta(seconds=1))

        assert queue.claim(conn) is None
        stored = job_repo.get(conn, job_id)
        assert stored is not None
        assert stored.status is JobStatus.FAILED
        assert stored.last_error == "broken input"

    def test_a_finished_job_is_not_claimed_again(
        self, conn: Connection[Any], clock: SimulatedClock
    ) -> None:
        queue = _queue(clock, JobClass.RUNTIME)
        queue.enqueue(conn, kind="dispatch_tick")
        job = queue.claim(conn)
        assert job is not None

        queue.finish(conn, job)
        assert queue.claim(conn) is None
        assert job_repo.counts_by_status(conn, JobClass.RUNTIME) == {JobStatus.DONE: 1}


class TestTheSchemaRefusesNonsense:
    """CHECK constraints, which is part of why this cannot run on SQLite."""

    def test_an_unknown_job_class_is_rejected(self, conn: Connection[Any]) -> None:
        with pytest.raises(Exception, match="job_class"):
            conn.execute(
                "INSERT INTO job (job_class, kind, status, available_at, created_at) "
                "VALUES ('sneaky', 'x', 'queued', %s, %s)",
                (START, START),
            )

    def test_a_running_job_must_name_its_worker(self, conn: Connection[Any]) -> None:
        with pytest.raises(Exception, match="running_jobs_have_a_worker"):
            conn.execute(
                "INSERT INTO job (job_class, kind, status, available_at, created_at) "
                "VALUES ('runtime', 'x', 'running', %s, %s)",
                (START, START),
            )


class TestRetryPolicy:
    """Pure functions, so no database needed."""

    def test_backoff_grows_and_is_capped(self) -> None:
        """Without a delay, a job that fails instantly is retried as fast as the
        worker can loop and one bad row saturates the queue."""
        delays = [retry_delay(attempt).total_seconds() for attempt in range(1, 8)]
        assert delays == sorted(delays)
        assert max(delays) <= 3600

    def test_attempts_are_counted_against_the_limit(self) -> None:
        assert should_retry(attempts=1, max_attempts=3)
        assert not should_retry(attempts=3, max_attempts=3)


class TestTimingRules:
    """ClassTiming is pure, so the reaper's rules are tested without a database."""

    def test_a_job_with_no_heartbeat_counts_as_dead(self) -> None:
        assert RUNTIME_TIMING.is_dead(None, START) is True

    def test_a_recent_heartbeat_is_alive(self) -> None:
        assert RUNTIME_TIMING.is_dead(START, START + timedelta(seconds=59)) is False

    def test_an_old_heartbeat_is_dead(self) -> None:
        assert RUNTIME_TIMING.is_dead(START, START + timedelta(seconds=61)) is True

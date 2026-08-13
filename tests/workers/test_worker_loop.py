"""The claim loop, against a real PostgreSQL (ADR-039).

Two of these need two connections at once, and that is the point of them. The
heartbeat and the reaper both work on rows another transaction is holding, and
every question about them - is the beat visible, does the sweep block - is a
question about what one session can see of another's uncommitted work. A test
with one connection answers it wrongly and passes.

The failure this file exists to prevent is invisible on short jobs. A five-second
ingest commits before any threshold expires, so the tests, the demo and the first
weeks of use all look fine; it surfaces on the first two-hundred-page manual, in
the plant, as a job that runs twice.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.platform.clock import SimulatedClock
from pdm.platform.jobs import ClassTiming, Job, JobClass, JobKind, JobQueue
from pdm.workers.loop import UnknownJobKind, Worker

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
TIMING = ClassTiming(heartbeat_seconds=30, dead_after_seconds=900)


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[Any]]:
    connection = connect(database_url)
    try:
        connection.execute("TRUNCATE job")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def pool(database_url: str) -> Iterator[ConnectionPool[Connection[Any]]]:
    # Two, as ADR-039 requires of a worker: the handler holds one for the whole
    # transaction and the heartbeat needs its own.
    made = ConnectionPool(database_url, min_size=2, max_size=4, open=True)
    try:
        yield made
    finally:
        made.close()


def _queue(clock: SimulatedClock, worker: str = "worker-1") -> JobQueue:
    return JobQueue(job_class=JobClass.AUTHORING, worker=worker, timing=TIMING, clock=clock)


def _worker(
    pool: ConnectionPool[Connection[Any]],
    clock: SimulatedClock,
    handlers: dict[str, Any],
    worker: str = "worker-1",
) -> Worker:
    return Worker(queue=_queue(clock, worker), pool=pool, clock=clock, handlers=handlers)


class TestOneJob:
    def test_an_empty_queue_says_so_rather_than_blocking(
        self, pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)

        assert _worker(pool, clock, {}).run_one() is False

    def test_the_handler_runs_and_the_job_is_done(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST, payload={"document_id": "a" * 64})
        conn.commit()
        seen: list[Job] = []

        assert (
            _worker(pool, clock, {JobKind.INGEST.value: lambda _, job: seen.append(job)}).run_one()
            is True
        )

        assert [job.kind for job in seen] == ["ingest"]
        assert _status(conn) == "done"

    def test_the_work_and_the_job_commit_together(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """ADR-017's promise, tested by writing something and reading it back
        from a different connection after the loop returns."""
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()

        def handler(job_conn: Connection[Any], job: Job) -> None:
            job_conn.execute("CREATE TEMP TABLE IF NOT EXISTS marker (id int)")
            job_conn.execute(
                "INSERT INTO job (job_class, kind, payload, status, attempts, "
                "max_attempts, available_at, created_at) "
                "VALUES ('authoring', 'follow-up', '{}', 'queued', 0, 3, %s, %s)",
                (START, START),
            )

        _worker(pool, clock, {JobKind.INGEST.value: handler}).run_one()

        rows = conn.execute("SELECT kind, status FROM job ORDER BY id").fetchall()
        assert rows == [("ingest", "done"), ("follow-up", "queued")]


class TestWhenAHandlerFails:
    def test_the_job_is_released_for_another_attempt(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()

        def explode(job_conn: Connection[Any], job: Job) -> None:
            raise RuntimeError("the PDF is not a PDF")

        assert _worker(pool, clock, {JobKind.INGEST.value: explode}).run_one() is True

        row = conn.execute("SELECT status, attempts, last_error FROM job").fetchone()
        assert row is not None
        assert row[0] == "queued"
        assert row[1] == 1
        assert "the PDF is not a PDF" in row[2]

    def test_the_error_survives_the_rollback_that_discards_the_work(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """The shape of the bug found in slice 3.4, one layer over.

        The handler's writes are rolled back - that is the point - and the reason
        it failed must not go with them, or the queue holds a job that has been
        tried three times with nothing to say why.
        """
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()

        def write_then_fail(job_conn: Connection[Any], job: Job) -> None:
            job_conn.execute(
                "INSERT INTO job (job_class, kind, payload, status, attempts, max_attempts, "
                "available_at, created_at) "
                "VALUES ('authoring', 'should-not-exist', '{}', 'queued', 0, 3, %s, %s)",
                (START, START),
            )
            raise RuntimeError("failed after writing")

        _worker(pool, clock, {JobKind.INGEST.value: write_then_fail}).run_one()

        kinds = [row[0] for row in conn.execute("SELECT kind FROM job ORDER BY id").fetchall()]
        assert kinds == ["ingest"]
        error = conn.execute("SELECT last_error FROM job").fetchone()
        assert error is not None and "failed after writing" in error[0]

    def test_a_kind_this_worker_does_not_handle_fails_the_job_not_the_worker(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """A worker that fell over on an unrecognised kind would stop working
        because somebody deployed a new job type into a queue it shares."""
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind="a-kind-from-a-later-slice")
        conn.commit()

        assert _worker(pool, clock, {JobKind.INGEST.value: lambda _, __: None}).run_one() is True

        error = conn.execute("SELECT last_error FROM job").fetchone()
        assert error is not None
        assert UnknownJobKind.__name__ in error[0]

    def test_the_last_attempt_leaves_the_job_failed_rather_than_queued(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST, max_attempts=1)
        conn.commit()

        def explode(job_conn: Connection[Any], job: Job) -> None:
            raise RuntimeError("no")

        _worker(pool, clock, {JobKind.INGEST.value: explode}).run_one()

        assert _status(conn) == "failed"


class TestTheHeartbeatIsVisibleWhileTheWorkIsInFlight:
    """The reason ADR-039 exists. Needs two connections to be able to fail."""

    def test_another_session_can_see_the_beat_before_the_job_commits(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()
        seen: list[datetime | None] = []

        def slow(job_conn: Connection[Any], job: Job) -> None:
            # Mid-job, from outside the job's transaction: exactly what the
            # reaper does.
            row = conn.execute("SELECT heartbeat_at FROM job WHERE id = %s", (job.id,)).fetchone()
            conn.commit()
            seen.append(row[0] if row else None)

        _worker(pool, clock, {JobKind.INGEST.value: slow}).run_one()

        assert seen == [START], "the claim's own heartbeat is invisible until commit (ADR-039)"

    def test_a_sweep_during_a_job_returns_rather_than_blocking_on_it(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """The reaper must not wait behind a running job's row lock.

        Without SKIP LOCKED this test does not fail - it hangs, which is the
        production behaviour it prevents: one long job stalls the reaping of
        every genuinely dead job in its class.

        It also shows the cost of the corrected design honestly. The claim is
        committed, so a sweep two hours later *does* take the job back while the
        handler is still working - which is exactly what the heartbeat thread is
        for, and this sweep is stale on purpose to prove the mechanism is the
        beat and not the lock.
        """
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()
        swept: list[list[Job]] = []

        def slow(job_conn: Connection[Any], job: Job) -> None:
            late = SimulatedClock(START + timedelta(hours=2))
            swept.append(_queue(late, worker="reaper").reap(conn))
            conn.commit()

        _worker(pool, clock, {JobKind.INGEST.value: slow}).run_one()

        assert [job.id for job in swept[0]]
        # The work still committed; only the row changed hands, and finish said
        # so rather than overwriting another worker's claim.
        assert _status(conn) == "queued"

    def test_a_fresh_beat_keeps_the_job_out_of_the_sweep(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """The mechanism that actually protects a twenty-minute ingest."""
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()
        swept: list[list[Job]] = []

        def slow(job_conn: Connection[Any], job: Job) -> None:
            # Ten minutes in, inside the fifteen-minute threshold: the claim's
            # own beat is committed and visible, so the sweep leaves it alone.
            late = SimulatedClock(START + timedelta(minutes=10))
            swept.append(_queue(late, worker="reaper").reap(conn))
            conn.commit()

        _worker(pool, clock, {JobKind.INGEST.value: slow}).run_one()

        assert swept == [[]]
        assert _status(conn) == "done"

    def test_a_job_whose_worker_died_is_reaped(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """The other side: nothing holds the row, and the sweep takes it back."""
        clock = SimulatedClock(START)
        queue = _queue(clock)
        job = queue.enqueue(conn, kind=JobKind.INGEST)
        queue.claim(conn)
        conn.commit()

        later = SimulatedClock(START + timedelta(hours=2))
        returned = _worker(pool, later, {}, worker="reaper").reap()

        assert [item.id for item in returned] == [job.id]
        assert _status(conn) == "queued"


class TestStopping:
    def test_the_loop_returns_after_the_job_in_hand(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """SIGTERM during an ingest finishes it rather than abandoning it, so a
        `docker compose down` does not cost the reaper's whole threshold."""
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind=JobKind.INGEST)
        conn.commit()
        worker = _worker(pool, clock, {})

        def stop_midway(job_conn: Connection[Any], job: Job) -> None:
            worker.stopping = True

        worker.handlers[JobKind.INGEST.value] = stop_midway
        worker.run_forever()

        assert _status(conn) == "done"

    def test_an_idle_worker_sweeps_and_waits_rather_than_spinning(
        self, pool: ConnectionPool[Connection[Any]]
    ) -> None:
        clock = SimulatedClock(START)
        worker = _worker(pool, clock, {})

        # One pass: nothing to claim, so it reaps and sleeps once, and the
        # simulated clock records how long for.
        original = clock.sleep

        def sleep_once(seconds: float) -> None:
            original(seconds)
            worker.stopping = True

        clock.sleep = sleep_once  # type: ignore[method-assign]
        worker.run_forever()

        assert clock.now() == START + timedelta(seconds=TIMING.heartbeat_seconds)


def _status(conn: Connection[Any]) -> str:
    row = conn.execute("SELECT status FROM job ORDER BY id LIMIT 1").fetchone()
    assert row is not None
    return str(row[0])


class TestWhatTheCodeReviewFound:
    """Three of them, and the first is the mechanism this slice was reopened for."""

    def test_the_thread_beats_while_the_handler_works(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """Deleting `_beating` used to leave the suite green.

        The earlier test passed on the heartbeat `claim` writes, which is enough
        for ten simulated minutes against a fifteen-minute threshold and says
        nothing about the thread. This one waits in real time for a real beat,
        with the interval turned down to a second, and fails if nothing beats.
        """
        clock = SimulatedClock(START)
        fast = ClassTiming(heartbeat_seconds=1, dead_after_seconds=3)
        queue = JobQueue(job_class=JobClass.AUTHORING, worker="worker-1", timing=fast, clock=clock)
        queue.enqueue(conn, kind=JobKind.INGEST)
        conn.commit()
        beats: list[datetime] = []

        def slow(job_conn: Connection[Any], job: Job) -> None:
            # The beat is written by another connection while this one holds an
            # open transaction, so it is read from a third.
            time.sleep(1.4)
            clock.advance(timedelta(seconds=90))
            time.sleep(1.4)
            row = conn.execute("SELECT heartbeat_at FROM job WHERE id = %s", (job.id,)).fetchone()
            conn.commit()
            assert row is not None and row[0] is not None
            beats.append(row[0])

        worker = Worker(queue=queue, pool=pool, clock=clock, handlers={JobKind.INGEST.value: slow})
        worker.run_one()

        assert beats and beats[0] > START, "the heartbeat thread never reported in"

    def test_a_job_that_kills_its_worker_is_not_reaped_for_ever(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """`fail` counts the attempts, and a job that OOMs its worker never
        reaches `fail`. Re-queued unconditionally it would be claimed, kill the
        worker, and be reaped again for as long as anything restarted it."""
        clock = SimulatedClock(START)
        queue = _queue(clock)
        queue.enqueue(conn, kind=JobKind.INGEST, max_attempts=1)
        queue.claim(conn)
        conn.commit()

        later = SimulatedClock(START + timedelta(hours=2))
        returned = _worker(pool, later, {}, worker="reaper").reap()

        assert [job.status.value for job in returned] == ["failed"]
        assert _status(conn) == "failed"

    def test_a_reaped_workers_failure_cannot_reopen_someone_elses_job(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """The other exit `finish` was hardened against, left open until now.

        The first worker is reaped mid-job and a second claims it; when the first
        eventually fails, an unscoped UPDATE would flip the row back to `queued`
        under the second worker - and the same symptom would be drafted twice.
        """
        clock = SimulatedClock(START)
        first = _queue(clock, worker="worker-1")
        job = first.enqueue(conn, kind=JobKind.INGEST)
        claimed = first.claim(conn)
        conn.commit()
        assert claimed is not None

        # Reaped, then taken by somebody else.
        late = SimulatedClock(START + timedelta(hours=2))
        _queue(late, worker="reaper").reap(conn)
        second = _queue(late, worker="worker-2")
        assert second.claim(conn) is not None
        conn.commit()

        # The original worker finally gives up.
        first.fail(conn, claimed, "died late")
        conn.commit()

        row = conn.execute("SELECT status, claimed_by FROM job WHERE id = %s", (job.id,)).fetchone()
        assert row == ("running", "worker-2")

    def test_a_worker_with_no_handlers_claims_nothing(
        self, conn: Connection[Any], pool: ConnectionPool[Connection[Any]]
    ) -> None:
        """What `worker-runtime` depends on entirely (ADR-040).

        Claiming a job only to fail it as an unknown kind would burn the attempts
        of a job whose handler ships next month - and that container exists
        precisely because layers 1 and 3 have not been built.
        """
        clock = SimulatedClock(START)
        _queue(clock).enqueue(conn, kind="a-kind-from-a-later-slice")
        conn.commit()

        assert _worker(pool, clock, {}).run_one() is False
        assert _status(conn) == "queued"
        attempts = conn.execute("SELECT attempts FROM job").fetchone()
        assert attempts == (0,)

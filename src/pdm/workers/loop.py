"""The loop both workers run: claim, do, commit, repeat (ADR-039).

Shared between `workers/runtime` and `workers/authoring` so that when the trigger
loop and the dispatch tick arrive they are a handler in a table rather than a
second copy of this. The two entrypoints stay separate packages and must not
import each other (invariant 12, enforced in `.importlinter`); this module is
below both and imports neither.

Three things here are not obvious and each has a reason in ADR-039:

  * **the handler runs inside the job's transaction** (ADR-017), so a drafted
    playbook and the job that produced it commit together or not at all;
  * **the claim commits before the work starts**, because an uncommitted claim
    is invisible to every other session - a heartbeat sent from anywhere else
    matches no row, and a rollback would take the attempt counter with it;
  * **a failure is recorded on a second connection**, because the transaction
    that would have carried the error is the one being rolled back;
  * **a thread beats while the handler works**, because the reaper re-queues
    anything silent for longer than the class threshold and the long jobs are
    exactly the ones that would then run twice.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import FrameType
from typing import Any

from psycopg import Connection
from psycopg_pool import ConnectionPool

from pdm.platform.clock import Clock
from pdm.platform.jobs import Job, JobQueue

log = logging.getLogger(__name__)

# What a handler is: everything it needs to do the work, and nothing about the
# queue. A handler that could finish or fail its own job would be a handler that
# could commit half of one.
Handler = Callable[[Connection[Any], Job], None]


class UnknownJobKind(Exception):
    """A job whose kind no handler in this worker claims.

    Fails the job rather than crashing the worker. A runtime worker that fell
    over on an unrecognised kind would stop dispatching tickets because somebody
    deployed a new job type, and the queue is shared.
    """


@dataclass
class Worker:
    """One process, one job class, one job at a time.

    Single-threaded on purpose. Concurrency inside a worker would need a
    connection per job plus one heartbeat each, and ADR-017 already holds the
    authoring worker at one because the GPU behind it is one.
    """

    queue: JobQueue
    pool: ConnectionPool[Connection[Any]]
    clock: Clock
    handlers: dict[str, Handler]
    # Set by SIGTERM. Read between jobs, never mid-job: a job abandoned halfway
    # is one the reaper has to rediscover fifteen minutes later, and a
    # `docker compose down` during an ingest should not cost that (ADR-039).
    stopping: bool = field(default=False)

    def install_signal_handlers(self) -> None:
        def stop(signum: int, frame: FrameType | None) -> None:
            log.info("signal %s received; finishing the current job", signum)
            self.stopping = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)

    def run_forever(self) -> None:
        """Until SIGTERM. Sleeps through the Clock, so a test can compress it."""
        while not self.stopping:
            if not self.run_one():
                # Nothing to do: sweep for jobs whose worker died, then wait.
                # Between jobs rather than on a timer, because nothing is waiting
                # on a job that has already been dead for the whole threshold,
                # and a timer thread is a second thing that can be mid-
                # transaction when SIGTERM arrives (ADR-039).
                self.reap()
                self.clock.sleep(self.queue.timing.heartbeat_seconds)

    def run_one(self) -> bool:
        """Claim, then do the work. False when the queue had nothing.

        A worker with no handlers claims nothing at all. `worker-runtime` runs
        that way until layers 1 and 3 give it something to do, and claiming a job
        only to fail it as an unknown kind would burn the attempts of a job whose
        handler ships next month.

        **Two transactions, and the split is not an optimisation.** The claim
        commits on its own; the handler and `finish` share the second.

        ADR-039 first said one transaction for both, and a test disproved it in
        two ways at once. An uncommitted claim is invisible to every other
        session, so a heartbeat sent from a second connection matches no row -
        the beat cannot be made visible from outside a transaction that has not
        committed, which was the whole of that decision. And a handler failure
        rolled the claim back along with the work, taking `attempts` with it: a
        poison job would be retried for ever, with the counter that exists to
        stop it reset on every pass.

        ADR-017's guarantee survives the split, because it is about the *result*:
        the handler's writes and the `done` row still commit together, so a
        playbook with no finished job and a finished job with no playbook both
        remain impossible. What is given up is narrower - a crash between the two
        leaves a job `running` that nobody is running - and that is the case the
        reaper was built for.
        """
        if not self.handlers:
            return False

        with self.pool.connection() as conn, conn.transaction():
            claimed = self.queue.claim(conn)
        if claimed is None:
            return False

        log.info("claimed job %s (%s)", claimed.id, claimed.kind)
        with self.pool.connection() as conn, self._beating(claimed):
            try:
                with conn.transaction():
                    self._handle(conn, claimed)
                    if not self.queue.finish(conn, claimed):
                        # The reaper gave up on this worker mid-job and somebody
                        # else may be running it now. The work is committed
                        # either way; that it happened twice is worth a line.
                        log.warning(
                            "job %s was no longer ours when it finished: the work committed, "
                            "the row belongs to another worker",
                            claimed.id,
                        )
            except Exception as error:
                # Recorded after the rollback, so the error is not written into
                # the transaction that is discarding everything else - the shape
                # of the access-log bug found in slice 3.4.
                log.exception("job %s failed", claimed.id)
                self.fail(claimed, error)
        return True

    @contextmanager
    def _beating(self, job: Job) -> Iterator[None]:
        """Report that this worker is still alive, for as long as the job runs.

        A thread, which ADR-039 first refused and a test then required. With the
        claim committed the reaper can see the job, and it re-queues anything
        whose last beat is older than the class threshold - fifteen minutes for
        authoring, against manual ingests that ADR-017 puts at five to twenty.
        Without this, the long jobs are exactly the ones that get run twice.

        Cheap to keep honest: the thread owns nothing but a connection it borrows
        per beat, holds no transaction, and is joined before `run_one` returns. It
        cannot be the thing that is mid-write when SIGTERM arrives, which was the
        objection to having one.

        A beat that matches no row means the reaper has already given the job to
        somebody else. The thread stops rather than beating into the void; the
        handler runs on, and `finish` is what notices.
        """
        done = threading.Event()

        def beat() -> None:
            while not done.wait(self.queue.timing.heartbeat_seconds):
                try:
                    with self.pool.connection() as conn:
                        alive = self.queue.heartbeat(conn, job)
                        conn.commit()
                except Exception:
                    log.exception("heartbeat for job %s failed", job.id)
                    continue
                if not alive:
                    log.warning("job %s is no longer claimed by this worker", job.id)
                    return

        thread = threading.Thread(target=beat, name=f"heartbeat-{job.id}", daemon=True)
        thread.start()
        try:
            yield
        finally:
            done.set()
            thread.join(timeout=self.queue.timing.heartbeat_seconds)

    def _handle(self, conn: Connection[Any], job: Job) -> None:
        handler = self.handlers.get(job.kind)
        if handler is None:
            raise UnknownJobKind(
                f"this worker handles {sorted(self.handlers)} and job {job.id} is '{job.kind}'"
            )
        handler(conn, job)

    def reap(self) -> list[Job]:
        with self.pool.connection() as conn:
            returned = self.queue.reap(conn)
            conn.commit()
        for job in returned:
            log.warning(
                "job %s was abandoned by %s and is back in the queue", job.id, job.claimed_by
            )
        return returned

    def fail(self, job: Job, error: BaseException) -> None:
        """Record the failure on its own connection.

        The transaction that would have carried it has just rolled back, taking
        any write inside it with it. Recorded from outside, the error survives -
        the same shape as the access-log line lost to a rollback in slice 3.4.
        """
        with self.pool.connection() as conn:
            self.queue.fail(conn, job, f"{type(error).__name__}: {error}")
            conn.commit()

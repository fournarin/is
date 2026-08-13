# ADR-039: What a worker does between claiming a job and finishing it

## Context

The job table has had a claim, a heartbeat, a reaper and two classes since slice
1.3, and nothing has ever run a loop over it. `docker-compose.yml` names the
entrypoint - `python -m pdm.workers.authoring` - beside a comment saying it
arrives with the slice that gives it a claim loop. This is that slice, and
writing the loop turns three things that read as settled into open questions.

**ADR-017 requires a job and its result to commit in one transaction.** That is
what makes "no playbook without a job, no job without a playbook" true. Taken
literally it also means the whole of a twenty-minute manual ingest happens inside
one open transaction, and two things follow that nobody has written down:

1. **A heartbeat written in that transaction is invisible.** No other session can
   see an uncommitted `UPDATE`, so from the reaper's point of view the worker
   went silent the moment it claimed the job.
2. **The reaper blocks instead of reaping.** Its `UPDATE` has no `SKIP LOCKED`,
   and the claim holds a row lock for the life of the transaction, so a sweep
   that touches a running job waits for it - stalling the reaping of every other
   dead job in that class behind a job that is perfectly healthy.

The third question is smaller and more immediate: a drafting job needs a
*question* to retrieve with, and slice 3.5 left where it comes from unsettled.

## Decision

### 1. One transaction for the work, a second connection for the heartbeat

The handler runs inside the job's transaction, as ADR-017 requires. The heartbeat
runs on its own connection and commits on its own, so it is visible while the
work is still in flight.

Two connections per running job is the price of ADR-017's guarantee, and it is
the smaller of the two costs available: the alternative - committing progress in
pieces - is what ADR-017 exists to refuse.

### 2. The reaper skips locked rows

`FOR UPDATE SKIP LOCKED` on the reaper's selection, the same construct the claim
already uses. A row still held by a live transaction is a job still running, and
the sweep's job is to find the ones nobody holds.

### 3. The worker reaps its own class, and only between jobs

No separate reaper process. A sweep runs when the queue comes up empty, which is
exactly when the worker has nothing else to do and when a stalled job is worth
noticing. Both workers therefore reap, each with its own class's threshold -
which is the whole reason ADR-026 gave the two classes separate timings.

### 4. Shutdown finishes the job in hand

`SIGTERM` sets a flag; the loop returns after the current job commits. It does
not abandon the transaction, because a job killed mid-flight is a job the reaper
has to rediscover fifteen minutes later, and a `docker compose down` during an
ingest should not cost fifteen minutes of nothing happening.

A second `SIGTERM` is not special-cased. `SIGKILL` already exists for the case
where somebody means it, and the reaper is what covers the aftermath.

### 5. The poll interval is the class's own heartbeat interval

No new number. A queue polled more often than its workers report in is a queue
being polled for the sake of it, and `policy.yaml` already carries one interval
per class with a recorded reason (ADR-026).

### 6. A drafting job carries its question in the payload

`{symptom_code, machine_model, question}`. The question is supplied by whoever
enqueues the job, and this record does not decide where *they* get it - an
engineer typing it and a rule's description are both plausible and the choice
belongs to the slice that builds the enqueueing screen.

What it does decide: **the question is stored on the job**. A drafting result is
reproducible only if the question that produced it is recorded, and a job that
derived its own query from a symptom code at run time would produce different
drafts as that derivation changed, with nothing saying so.

### 7. A handler that raises fails the job, and the transaction rolls back

No partial results. `JobQueue.fail` then records the error on its own connection,
because the transaction that would have carried it is the one being rolled back -
a failure recorded inside the rolled-back transaction is a failure nobody hears
about, which is the same shape as the access-log bug found in slice 3.4.

## Reasons

**The heartbeat problem is invisible until it is expensive.** Everything passes on
short jobs: a five-second ingest commits before any threshold expires, so the
tests, the demo and the first weeks of use all look fine. It surfaces on the
first two-hundred-page manual, in the plant, as a job that runs twice.

**Reaping between jobs rather than on a timer keeps the worker single-threaded.**
A timer thread sharing a connection pool with the handler is a second thing that
can be mid-transaction when `SIGTERM` arrives, for a sweep that is not urgent -
nothing is waiting on a dead job that has already been dead for fifteen minutes.

## Consequences

- **A worker needs two connections**, so the pool minimum for a worker process is
  two rather than one. Undersized, the heartbeat blocks waiting for a connection
  held by the job it is reporting on, which is a deadlock that only appears under
  load.
- **`repo.reap` changes shape**, and its existing tests keep passing because they
  test the timing rather than the locking. The lock behaviour needs a test with
  two real connections, which is the only way to write it.
- **The runtime worker is not built here.** It has nothing to run: the trigger
  loop and the dispatch tick are layers 1 and 3. The loop in `workers/` is shared
  so that when they arrive, the entrypoint is a handler table and not a second
  copy of this logic.
- **Nothing enqueues a drafting job yet.** The handler exists and is tested by
  enqueueing one directly; the screen that asks for a draft comes with the review
  interface.

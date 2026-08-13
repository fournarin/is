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

### 1. The claim commits first; the work and the finish share the second transaction

*This section was written the other way round - one transaction for both, with
the heartbeat on a second connection - and a test disproved it before the record
was merged. What follows is what the measurement forced, with the original
reasoning kept below it because the correction is the useful part.*

**An uncommitted claim is invisible, including to the heartbeat.** The beat is
scoped to `claimed_by` and `status = 'running'`, which is right - a beat from a
process the reaper has replaced must not resurrect its claim - and from any other
session the row is still `queued` with no claimer, so the beat matches nothing at
all. A heartbeat cannot be made visible from outside a transaction that has not
committed. The first version of this ADR asked for exactly that.

**And a handler failure rolled the claim back with the work**, taking `attempts`
with it. A job that fails every time would be retried for ever, with the counter
that exists to stop it reset on every pass.

So: the claim commits on its own, and the handler's writes commit with `finish`.

**ADR-017's guarantee survives this, because it is about the result.** "No
playbook without a job, no job claiming success with no playbook" holds as long
as the work and `done` commit together, which they do. What is given up is
narrower: a crash between the two leaves a job `running` that nobody is running,
and that is the case the reaper already exists for.

### 2. The reaper skips locked rows

`FOR UPDATE SKIP LOCKED` on the reaper's selection, the same construct the claim
already uses. A row still held by a live transaction is a job still running, and
the sweep's job is to find the ones nobody holds.

### 3. A thread beats while the handler works

*Also written the other way round first: "no timer thread, one beat is enough".
With the claim now committed the reaper can see the job, so the class threshold
applies to it - fifteen minutes for authoring, against manual ingests ADR-017
puts at five to twenty minutes. Without a periodic beat, the long jobs are
precisely the ones that get reaped and run twice, which is the failure this
record was opened to prevent.*

A daemon thread beats every `heartbeat_seconds` on a borrowed connection, holds
no transaction, and is joined before the loop returns. The objection to a thread
was that it is a second thing that can be mid-write when `SIGTERM` arrives; this
one cannot be, because it owns nothing between beats.

A beat that matches no row means the reaper has already given the job away. The
thread stops rather than beating into the void, the handler runs on, and `finish`
is what notices - it is scoped to the claiming worker, so a worker that was
reaped cannot write `done` over a row somebody else is now running.

### 4. The worker reaps its own class, and only between jobs

No separate reaper process. A sweep runs when the queue comes up empty, which is
exactly when the worker has nothing else to do and when a stalled job is worth
noticing. Both workers therefore reap, each with its own class's threshold -
which is the whole reason ADR-026 gave the two classes separate timings.

### 5. Shutdown finishes the job in hand

`SIGTERM` sets a flag; the loop returns after the current job commits. It does
not abandon the transaction, because a job killed mid-flight is a job the reaper
has to rediscover fifteen minutes later, and a `docker compose down` during an
ingest should not cost fifteen minutes of nothing happening.

A second `SIGTERM` is not special-cased. `SIGKILL` already exists for the case
where somebody means it, and the reaper is what covers the aftermath.

### 6. The poll interval is the class's own heartbeat interval

No new number. A queue polled more often than its workers report in is a queue
being polled for the sake of it, and `policy.yaml` already carries one interval
per class with a recorded reason (ADR-026).

### 7. A drafting job carries its question in the payload

`{symptom_code, machine_model, question}`. The question is supplied by whoever
enqueues the job, and this record does not decide where *they* get it - an
engineer typing it and a rule's description are both plausible and the choice
belongs to the slice that builds the enqueueing screen.

What it does decide: **the question is stored on the job**. A drafting result is
reproducible only if the question that produced it is recorded, and a job that
derived its own query from a symptom code at run time would produce different
drafts as that derivation changed, with nothing saying so.

### 8. A handler that raises fails the job, and the transaction rolls back

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
  two rather than one. Undersized, the heartbeat thread blocks waiting for a
  connection held by the job it is reporting on, which is a deadlock that only
  appears under load.
- **A job can still run twice**, when a worker is stalled rather than dead - the
  beats stop, the reaper takes the job, and the original wakes up and completes
  its transaction. The work commits; the row does not, because `finish` is scoped
  to the claimer, and the second run is logged as a warning rather than silently
  overwriting. Handlers therefore have to tolerate being run twice, which ingest
  does by construction (it replaces a document's pages and chunks) and drafting
  does not (it would file two proposals for one symptom). Left as it stands and
  written down here rather than solved with a unique index that would need a
  vocabulary for "the same drafting request".
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

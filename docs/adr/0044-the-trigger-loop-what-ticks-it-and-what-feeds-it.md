# ADR-044: The trigger loop - what ticks it, what feeds it, and what happens to a ticket the world overtakes

## Context

Layer 1 has been able to detect since slice 5.1 and to predict since 5.2, and
**nothing has ever called it outside a test**. `Triggers.observe` is constructed
by two test files and one measurement script; `worker-runtime` runs with
`handlers={}` and only reaps. The system can therefore be said to monitor and
predict, and a technician standing at a machine would see nothing, because no
process reads a signal and no Finding has ever become a ticket outside a
transaction a test opened.

Closing that gap needs four things decided, and none of them is settled by an
existing record.

**What ticks it.** ADR-039 built one loop over the job queue and left a note that
the trigger loop would arrive "as a handler in a table rather than a second copy
of this". A handler runs when a job is claimed; nothing enqueues a job on a
schedule, and nothing in the system has ever needed a periodic anything before.

**What feeds it.** `SyntheticSource.stream()` yields twelve hours of a scenario
as fast as the caller can iterate it. A loop that consumed the stream would not
be a loop - it would produce every Finding of the run in one instant, stamped
with one decision time, and the shape of the thing being demonstrated would be
lost. Worse, the scenario's timeline is March and the process's clock is not, so
source time and decision time have to be reconciled by *something* (ADR-028), and
no module owns that job.

**What happens when a prediction is overtaken.** `repo.supersede` says in its own
docstring that two work orders for one fault is what ADR-023 §7 exists to
prevent. Until now nothing issued work orders from Findings at all, so the
sentence was true and idle. The moment the loop issues one, a superseded
prediction leaves a live ticket behind describing a crossing that has already
happened - and an expired one leaves a ticket for a crossing that never will.
Both sit in the open queue, and `load_ratio` is a sum over the open queue.

**Whether invented data may reach a technician silently.** The only signal source
that exists is synthetic. ADR-033 already refused to let a synthetic *manual* be
servable; the same question arrives one layer along, and the answer cannot be
left to whoever writes the compose file.

## Decision

### 1. The tick is a job that schedules its own successor

`JobKind.OBSERVE`, class `runtime`. The handler reads what is due, runs the batch,
issues the tickets, and **enqueues the next tick in the same transaction**. So a
tick's Findings, the work orders they produced and the appointment for the next
round commit together or not at all (ADR-017). There is no state in a timer, no
second loop beside the queue, and the whole of layer 1's schedule is a row
anybody can `SELECT`.

The alternative - a thread or an interval loop inside the process - was rejected
for the reason ADR-039 §4 rejected a reaper thread: it is a second thing that can
be mid-transaction when SIGTERM arrives, and it would put the pipeline's pulse
somewhere no other process can see it.

### 2. The period is the runtime class's heartbeat interval

No new constant. `policy.yaml` already carries `jobs.runtime.heartbeat_seconds`
with a recorded reason, and it is how often the worker polls the queue anyway: a
tick scheduled less often than the poll is a tick waiting for a wake-up it has
already had (the same argument as ADR-039 §6).

It is also the honest ceiling on detection latency. `R-safety-interlock-open` has
`for_seconds: 0`, which means "tell somebody the moment this is seen" - so the
tick period *is* the delay on the interlock alarm, and that number should be the
smallest one in the file rather than a new one chosen for tidiness.

### 3. A dead chain heals itself when the queue comes up empty

A self-perpetuating chain has one failure mode that matters: a tick that
exhausts its attempts schedules nothing, and layer 1 stops for ever, silently,
with the rest of the system still running.

`Worker` therefore takes an optional `on_idle` callback, invoked where the reaper
already runs - when a claim finds nothing. `worker-runtime` uses it to enqueue a
tick if none is pending. The authoring worker passes nothing and is unchanged.

The re-seed is idempotent through `JobQueue.pending`, the same primitive ADR-040
built for recognising the second press of a button: while a tick is queued or
running - including one waiting out a retry backoff - nothing is enqueued.
Ordinary retries stay with the queue; this catches only the case where the chain
is actually gone.

### 4. Signals arrive through a paced feed, and compression belongs to the clock

*Written first with a `speed` factor on the feed, and corrected before merge -
the correction is the useful part, so both are kept.*

`signals/feed.py` holds a source's iterator and hands out, per tick, the signals
whose source time has come due, from a fixed origin:

```
source_due = source_origin + (now − decision_origin)
```

**One second of decision time buys one second of scenario, and a compressed demo
runs a compressed clock** - `ScaledClock`, real sleeps and an accelerated `now`,
which is what ADR-028 built the port for and what `SimulatedClock` cannot do in a
long-running process (its `sleep` returns instantly and the worker would spin).

The first version put the factor on the feed instead, handing signals over 60×
faster while decision time ran at one second per second. That splits the two axes
apart, and **every window in this system is measured on decision time**: at 60×
a ticket read "expected to reach the threshold in about six hours" for a crossing
six minutes away, `expire_stale_predictions` could never fire inside a
twelve-minute run - making the whole withdrawal path this record adds
unreachable in the only mode anybody would demo - and the thirty-minute cooldown
covered thirty *hours* of plant time. One knob, in the port that exists for it.

**A signal's `timestamp` is never modified.** It is source time, it is what the
debounce measures duration with, and it is what `SyntheticSource.ground_truth()`
is anchored to (ADR-032). Rewriting it to look like now would produce a stream
whose measured ETA error could not be compared with any figure in
`docs/prediction-baseline.md`. The feed changes *when* a signal is handed over,
never what it says.

An exhausted scenario is quiet, not restarted. Replaying a run that already
happened would re-raise findings for failures the same data already showed, and a
loop that never ends would make "the demo ran for an hour" mean nothing.

### 5. A synthetic source must be asked for, and says what it is

`SIGNAL_SOURCE` has no default in code. Unset, `worker-runtime` runs exactly as
it does today: **no handlers and no chain**, reaping only, and a log line saying
layer 1 is idle because no source was configured - so a plant deployment that has
not been wired to OPC UA yet cannot quietly invent its own data. Starting the
chain anyway would mean a job row every ten seconds for ever to run an expiry
sweep over predictions nothing can produce.

Set to `synthetic`, the process announces at boot which scenario, seed and speed
it is running, and states that every ticket it produces describes a machine that
is not there. The compose file sets it, because the compose file is the demo and
the plant has given us nothing to read; the value is one line and visible.

### 6. Both a detection and a forecast become a work order, inside the tick

`Observation.raised` and `Observation.forecast` are treated the same way here.
Predicted work is the clearest example of the lower-priority work ADR-011 wants a
quiet shift to absorb, and a prediction that never becomes a ticket is a
prediction nobody acts on.

A repeat is not a ticket, which is the whole of ADR-023 and is already true one
level down: `observe` returns repeats as counts, and this handler issues orders
only from what was raised.

`under_repair` is read from the **open tickets**, and from the Findings behind
them in whatever state those are: the references an open order carries, resolved
to (machine, rule). Not a query per machine, and not a new column - the
trace-back direction `finding_ref` was kept for (ADR-030) is exactly this.

*This too was written the other way round: the live Findings that had an open
ticket. That is dead code, and the review found it before merge. A live Finding
suppresses its own rule as a repeat (ADR-023 §2) several branches before the
repair check is reached, so a map built from live Findings can only contain pairs
that are already handled - the mechanism would have been carried, and tested, and
never once have fired. The case ADR-023 §4 is actually about is invisible from
that side: a technician resolves the Finding and then spends an hour repairing
the machine, the cooldown covers thirty minutes of it, and for the rest the rule
is free to raise a second ticket for the job somebody is inside the machine
doing.*

### 7. A ticket nobody has touched is cancelled when its Finding is overtaken

When a detection supersedes a prediction, or the expiry sweep retires one, the
prediction's ticket is cancelled **if it is still `queued`**. Forecasts are
ticketed before detections within a tick, so that a batch carrying both the trend
and the crossing it predicted has a ticket to withdraw when it withdraws one -
the other order leaves a ticket issued against an already-superseded Finding,
which nothing can ever retire. If somebody has
taken it - assigned, in progress, handed over - it is left alone. A ticket
disappearing from under a technician who is standing at the machine is worse than
a ticket whose sentence has aged, and the second ticket the detection raises
carries the current reason anyway.

No new field records why. The cancelled order points at its Finding, and that row
says `expired`, or `superseded` with `superseded_by` - which is what a trace-back
reference is for. `cancelled` needs no outcome (the constraint in migration 0006
requires one only for `closed`), and inventing `no_problem_found` here would feed
the one false-alarm signal Loop 2 will ever have with events no person observed.

### 8. The ticket's ETA is not refreshed when the fit moves

`refresh_prediction` already moves the Finding's `eta` on every re-fit. The work
order's copy stays as issued.

`reason` is written once, at creation (ADR-005, ADR-041). Moving `eta` without
rewriting the sentence produces a ticket whose number and whose words disagree,
which is worse than one that is merely old; rewriting the sentence is what
ADR-005 forbids. The freshest prediction is one join away through `finding_ref`,
which is where the screen already reads "seen N times" from.

## Reasons

**Putting the pulse in the queue costs nothing and buys evidence.** A failing tick
appears in `job.last_error` with an attempt count, not only in a log somebody has
to be watching. `SELECT * FROM job WHERE kind = 'observe'` answers "is layer 1
alive" from a psql prompt, which is the question an operator asks first and the
one a background thread answers worst.

**The feed is where the two time axes meet, and it had to be somewhere.** ADR-028
separated source time from decision time and every module since has been careful
to say which it holds. Joining them is a real operation with a real policy in it,
and leaving it implicit in a composition root would mean the policy exists but
nothing states it.

**Cancelling only untouched tickets is the general shape of every later
correction.** Layer 3 will want to move work, and the same line applies: the
system may rearrange what nobody has picked up, and must not rearrange what
somebody has.

## Consequences

- **Layer 1's memory belongs to one process.** The debounce and the trend windows
  live in the `Triggers` instance held by whichever worker runs the tick (ADR-042
  §1). A second `worker-runtime` replica would claim some ticks with an empty
  window and produce fewer predictions with no error anywhere. One replica is
  what `docker-compose.yml` runs, and running two is a decision that now needs a
  record.
- **The reaper runs on every idle cycle rather than rarely**, because the queue is
  now empty only in the seconds between ticks. It is a `SKIP LOCKED` update over a
  small table per class; noted rather than measured, and worth measuring if the
  job table ever grows.
- **A tick that fails loses its batch of signals.** The transaction rolls back,
  the feed has already handed those signals over, and the next tick asks for what
  is due at *its* time. A retry does not re-read them. This is acceptable because
  a rule fires on a condition that persists - a hot motor is still hot ten seconds
  later - and because the in-memory state does *not* roll back: the debounce run
  and the trend window survive, so the very next hot reading raises the Finding
  the lost batch would have raised, rather than starting the excess again. It
  would be unacceptable for anything that must see every sample, which nothing in
  layer 1 is.
- **The job table grows by a row per tick** - one every ten seconds, about
  eight and a half thousand a day, where the authoring queue produced one per
  manual. They are small and the claim reads a partial index of queued rows, so
  nothing slows down; but finished ticks are a heartbeat rather than evidence,
  and unlike an ingest job nobody will ever want to read one. Pruning them needs
  a retention number, and a number with no source is what `workflow.md` 4.1
  refuses, so it is left for the slice that has one.
- **Nothing collapses two chains back into one.** `ensure_tick_queued` only ever
  adds, so a fork - two replicas, or a commit that was in doubt - leaves two
  ticks running in parallel for ever. Harmless to the data (the unique index
  turns the duplicate work into `lost_races`) and doubling the tick rate;
  the same one-replica assumption as the first consequence, and it ends the same
  way, with a record.
- **The first fit is the one the ticket carries**, and
  `docs/prediction-baseline.md` says the first fit is the least accurate, because
  error grows with horizon. Re-issuing a ticket when the ETA moves further than
  its own confidence interval is the obvious answer and is not decided here.
- **Prediction is now on in a real process**, so the false-alarm count measured in
  slice 5.2 - twenty-one forecasts on a channel that never crosses, collapsed by
  suppression into one record - is now twenty-one forecasts collapsed into one
  record **and one ticket**. The ticket is the part that costs a person something,
  and it is the argument for reducing the number rather than reporting it.
- **Nothing dispatches these tickets yet.** They enter the queue with
  `status = queued` and no assignee, which is what layer 3 will read (ADR-011).
  Until it exists, the demo shows a queue that grows and never empties.

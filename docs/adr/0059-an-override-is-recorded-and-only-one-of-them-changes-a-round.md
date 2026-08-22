# ADR-059: An override is recorded, and only one of the two changes a round

Revisits [ADR-005](0005-every-ticket-carries-its-reason.md), which said the
system must explain itself to a person, and
[ADR-011](0011-load-ratio-switches-dispatch-behaviour.md), which kept the load
gate separate so that what it is holding could be shown to a shift lead. Both
described the sentence going one way. This record says what happens when the
person answers.

## Context

Two overrides are in the design and neither had anywhere to land.

A technician looks at the job the queue put first and disagrees with it. A shift
lead looks at four tickets the gate is holding and decides one of them is going
out anyway - the line is stopping for a die change, the technician is already at
that machine, the customer audit is on Thursday. Both are ordinary, both will
happen on the first real shift, and both were, until this slice, invisible: the
system would have been overruled verbally and gone on reporting that it had
decided.

Three things make that worse than it sounds.

**A round is never stored.** ADR-050 computes the gate's report when somebody
asks, from the same `dispatch()` the rounds use, because "four tickets are being
held" is a question about the queue in front of a person and the answer that was
true five minutes ago is the wrong one. The consequence is that the band, the
ratio and the shift a decision was taken against exist only while somebody is
looking at them. An override recorded without them cannot be read back in the
context that produced it, and one recorded later cannot be reconstructed at all.

**`dispatch()` may not read a table.** Invariant 10 and ADR-045 §6 make the round
a function of its arguments, which is what lets the simulator run hundreds of
scenarios in CI and lets Loop 6 replay real decisions against different weights.
A release that `dispatch()` looked up for itself would end both.

**An override with no reason is indistinguishable from a bug.** Six weeks later,
a released ticket with no sentence beside it reads as the gate having failed.

## Decision

### 1. Both overrides are recorded; only the release changes anything

`work_order_override` records who, when, which order, which kind, and the typed
reason. `reason` is `NOT NULL` with a non-empty `CHECK`, in the database rather
than only in the request model that happens to be in front of it today.

A **disagreement** records and changes nothing - not the score, not the
ordering, not the round. This is the decision, not an omission. A queue that can
be argued down is not a queue: the easy job gets talked to the top, on the shift
where that is worst, and the load gate stops meaning anything. What the button
is worth is the record. A hundred disagreements against the same term is an
argument about the score that can be had with evidence, and it is worth nothing
if it was never written down while somebody was standing at the machine.

A **release** takes one held ticket out of the gate's hands, because that is
what the shift lead pressed it for.

### 2. The released set reaches `dispatch()` on the queue, not as a table

`Queued` carries a `released` flag. The service reads the overrides and sets it;
the pure function is handed the answer along with the roster and the orders, and
its signature does not change. This is the same pattern as ADR-030's
self-contained work order: copy what is needed to where it is needed, rather
than letting the algorithm reach for it.

A release has **no expiry**, and that is a decision rather than an omission. Any
lifetime would be a constant with nothing behind it - not a manual, not a
measurement, not a recorded decision - and it would silently un-release work a
supervisor said to release. It stops mattering on its own: a round ranks only
orders that are still queued, so a released order that gets placed is not one of
them any more.

### 3. Released work is priced into the shift before the top-up decides

The release passes the gate. It does not stop costing the shift what it costs:
released **scheduled** work is added to the running ratio before the round
decides how much more maintenance to pull forward, so a supervisor's choice
changes *which* PM work this shift does rather than *how much*.

Two details, both of which would be silent if wrong. Released **condition and
manual** work is not added, because queued work of those origins is already in
`load_ratio` (ADR-045 §2) and counting it again would spend the same hour twice -
the shift would top up one job fewer than it has room for, every round, with
every number still adding up. And the addition happens **up front** rather than
as the ranked loop reaches each release: added in rank order, a release would
displace an automatic top-up when it happened to rank high and pile on top of it
when it happened to rank low, so the boundary a supervisor is shown would mean
two different things depending on how old their ticket was.

### 4. Releasing is refused where it could not have an effect

Three refusals, all 409:

- the gate is not holding that order - it was released by the round itself, or
  nobody has crewed it, which is a different problem with a different sentence;
- it has already been released, so a second record would say the same thing
  twice and the first one names who decided;
- the round has **no capacity** at all: no shift covers this moment, or nobody
  is rostered (ADR-045 §3). Everything is held there and the gate is not what is
  holding it. Recording a release would put a decision in the log that could not
  have an effect, and the honest answer is the sentence the round already wrote.

Releasing still does not conjure a technician. A released order nobody can crew
comes back unassigned with the same sentence as everybody else's.

### 5. Who may do which

A disagreement may be recorded by anybody who may be shown a ranking. Narrowing
it to the person holding the ticket would record only the objections that are
convenient, and the record is the entire value of the button.

A release is the supervisor's, per ADR-024's table and ADR-011's sentence: the
gate reports to the shift lead, and taking work out of its hands is the shift
lead's decision to defend. Checked at the endpoint and logged either way, like
every other authority in this system (invariant 6).

## Reasons

The alternative for the disagreement was to let it re-rank, which is what most
systems do and what makes them stop being schedulers. The alternative for the
release was to let `dispatch()` read the override table, which would have cost
the replayability every measurement in the report depends on.

Recording the band and ratio on the row is the same argument as
`playbook_snapshot` and as the facts a work order carries for the scheduler
(ADR-041): the context is copied to where it will be read, because the thing it
came from is deliberately not kept.

## Consequences

- The report can say how often the gate was overruled and by whom, which is a
  measurement of the gate rather than an opinion about it. Section 1 is what
  makes that number mean something: nothing else moves when the button is
  pressed.
- A release survives the shift it was made on. If that ever proves wrong, the
  fix is a new record with an expiry that has a source behind it, not a constant
  chosen here.
- `Queued` now carries something that is not on the work order. It is the second
  thing the round is told rather than reads, after the roster, and the two are
  read by the same half of the split (`service.py`).
- The overrides table is the input a later slice needs to ask whether the load
  boundaries are set where the plant wants them. This record does not answer
  that question; it makes it answerable.

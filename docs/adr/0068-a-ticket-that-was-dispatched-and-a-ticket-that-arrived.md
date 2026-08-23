# ADR-068: A ticket that was dispatched and a ticket that arrived are two facts

## Context

ADR-012 answers the riskiest open question in this project - whether the plant
already has a CMMS - by refusing to answer it. Tickets leave through an
interface, `OwnSystemSink` first, and the scheduler never learns what is on the
other side.

Until this slice that was a sentence in a record. `src/pdm/sinks/` held a module
docstring and no code, while `.importlinter` already named it in three
contracts. A released ticket existed only as a row the web app happened to read,
so nothing anywhere could fail if layer 3 started knowing where tickets go.

Building the port raises a question ADR-012 did not have to answer, because with
one destination inside our own database it never came up: **what happens when
the destination does not take the ticket.** That is not a hypothetical the day
the destination is somebody else's system - it is the ordinary case, several
times a week.

## Decision

### 1. Delivery is at-least-once, with the state stored

`ticket_delivery`, one row per work order, keyed by `work_order_ref`. A round
queues a row for each placement it wrote, in the same transaction as the
placement; a later step works through what is outstanding and records what
happened - `delivered` with the destination's own identifier, or `failed` with
what it said.

The alternative was fire-and-forget: call the sink, log the result, keep
nothing. It is cheaper and it is wrong in one specific way - **an undeliverable
ticket becomes indistinguishable from a delivered one**, and the person who
finds out is the technician who was never sent the job. Every other part of this
system is built so that the failure is visible before somebody at a machine
discovers it; layer 4 is the last place to make an exception.

At-least-once rather than exactly-once because exactly-once across two systems
is not available. `TicketSink.deliver` is documented as safe to call again, and
a destination that cannot deduplicate will one day see the same ticket twice.
That is the honest trade: a duplicate ticket is an annoyance, a missing ticket is
a machine nobody was sent to.

### 2. A refused delivery does not un-place the work

The order keeps its assignees, its score and its reason. A CMMS being down is a
fact about the CMMS, and taking the job back from a technician who can already
see it on their own screen would turn somebody else's outage into our own.

The direction that does hold is the other one: the delivery row is written in the
round's transaction, so a round that rolls back takes its queued deliveries with
it. There can be no ticket placed with nothing knowing it has to go out - the
same argument ADR-017 makes for putting the job queue in PostgreSQL.

### 3. Only `DeliveryFailed` is a refusal. Everything else is a defect

An adapter says "the destination would not take this" by raising
`DeliveryFailed`, which is recorded and retried. Any other exception propagates,
the round's transaction rolls back, and the job queue retries the whole thing.

An adapter that returned a status instead would let a forgotten check report
success, which is the failure mode that produces a silent hole rather than a
loud one.

### 4. There is no attempt cap, and `destination` is recorded rather than used

**No cap.** A cap means the system silently gives up on a ticket somebody is
waiting for, and choosing the number would mean choosing how many failures are
acceptable before a machine goes unattended. Instead `attempts` climbs and the
row stays outstanding, which is what makes a stuck destination visible to
whoever looks. What is capped is the *batch* - fifty per round, and this record
is its source: enough that a night's backlog drains in a few rounds, few enough
that one round does not hold its transaction open across hundreds of calls to
somebody else's system while the next one waits.

**`destination` is recorded, not used to select.** An order delivered to one
destination is not undelivered by somebody changing the configured sink in
`policy.yaml` (slice 12.2). The record says where it actually went, which is the
only thing that can answer that question afterwards.

### 5. `OwnSystemSink` is thin, and that is the point

Our own system's ticket is already in the table the technician's screen reads, so
the receipt is the work order's own ref and delivery cannot fail. The adapter is
ten lines.

That is not evidence that the port is over-built. What the slice builds is the
record and the retry, and those cannot be added in the week the CMMS answer
arrives - that is the week they will be skipped. ADR-012's argument is that the
outbound layer must be cheap to change; this is what "cheap" costs.

## Consequences

- **`pdm.dispatch` and `pdm.work` may not import `pdm.sinks` at all**, stated as
  a new import contract. Not "no concrete sink": importing the port would
  already be layer 3 knowing that a destination exists, and the failure worth
  preventing - a scheduler that starts ranking by whether a ticket was
  delivered - needs only the port. This is statable absolutely because delivery
  is a step the composition root takes after a round.
- One destination is still one destination, so "swappable" remains a claim.
  Slice 12.2 is what tests it.
- Nothing yet shows a stuck delivery to a person. The row is there and the API is
  not; the overview screen is where it would belong (ADR-063), and this record
  is the reason it will have something to show.

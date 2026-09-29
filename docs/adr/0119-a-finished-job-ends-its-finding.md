# ADR-119: A finished job ends its Finding

Written on 2026-09-30, from an acceptance walk on a fresh stack: after a
rehearsal, a machine had an open Finding and no live work order, and the rule
behind it could fire as often as it liked without a new ticket.

## Context

ADR-023 gives a Finding a lifecycle (open, acknowledged, resolved, expired,
superseded) and makes it the suppression key: while a Finding is open for a
(machine, rule), a new firing is a repeat of it. Expiry (predictions) and
supersession (a detection overtaking a prediction) were built. Resolution was
built as a function - `Triggers.resolve` - and nothing called it. ADR-044 §6 even
describes "a technician resolves the Finding", but no screen, endpoint or worker
does.

So a detected Finding outlived its job for ever. The technician closed the job;
the Finding stayed open; the fault came back a week later; the rule fired, was
counted as a repeat, and no ticket was issued. Suppression meant to stop an
alarm flood (ADR-023) had become a machine that could never be ticketed again
for that rule.

## Decision

1. Each tick of the trigger loop, before it observes the new batch, resolves
   every open or acknowledged Finding that has had at least one ticket and has
   none open any more (queued, proposed, assigned, in progress, handed over).
   The cooldown starts from that moment.
2. A cancelled ticket counts as finished. Cancelling says the job will not be
   done, not that the condition cannot come back; if it persists, a new Finding
   and a new ticket follow after the cooldown.
3. A Finding that never had a ticket is left open. That is a Finding nobody
   could price, already reported as `unpriced` (ADR-044); resolving it would hide
   the gap.
4. It runs in the runtime worker, which already speaks to both layers, with two
   reads and no join across their tables (ADR-030). Layer 2 learns nothing about
   Findings it did not already carry.

## Consequences

- A fault that returns after a repair is ticketed again, once, after the
  thirty-minute cooldown - which also keeps a sensor that is still hot right
  after the close from raising a second ticket at once.
- A prediction whose job was done before its ETA is now resolved rather than
  left to expire, so ADR-020's accuracy loop no longer counts an early repair as
  a prediction that failed to come true.
- The orphaned Findings already in a database are resolved on the first tick
  after this is deployed.

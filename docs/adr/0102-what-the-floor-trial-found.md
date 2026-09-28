# ADR-102: What the floor audit found, and an empty snapshot filled once

Written on 2026-09-28, from an end-to-end audit of the live stack that played
every role through the five requirements.

## The one that changes an invariant

**An order issued before any playbook existed never got one.** The engineer
approved SYM-014, the shift lead confirmed the waiting order, and the
technician was told "no approved steps exist for this symptom", which was false.
Nothing would ever correct it: the Finding stays open, so no new order is issued.
Invariant 2 froze the snapshot at issue, including an empty one.

Invariant 2 exists so that a job proves what it instructed. An order nobody has
started has instructed nothing yet. So migration 0015 lets the database accept
exactly one change to a snapshot: **from no steps to steps, while the order has
no work segment, with an approver and an approval time.** Every other change is
refused as before. A snapshot that holds steps is never rewritten, and a job
somebody has started is never touched. Approving a playbook now gives it, in one
statement, to the queued, proposed or assigned orders of its symptom and model
that are waiting with none. The estimate, skill and crew size come with it, so
the load figure stops reading the fallback.

## The rest

- The ticket carries the manual's title and edition per step, and the tools the
  approved playbook lists (read from the served playbook; the steps stay the
  snapshot).
- The shift lead's board lists proposals by priority rather than by age, and
  shows the work the gate admitted that has nobody free, which on a heavy shift
  is where an urgent job waits.
- A forecast overtaken by the crossing it predicted says so on the job card.
  The reason itself is still written once (ADR-005).
- A second tap on "start" returns to the job with the API's sentence instead of
  a crash page. A refused approval keeps the engineer's Thai renderings. Draft
  reasons, outcomes and board refusals are Thai. Printing from a dark-mode phone
  prints black on white.

## Not done

- An urgent job assigned to a technician who is mid-job waits behind it, and
  nothing alerts anybody. That is a dispatch policy question.
- The line overview still shows station and component codes.
- `/loops` is an engineer's screen and is still English prose.

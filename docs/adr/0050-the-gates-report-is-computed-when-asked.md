# ADR-050: The gate's report is computed when asked, not stored

## Context

ADR-011 split scheduling into a gate and a score so that the gate could be
explained in one sentence: "this shift is at 92%, four non-urgent jobs are being
held". ADR-045 §8 made the round produce that sentence with the decision, and
then §"Consequences" said plainly that nothing is persisted - a held order is a
queued order that was not admitted this round, there is no new status and no new
column, and "held" is not something anybody can query historically without
recording the rounds themselves, "which is a decision for whoever needs that
history".

Slice 6.3 is whoever needs it. A shift lead has no way to see what the gate held
back, and a supervisor whose work does not appear cannot tell a system that is
holding it from a system that lost it. That is principle 3 - a system that
cannot say why gets overruled and then abandoned - arriving from the direction
nobody planned for, because ADR-005 was written about the ticket that exists and
this is about the ticket that did not appear.

Two ways to answer it:

**Record every round.** A row per round and a row per held order, 288 rounds a
day for ever, and a retention policy nobody has decided. It answers "why was
WO-123 not released at 14:05" - a question about the past that nothing else in
the system can currently answer either.

**Compute the answer when somebody asks.** `dispatch()` is a pure function of
the queue, the roster and the moment (ADR-045 §6), so the gate's report at any
instant is derivable from what is in the tables now.

## Decision

**The report is computed when asked, from the same `dispatch()` the rounds use.**
The read path calls `DispatchRounds.decide()`, which loads the world and returns
the round without writing any of it.

Three things follow, and the third is the one that decides it:

1. **No table, no retention policy, no growth.** Nothing accumulates, so nothing
   has to be pruned, and there is no second schema to migrate when the score
   changes.
2. **The supervisor and the scheduler cannot disagree.** One implementation of
   the gate produces both the decision and the explanation. A stored report
   would be a copy, and a copy of a decision is a thing that can drift from it -
   quietly, because both would look plausible.
3. **The question is about now.** "What is being held" is asked by somebody
   looking at a queue in front of them, and the answer that was true five
   minutes ago is the wrong one. A recorded round would answer a question nobody
   at the plant is asking.

**What this gives up is stated rather than hidden.** There is no answer to "why
was this held at 14:05", and there will not be one until rounds are recorded.
The response carries the moment it was computed at, so nobody can mistake it for
the last round that ran - the two differ by up to one cadence, and a report that
did not say so would be read as history.

## Reasons

**A held order is not a state, it is the absence of one.** Every other thing the
system persists is something that happened: an order was issued, a Finding was
raised, a playbook was approved. "Held" is what did not happen this round, and
it stops being true the moment the shift's load changes. Writing it down would
turn a fact about now into a record that has to be kept correct.

**Recomputing is cheap and the cost is bounded by the thing being reported.**
The whole open queue is what `load_ratio` sums over anyway (design.md 13.2), so
answering this question costs one round's arithmetic over a queue that is short
enough for a supervisor to be reading about.

**The history question is real and this does not answer it.** When somebody
needs "why did this wait all afternoon", the answer is to record rounds, and
this record is what they should argue with. It is deferred because nobody has
asked yet, not because it would be wrong.

## Consequences

- `DispatchRounds` grows `decide()`, which the writing path also uses. The read
  path and the round therefore cannot diverge without a test failing in both.
- The API never writes a placement. Rounds run in `worker-runtime`, which stays
  the only process that assigns anybody to anything (ADR-026).
- A ticket's own `priority_reason` is *not* recomputed on read: it is the
  sentence the person was actually given when the work was released, and
  re-deriving it would show them an explanation of a queue that has changed.
  The two read paths are asymmetric on purpose, and for the same reason - both
  answer the question the reader is actually asking.
- If rounds are recorded later, this record is superseded in part rather than
  replaced: the live report stays the answer to "what is held now".

# ADR-022: Every self-improvement loop proposes; it does not change

## Context

The system has to improve over time, but ADR-003 forbids the LLM from working at
runtime and ADR-004 defers supervised models, so nothing in it "learns" in the
usual sense. Meanwhile the system already captures feedback in several places -
actual durations, technicians' objections, symptoms with no playbook, ETA
accuracy - with nothing consuming any of it systematically.

## Decision

Define seven loops, all with the same shape: **compute a proposal with its
evidence and put it in a queue for a person to approve. Never write to
configuration directly.**

The single exception is the duration-estimate loop, which may adjust
automatically within a bound of plus or minus twenty percent per cycle, because
an estimate is not an instruction a technician follows: getting it wrong skews a
queue rather than hurting somebody.

## Reasons

1. **The same shape as ADR-003.** This system tells people to go and touch
   machinery. A system that adjusts itself quietly means that one day its
   behaviour changes with nobody knowing why and nobody accountable.
2. **The two kinds of error do not cost the same.** Loosening a rule threshold to
   reduce false alarms always increases misses, and misses are far more
   expensive. A loop must therefore show both effects together, and must never
   propose loosening a threshold tied to safety.
3. **The best signal is the one nobody has to be asked for.** A technician
   opening the manual repeatedly at the same step says that step is
   under-written, without the technician having to say anything - unlike a button
   that most people never press.
4. **An engineer's ordinary judgements build a gold set for free**, which makes
   the publication requirement for reproducible retrieval metrics achievable in
   one term with nobody labelling anything extra.

## Consequences

- **The constraint that dispatch must be a pure function changes status** from a
  testing convenience to a precondition of the scheduler-weights loop, because
  replaying past events under different weights is impossible if dispatch queries
  the database internally.
- The technician's close-out screen needs a **"no problem found"** outcome (the
  only false-alarm signal the system will ever get) and chips separating blocked
  time from repair time. Without both, two of the loops cannot function.
- Guard against the closed loop oscillating (estimate to load ratio to which work
  is dispatched to actual duration) by capping movement per cycle and adjusting
  weekly rather than per work order.
- **Every loop measures at the level of a rule, a playbook or a policy - never an
  individual person.**
- In one term only three loops plus the simulator mechanism can genuinely close.
  The rest ship as mechanisms awaiting data, and the report must say so rather
  than claim the system already improves itself.

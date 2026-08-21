# ADR-049: Three things ADR-045 left ambiguous

## Context

ADR-045 settled the gate, the score and the round. Reading it against the code
that implements it turns up three places where the record and the behaviour do
not obviously agree. None is a defect on its own; all three are the kind that is
invisible until somebody reads one against the other, and the report is written
from the records rather than from the code.

**The skill-match term.** ADR-045 §1's table defines it as 1 where "somebody
**free** holds it". `_skill_match` checks everybody rostered and active,
regardless of whether any of them has a minute left. The two differ exactly when
the only holder of a skill is booked solid, which is the case the term exists to
notice.

**The sentence threshold.** `_reason()` keeps the contributions above `0.05`
when it builds the sentence a technician reads. `policy.yaml` says a constant
needs a manual, a measurement or a recorded decision behind it, and this has
none of the three.

**Local times that do not exist.** ADR-045 §7 gave the plant a timezone and said
shift boundaries are local wall-clock times. It did not say what a boundary
means when the local time it names is skipped or repeated by a daylight-saving
transition.

## Decision

### 1. The skill-match term is about the shift's competence, not a technician's free minutes

The code is right and the word "free" in ADR-045 §1 is loose. The term answers
"does this shift have anybody who can do this job", and it is 1 when somebody
rostered and active holds the skill, whether or not they have time left today.

Two reasons, and the second is the one that matters:

**Availability is already answered, twice.** `_assign` will not place an order on
somebody without the minutes for it, and an admitted order nobody can take comes
back as unassigned with the reason. Folding the same fact into the score would
count it in two places, and a supervisor comparing the ranking against the
reason would be reading one input twice.

**A score that moved with people's free minutes would reorder the queue as work
finished.** Every completed job frees somebody, which would change the
skill-match term of everything they could do, which would re-rank the queue
under a technician already walking to a machine. design.md 6.2 refuses that for
accepted work, and ADR-045 §4 built the round around it; a term that quietly
reintroduced the churn one level down would undo it.

### 2. `_reason`'s threshold is presentational, and this is its source

`0.05` decides which clauses appear in a sentence. It cannot change a score, an
ordering, an admission or an assignment - every term is in the weighted sum
whatever the threshold does, and the threshold is read after the sum. It is a
readability choice: a sentence listing five terms, three of them near zero,
reads as a formula rather than as a reason.

It stays in the code rather than moving to `policy.yaml`, because putting it
beside the weights would say it is policy, and a supervisor tuning it would
change nothing about what the system does. **This record is the third kind of
provenance `policy.yaml` asks for.**

### 3. A shift is its wall-clock hours, and a skipped local hour takes the offset after the change

A shift that runs 22:00 to 06:00 runs from when people arrive to when they
leave. Across a spring-forward that is seven real hours and across an autumn
fall-back it is nine, and both are what the plant actually worked - so the
window `shift_at` returns is correct in a daylight-saving zone, not merely
tolerable. Nothing needs to change.

What was undefined is a boundary naming a local time that a transition removes.
`06:00` exists every day of the year in every zone this project will plausibly
meet; `02:30` does not, twice a year, in about half of them. Such a boundary
resolves to the offset in force **after** the change - the hour the plant would
actually be standing there - which is what `datetime.combine` with a `ZoneInfo`
already produces. Recorded rather than implemented, because the behaviour is
already right and an implementation would only be a chance to make it wrong.

## Reasons

The three share a shape: in each, the code does the sensible thing and the
record either says something slightly different or says nothing. Left alone,
each would be found by whoever writes the report, at the point where they can
least afford to discover that a record and its implementation disagree.

Fixing the record rather than the code, twice out of three, is deliberate.
ADR-045's decisions are sound; what is wrong is one word and one silence.

## Consequences

- ADR-045 §1's table should be read with this record beside it. That is what
  append-only costs and what the "superseded in part by" column is for.
- The skill-match term stays computable without a roster's remaining minutes,
  which keeps `_rank` a function of the queue and the shift rather than of the
  round's progress.
- If a scenario ever wants "the only electrician is booked" to lower a job's
  rank, that is a new term rather than a change to this one, and it would have
  to answer the churn argument in section 1.
- A plant in a daylight-saving zone is supported. The only shift boundary that
  needs care is one inside the skipped hour, and section 3 says what it means.

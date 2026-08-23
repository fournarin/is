# ADR-075: What the confirmation record may be read to say, and what it may not

Extends [ADR-071](0071-a-round-proposes-and-a-person-decides.md), which wrote
`dispatch_proposal` and, in section 8, said what the table was for without
saying what a reading of it looks like. It does not revisit any decision in that
record: the mode, the states, the sweep and the refusal to write a threshold all
stand exactly as written.

## Context

ADR-071 §8 answers the advisor's condition for ever turning confirmation off -
"ต้องดู performance ไปก่อน" - with a table, and then stops: **no threshold goes
into `policy.yaml`**, because a number deciding when a plant may stop reviewing
its own work orders is not a value this project may invent before it has
measured anything.

What the record has lacked since is a reader. Nothing in the system has ever
opened `dispatch_proposal`, and a table nobody reports from is a table somebody
eventually drops - the same argument ADR-059 made for the override record, one
layer up. It is also, on ADR-071's own reasoning, the most publishable thing in
layer 3: how far a shift lead agrees with an optimiser is a result, it can be
collected on ADR-014's technician trial, and it needs no plant data at all.

Four questions had to be settled before any arithmetic could be written, and
three of them are ways this report can mislead rather than inform.

1. **What is the denominator?** Agreement is a fraction, and there are two
   plausible bottoms to it - everything proposed, or everything a person
   answered - which say different things about the same shift.
2. **Is an expiry a slow decision?** The table's `decided_at` is populated on an
   expired row, and it is the sweep's timestamp.
3. **What is the unit of the finding?** A count of rejections, or the rejections
   themselves.
4. **What may this report conclude?** ADR-071 §8 refuses a threshold. A report
   is a good place to smuggle one back in as a recommendation.

## Decision

### 1. The three endings stay three endings, and expiry is reported in full

`confirmed`, `rejected` and `expired` are counted apart and never collapsed into
"not confirmed", because they are evidence about different things. A rejection
is an argument about the score - the scheduler proposed something a person would
not send anybody to do. An expiry is an argument about the confirmation step
itself, and ADR-071 §8 already says it is as strong a case for `automatic` as
agreement is: a step nobody reaches is a queue with a person-shaped hole in it.

So expiries get the treatment rejections get: **every row, listed, with the
round it was decided against**, not a number in a corner. The issue behind this
slice asked for expiry to be reported as loudly as rejection, and a count beside
a list is not as loud as a list.

`pending` is counted too. Without it a report written in the middle of a shift
describes a shift lead who has answered everything they were asked.

### 2. Agreement is measured over what a person answered; expiry over what ended

Two denominators, both on the record rather than left to whoever renders it,
because picking the wrong one is the whole way this report can mislead:

- `confirmed_share` = confirmed / (confirmed + rejected). An expiry is nobody's
  opinion about the placement, and putting it under the line would report
  disagreement that was never expressed.
- `expired_share` = expired / (confirmed + rejected + expired). Here the
  expiries belong under the line, because the question is what share of the
  decisions that reached an ending reached it without a person - and the set
  somebody could have answered in time is every settled proposal.

Both are **absent rather than zero** when there is nothing to divide by.
"Nobody confirmed anything" and "nothing has been answered yet" are opposite
findings, and only one of them is evidence (principle 5).

### 3. An expiry is not a decision time

`decision_time` - median, mean and longest - covers confirmations and rejections
only. An expired row's `decided_at` is always `proposed_at +
proposal_expires_minutes`, so including it would drag every figure towards a
value in `policy.yaml` and report a setting back as a measurement. It would also
make the shift lead look slowest at exactly the moments nobody was there at all,
which is the opposite of what the figure is read for.

Rejections are timed alongside confirmations. Both are a person reading a screen
and pressing something; timing only the agreements would measure how long
agreeing takes, which is a different question.

### 4. Per shift and per band, with the unrecorded rows kept

The same reading is produced for each shift and each band. "The shift lead
disagrees on heavy shifts" and "the shift lead disagrees" are different
findings, and only the first can be acted on - and ADR-011's two bands are two
different jobs to be a shift lead in.

A proposal that recorded no band - a round with no capacity to compute a ratio
from (ADR-045 §3) - is reported under an empty key rather than dropped, so the
segments always add up to the total. Segments that quietly disagreed with the
overall figure would leave a reader unable to tell which of the two was wrong.

### 5. The report proposes nothing, and says so on every copy

There is no recommended threshold, no "ready to switch" verdict, and no field a
screen could render as one. This slice is the measuring that ADR-071 §8 makes a
precondition for the deciding; producing both here would make the precondition
meaningless.

Every report carries what the record structurally cannot say, in the same shape
ADR-073 §6 gave the threshold loop and for the same reason - a caveat that lives
only in a document is absent at the moment somebody is looking at a number:

- **it says nothing about whether either party was right.** Nothing here records
  what a confirmed placement went on to cost, and a supervisor who confirms
  everything to clear a screen is indistinguishable from one who read each
  proposal.
- **it is silent about the mode it would be used to argue for.** In `automatic`
  no proposal row is written (ADR-071 §8), so this record cannot say what would
  have happened without the step it measures.

### 6. Where it is read, and by whom

`GET /dispatch/confirmations`, computed when asked and writing nothing, beside
the gate's report that already works that way (ADR-050). Both bounds of the
window are optional and neither has a default: how much history is enough to
argue from is exactly the judgement ADR-071 §8 keeps for the advisor and the
maintenance department, and a default here would make it silently. The window is
bounded on `proposed_at`, because the question is what a shift lead was asked
during a stretch of time - a proposal answered after the window closed still
belongs to the shift it was asked about.

Read by the supervisor and the engineer, and not by the technician. Everybody
who may be shown a ranking may read the proposals (ADR-005), but this is a
report *about* the shift lead rather than *for* them, and the people who would
act on it are the shift lead themselves and the engineer who would take it to the
maintenance department with the switch in hand.

It is deliberately not on `/overview`. That screen is what the shift lead has to
act on now - what the gate is holding, and what it is asking about - and a
scoreboard of their own agreement rate sitting beside the queue changes what
pressing confirm feels like. `docs/results/confirmations.md` is where the answer
gets written down, with the other measurements.

### 7. The reading is a pure function of the rows

`agreement()` takes proposals and returns a report; the SQL that fetches them is
in `dispatch/repo.py` (invariant 10, ADR-030). So every case - three expiries and
no answers, a band that was never recorded, an empty window - is tested against
proposals written out by hand rather than against a world driven into that shape
through the scheduler.

## Reasons

1. **A table nobody reports from gets dropped.** `dispatch_proposal` costs a
   write on every round and a person's press on every ticket. The only thing
   that makes that cost defensible is somebody reading it back, and ADR-071 §8
   named what they would read without building it.

2. **The refusals are the content.** Three of the five decisions above are about
   what the report must not do - not average the sweep into a person's decision
   time, not divide by an ending nobody chose, not conclude. Those are the ways
   a report like this ends up quoted in a defence as evidence for something it
   never measured.

3. **Expiry is the finding nobody asks for.** The question this record exists to
   answer is "should we turn this off yet", and the answer that would come from
   agreement figures is a comfortable one either way. The uncomfortable answer -
   that a large share of proposals were never answered at all - is the one that
   would change what the plant does, so it is reported in full rather than
   summarised.

4. **It is measurable on the trial, not on the plant.** ADR-014's technician
   trial produces exactly the rows this reads, which puts a real result in the
   report without a single sensor reading (principle 4).

## Consequences

- `docs/results/confirmations.md` exists from this slice with **no figures in
  it**, and says so plainly: the method, the endpoint, and the sentence that no
  trial has been run yet. It is the file the written report quotes once one has,
  and stating the absence is the honest form of an unmeasured result
  (principle 5).
- ADR-014's technician trial gains a third thing to collect on the day, beside
  whether a technician can work from the ticket and whether a shift lead can
  decide from the proposal: what they decided, and how long it took them.
- Nothing about the switch changes. `dispatch.confirmation` stays `supervisor`,
  and this record is what would one day be put in front of somebody arguing that
  it should not be.
- The report is one more reason `dispatch_proposal` may not be pruned. A row
  answered six weeks ago is the only evidence that the shift lead agreed with
  the scheduler six weeks ago.

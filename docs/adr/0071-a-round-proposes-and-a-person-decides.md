# ADR-071: A round proposes, and a person decides

Revisits [ADR-011](0011-load-ratio-switches-dispatch-behaviour.md), which made
layer 3 a gate and a score and let the result go straight to a technician;
[ADR-068](0068-a-ticket-that-was-dispatched-and-a-ticket-that-arrived.md), which
queues a delivery in the round's own transaction; and
[ADR-061](0061-what-the-technicians-screen-reads-and-from-where.md), which said
where the technician's screen reads each figure from.

## Context

The brief said the system dispatches tickets automatically, and every record so
far has been written on that reading. On 2026-08-23 the advisor was asked who
presses the button, and answered: **at first a person should, and later, once
there is something to judge it by, approval could be made automatic.**

That is not a smaller version of what is built. It is a different flow with a
person standing in the middle of it, and three things in this repository assume
the person is not there.

**A round's decision is final the moment it is written.** `repo.place` sets
`status = 'assigned'` and writes the assignees, and from that instant the job is
a technician's. There is no state for a decision that has been taken and not yet
approved, and `WorkOrderStatus`'s own docstring has said since it was written
that the set was derived rather than quoted and was "worth confirming before
layer 3 is built on it".

**The delivery goes out with the round.** ADR-068 queues a `ticket_delivery`
row in the same transaction as the placement, on the argument that a ticket
cannot be placed without something knowing it has to go out. With a person in
the middle, that argument now sends tickets to a CMMS before anybody has
approved them.

**And building the step found a defect that was already there.** The
technician's screen calls `myWork`, which filters `round.placed` from
`GET /dispatch/round`; that endpoint computes a round when asked (ADR-050), and
`dispatch()` considers only orders whose status is `queued`. So an order stops
appearing in `placed` the moment a round writes it. In the rehearsal this is
invisible, because `scripts/rehearse.py` scales `worker-runtime` to zero while
the checks run - deliberately, so that rounds do not place work in the middle of
a check asserting on its own seeded orders - and every screen check therefore
sees a queue no round has ever touched. With the worker running, which is the
shipped configuration, a technician's job disappears from their screen at the
exact moment the system decides to give it to them:

```
before the round writes: placed=['WO-006061']  → the screen shows it
the round wrote:         placed=['WO-006061']  → status becomes 'assigned'
after the round writes:  placed=[]             → the screen shows nothing
```

It has to be fixed here rather than filed, because in the mode the advisor asked
for a round places nothing at all until a supervisor presses confirm, and a
screen reading from `placed` would then be empty always rather than sometimes.

## Decision

### 1. A round proposes. A person confirms. `proposed` is the state in between

`WorkOrderStatus` gains `proposed`: the round has decided who should do this
job and nobody has agreed to it yet. Confirming moves it to `assigned`, which is
the state everything downstream already understands, so no screen, transition or
query beyond the ones named here learns that confirmation exists.

The alternative was to leave the status alone and record approval beside it.
Rejected because `status` is what every other part of the system asks about -
`open_orders`, the capacity calculation, the technician's transitions, the
partial index - and a job whose status says a technician has it while another
table says nobody has approved it is a disagreement that will be resolved
differently in each of those places.

### 2. Which mode the plant runs in is one key in `policy.yaml`, and both modes are one path

```yaml
dispatch:
  confirmation: supervisor    # or: automatic
```

`supervisor` is the default, because that is what was asked for and because it
is the mode that cannot lose work: a plant that meant to review and got
automatic dispatch finds out from a technician who was sent somewhere nobody
approved.

**Automatic is not a second code path.** The round decides identically, scores
identically and crews identically in both; the only difference is the status it
writes and whether a proposal is recorded. A fork here would mean the mode the
plant eventually runs in is the one this project tested least, and the switch
was asked for precisely so that it can be thrown later without a rewrite.

### 3. A proposal holds the capacity it was decided against, and no round touches it

`proposed` joins `TAKEN` in `dispatch/domain.py`: its `estimated_minutes ×
required_technicians` count as committed, they are subtracted from its
assignees' remaining minutes, and `dispatch()` will not re-place it.

The alternative - leave a proposal in the queue to be re-ranked every round
until somebody confirms it - was rejected for a reason the load gate makes
sharp. A proposal that does not consume capacity is a shift that reads emptier
than it is, and ADR-011's gate responds to an empty-looking shift by releasing
*more* work; four unconfirmed proposals would each be proposed again to somebody
who is already spoken for, and the supervisor's screen would fill with
duplicates of the same decision.

### 4. A rejection puts the order back in the queue immediately, with a reason

Not a hold, not a cooling period, not a mark that stops it being proposed again.
The order returns to `queued` and the next round ranks it against what is true
then.

A supervisor rejecting a proposal is usually saying "not this person" or "not
now", and both are facts about a world that changes every five minutes. If the
round proposes the same pairing again, that is information rather than a bug: it
means nothing has changed, and a second rejection with a second reason is
evidence about the score that Loop 6 can replay. A cooling window would suppress
exactly that evidence, and its length would be a constant with no measurement
behind it - which this project refuses everywhere else in `policy.yaml`.

The reason is required, for ADR-059's reason: a rejection with no reason is
indistinguishable from a misclick when somebody reads it back.

### 5. Whoever makes a ticket real is what queues its delivery

ADR-068's rule was "the delivery row is written in the transaction that placed
the work". The rule becomes: **the delivery row is written in the transaction
that made the ticket somebody's job.**

In `automatic` that is the round, unchanged. In `supervisor` it is the
confirmation, in the request's transaction, and `RoundReport` separates what it
placed from what it proposed so that the worker hands layer 4 only the first.
ADR-068's guarantee holds exactly as stated - there is no committed state in
which a technician has been given a job and nothing knows it has to go out -
and it now holds for the step that actually gives it to them.

The composition layer is what does this, not layer 3: `.importlinter` bans
`pdm.dispatch` from importing `pdm.sinks` at all, and the confirmation endpoint
lives in `pdm.api.dispatch`, which is the same seam ADR-061 §1 already argued
for reading a Finding.

### 6. A proposal nobody answers goes back into the queue

`dispatch.proposal_expires_minutes`, swept at the start of each round, in the
round's transaction, before it decides. An expired proposal returns its order to
`queued` and is recorded as `expired`.

Without this the failure is quiet and total: a supervisor who goes home leaves
every proposal holding its technician's minutes until somebody notices, and the
gate - reading a shift that is committed to work nobody agreed to - holds back
everything behind it. This is ADR-023's argument about Findings, one layer up.
The sweep is in the round rather than in a second job because the round is
already the thing that runs on a cadence and already owns a transaction; a
second timer would be a second place that decides when a decision has gone
stale.

The value is a recorded decision, not a measurement: longer than a round, so a
proposal is never swept before a supervisor has plausibly seen it, and much
shorter than a shift, so a decision is never confirmed against a world eight
hours old. Thirty minutes is six rounds and a sixteenth of a shift.

### 7. The technician's screen reads the orders, not a recomputed round

`GET /work-orders/mine` returns the caller's own live work - `assigned`,
`in_progress`, `handed_over` - ordered by the `priority_score` layer 3 wrote
onto each order when it placed it. The web layer's `myWork` reads that instead
of filtering `round.placed`.

Two things follow, and both are the point:

  * **the ranking is a snapshot, deliberately.** `priority_score` is frozen at
    placement, so the queue does not re-order itself under a technician already
    walking to a machine - which is what design.md 6.2 asks for and what
    re-deriving the round on every page load quietly broke;
  * **`proposed` work is not the technician's**, so it cannot appear here. The
    same query that fixes the disappearing job is the one that keeps unapproved
    work off the screen.

`GET /dispatch/round` keeps doing what ADR-050 built it for - the gate's report,
computed when asked, for the person deciding - and stops being the source of
anybody's job list. Accepting an order that is still `proposed` is refused with
a sentence that names the state, rather than by the order being invisible.

### 8. What the record keeps, and what would justify turning the switch

One row per proposal in `dispatch_proposal`, carrying the assignees, the score
and the sentence the round wrote, plus the band, ratio, shift and date it was
decided against - copied on, because a round is never stored (ADR-050) and six
weeks later there is nothing else to read the decision back against. It settles
as `confirmed`, `rejected` or `expired`, with who decided and when.

That table is the answer to "ต้องดู performance ไปก่อน". What it can say is how
often the supervisor agreed with the scheduler, how often they did not and in
which words, how long a decision took, and how much was never answered at all -
and the last one is as strong an argument for automatic dispatch as the first,
because a confirmation step nobody reaches is a queue with a person-shaped hole
in it.

**No threshold is written into `policy.yaml`.** A number deciding when a plant
may stop reviewing its own work orders is not a value this project may invent
before it has measured anything, and it belongs to the advisor and the
maintenance department with the evidence in front of them.

In `automatic` no proposal row is written, because nothing was asked of
anybody. What the system is judged by then is the record that already exists:
the technician's disagreements (ADR-059) and the outcome of the work.

## Reasons

1. **The person in the middle was in the brief and was read out of it.** "แจก
   ticket อัตโนมัติ" is an instruction about who does the arranging, not about
   who is accountable for it. The advisor's answer says the accountability is
   staged - a person now, a policy later, decided on evidence - and a design
   that could only do one of the two would force the plant to choose between
   trusting it completely on day one and not using it.

2. **The switch is the deliverable, and the measurement is what makes it
   meaningful.** Anyone can add a boolean. What is worth a term is the record
   that lets somebody argue from it: proposal by proposal, what the scheduler
   said, what the shift lead said, and how far apart they were. That is also the
   most publishable thing in layer 3, because agreement between an optimiser and
   the person it is trying to replace is a result, and it needs no plant data to
   collect on a technician trial.

3. **The defect in §7 is the argument for this whole record in miniature.** A
   screen that recomputes what the scheduler *would* decide is showing an
   opinion, not a fact; it happened to agree with the database only while no
   round had run. Work a person has to act on must be read from what was
   written down, and the same sentence covers both halves of this slice: what a
   technician sees, and what a supervisor is asked to approve.

4. **`proposed` is honest about what the system knows.** Every other state in
   this project answers a question a person would ask - is it waiting, does
   somebody have it, is it finished. "Decided but not yet agreed to" is a real
   state of the world in a plant, and it has been one all along; before this
   record it was simply written down as though it were agreement.

## Consequences

- The check that would have caught §7's defect now exists:
  `web/check-the-technicians-screen.py` runs a real round and confirms its
  proposal before asserting on the screen, so it exercises the shipped path
  rather than the one that only holds while `worker-runtime` is stopped.
- `scripts/rehearse.py` still scales the worker to zero for the checks, and the
  reason in its comment is still correct. What changes is that the checks no
  longer *depend* on it being stopped.
- The rehearsal's demo world now needs a supervisor to press confirm before a
  technician has anything, which is the flow the plant will run and one more
  thing the demo can show.
- `dispatch()` is untouched. It has no parameter for the mode, no knowledge of
  proposals, and remains a pure function of its arguments (invariant 10,
  ADR-045 §6) - so the simulator's scenarios and slice 7.3's comparison measure
  exactly what they measured before.
- The load gate's report and the confirmation queue are two different screens
  for the same person, and both are on `/overview`: what the gate is holding
  back, and what it is asking about.
- ADR-014's technician trial gains a second question worth asking on the day:
  not only whether a technician can work from the ticket, but whether the shift
  lead can decide from the proposal without opening anything else.

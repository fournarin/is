# ADR-045: The load gate, the score, and what a round is allowed to move

## Context

ADR-011 split scheduling into a gate and a score, and gave the gate its two
boundaries. ADR-021 gave the downtime term its shape. ADR-025 and design.md 13.2
fixed the unit of `load_ratio` as person-minutes on both sides. `policy.yaml` has
carried five weights since slice 1.2 with a note saying they are starting values,
not measurements.

None of that is enough to compute anything, and the gaps are not small:

**The terms are on incompatible scales.** Severity is a rank of zero to three.
The downtime term is units of production lost, which for a bottleneck with no
buffer is hundreds. Waiting time is minutes and grows without limit. Added
together against weights that are all near 1.0, the score is the downtime term
with rounding noise, and every weight in the report would be a number that
describes nothing. This is the decision that determines whether `w1..w5` mean
anything at all.

**"Pending work in the shift" has two readings and one of them inverts the
behaviour the advisor asked for.** If every open order counts toward
`load_ratio`, then a backlog of PM work makes the shift read full, and the gate
responds by holding back the condition work that actually has to happen -
the opposite of "when it is light, release the secondary work".

**Nothing says what a round may touch.** design.md 6.2 says work a technician has
accepted is not moved, which means a round both reads orders it must not move and
moves orders it has just read.

**And the shift itself is not resolvable.** `plant.yaml` says the morning shift
starts at `06:00` and every timestamp in this system is UTC (ADR-028). Read as
UTC, that shift runs from one in the afternoon in the plant that is meant to be
running it.

## Decision

### 1. Every term is normalised to 0-1 before its weight is applied

Three of the five are naturally bounded and are mapped directly:

| term | 0 | 1 |
|---|---|---|
| severity | `low` | `critical` (rank / 3) |
| skill match | nobody on this shift holds the skill | somebody free holds it (0.5 where the order names no skill) |
| ETA urgency | the crossing is a full horizon away | it is due now |

The two that are unbounded - **downtime cost and waiting time** - are divided by
the largest value in the same round. So the score is **a comparison within one
round and nothing else**: it ranks the queue that exists at this moment, and two
scores from two rounds are not on the same scale.

That is stated rather than hidden, because the alternative is worse. A fixed
divisor for downtime would be a constant with no source (`workflow.md` 4.1), and
one for waiting would have to encode how long a job is allowed to wait, which is
the thing the weight is supposed to express.

**Consequence accepted:** `priority_score` must not be plotted over time or
compared between rounds, and the report must not present it as a magnitude.
What is comparable across rounds is the *ordering* and the individual terms,
which are returned alongside the score.

### 2. Scheduled work is the reserve; it is not demand until it is released

`load_ratio`'s numerator is the person-minutes of work that is **committed**:
every open order except PM work that is still queued.

```
committed = Σ estimated_minutes × required_technicians
            over open orders, excluding queued origin = scheduled
capacity  = Σ available_minutes over this shift's assignments
```

Counting queued PM work as demand makes a shift with a maintenance backlog look
busy, and the gate then holds back the condition work - which is precisely
backwards, and would have been invisible: the numbers all move, they just move
the wrong way. PM work joins the numerator at the moment the gate releases it,
which is what makes "top up to the light boundary" terminate.

### 3. The gate has three bands and releases in score order

```
ratio ≥ heavy_at_or_above   admit severity ≥ high only; hold the rest and say so
light_below ≤ ratio < heavy admit condition and manual work in score order
ratio < light_below         the same, then release scheduled work in score order
                            until the ratio reaches light_below
```

Releasing PM work up to the boundary rather than all of it: a quiet shift given
its entire maintenance backlog at once is a heavy shift one round later, and the
work released last is the work most likely to be abandoned at handover.

**A shift with no capacity is not a division by zero.** No shift covering this
moment, or nobody assigned to it, admits nothing and says which of the two it
was. Treating an empty roster as infinite load would give the right behaviour by
accident; treating it as zero load would release the entire queue to nobody.

### 4. A round places queued work only, and never moves the rest

Orders that are assigned, in progress or handed over are read - they consume
their assignees' capacity and they count in `load_ratio` - and are never
re-ranked, re-assigned or withdrawn. design.md 6.2's argument is that a queue
which reorders itself while a technician walks to the machine is a queue they
stop believing, and stability is worth more than a slightly better answer.

### 5. Assignment is greedy over the ranked list, and a multi-person job is all or nothing

Down the admitted list in score order: the technicians who hold the required
skill (or anybody, where the order names none) and have enough minutes left this
shift, most free capacity first, user id to break the tie. `required_technicians`
people or none at all - half a two-person job is a job that cannot be started,
and it would consume one person's shift to achieve nothing (ADR-025).

An admitted order nobody can take is returned as admitted-and-unassigned with the
reason, rather than dropped or silently held. "Nobody with `electrical` has time
left" is a fact a supervisor can act on within the shift; a ticket that simply
did not appear is not.

### 6. Determinism is a property of the code, not of the run

Every sort names its tie-break - score, then created time, then reference - and
no set or dict iteration order reaches an output. Nothing inside reads a clock:
`now` is an argument. This is invariant 10, and it is a precondition for the
simulator (design.md 7) and for Loop 6 replaying real decisions against
alternative weights.

### 7. The plant has a timezone, and shift boundaries are read in it

`plant.yaml` gains one key, `timezone`, validated at boot against the system's
zoneinfo database. Shift boundaries are local wall-clock times - `06:00` is when
people arrive - and the moment they are compared against is UTC.

Without it, `06:00` in a plant at UTC+7 resolves to the middle of the afternoon,
the night shift's date rolls a day early, and `shift_capacity_minutes` reads the
wrong roster: wrong for exactly one shift in three and right for the others,
which is the failure ADR-028 was written about and the reason it insisted on
timezone-aware timestamps in the first place.

### 8. The explanation is produced with the decision, not on request

Each placed order carries its `priority_reason` and the value of every term that
produced it. design.md 6.3 defers the *counterfactual* explanation - "delaying
this adds twelve minutes of downtime" - because re-solving is expensive; that is
about 3D. Opening the terms of a weighted sum costs nothing, and ADR-005 wants
the answer on the screen where the job is, not behind a button.

The round also carries one sentence for the supervisor: the load, and how many
orders it held. That sentence is the whole reason ADR-011 kept the gate out of
the score.

## Reasons

**Normalising within the round is the only option that adds no constants.** Every
alternative - a fixed scale for downtime, a maximum sensible wait, a saturating
curve - introduces a number nobody can source, and this project has a standing
rule against those. What it costs is cross-round comparability of one field,
which nothing needs and which the record now says not to use.

**The gate is the part the advisor described most concretely**, and it is the
part that has to keep working when everything else is uncertain. It reads two
numbers, both in person-minutes, and produces one sentence.

**Purity is not tidiness here.** Slice 7 compares three policies over hundreds of
scenarios in CI, and Loop 6 replays past decisions against different weights.
Both need this function to be replayable exactly; a single clock read or unsorted
set iteration inside it would make every measurement in the report
irreproducible, and would do it quietly.

## Consequences

- **`work.repo.open_orders` has to return the creation time**, which it does not
  today: the waiting term needs it and the contract deliberately does not carry
  it (the same argument that keeps `work_order_ref` off the contract). The pure
  function takes a small view - reference, order, created time - and the repo
  widens in the slice that wires this up.
- **Technicians and shift assignments have no tables yet.** The function takes
  them as arguments, so this slice needs no migration and no database at all; the
  tables arrive with the tick that calls it.
- **The weights remain unmeasured.** Normalising makes them interpretable, not
  correct. They are still the starting values `policy.yaml` warns about, and the
  simulator is what will move them.
- **A round with one order gives it a downtime term of 1.0**, because it is its
  own maximum. Harmless for ordering, misleading if read as a magnitude - the
  same caveat as section 1, arriving from a different direction.
- **Nothing is persisted.** A held order is a queued order that was not admitted
  this round; there is no new status and no new column, and the next round
  recomputes from scratch. That is what keeps the function replayable, and it
  means "held" is not a thing anybody can query historically without recording
  the rounds themselves - which is a decision for whoever needs that history.

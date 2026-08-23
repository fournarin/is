# ADR-066: What the finished jobs may change, and what stops them

## Context

ADR-006 keeps `estimated_minutes` on the playbook and `actual_minutes` on the
work order apart, and says why: the first is what the scheduler prices a shift
with, the second is what happened, and the gap between them is a feedback loop
that needs no machine learning at all. Slice 11.1 is that loop - the first one in
this system to close.

Four things had to be decided before any arithmetic could be written, and none of
them is a question about statistics.

1. **May it write?** ADR-022 defines seven loops with one shape - propose, never
   change - and then grants this loop, and only this loop, an exception: it may
   adjust automatically within plus or minus twenty percent per cycle, on the
   argument that an estimate is not an instruction a technician follows.
2. **What is the number?** A mean is the obvious choice and the wrong one.
3. **What is not evidence?** A closed order is not automatically a measurement of
   how long a repair takes.
4. **How much evidence is enough?** There is no manual and no measurement to
   appeal to for this, which is exactly the kind of number this project treats as
   a defect when it is invented quietly.

## Decision

### 1. The loop proposes. The exception in ADR-022 is declined

`estimated_minutes` is not changed by anything in this slice. The bound ADR-022
granted - twenty percent per cycle - is kept, as a **cap on the proposal** rather
than as permission to apply it.

ADR-022's argument for the exception is sound about safety and wrong about
accountability. An estimate really is not a torque value; nobody is hurt by one.
But it is the number `load_ratio` is computed from, `load_ratio` decides which
work the gate releases, and the release decision is the one the advisor asked
for by name. A figure that moves on its own is a figure that, in the week
somebody asks why the shift filled up, nobody can explain - and this project is
graded on being able to explain it.

The mechanism is also the cheap half. Applying a proposal is one `UPDATE` and an
approval; deciding whether the evidence is good enough is the part that needs a
person, and it is the part that would be skipped.

### 2. The median of `repair_minutes`, rounded half up

Not the mean, and not `actual_minutes`.

**`repair_minutes`**, because waiting for a part is not repair time (ADR-025).
Fed back, waiting inflates the estimate every cycle: a longer estimate makes the
shift read fuller, the gate holds more back, and the jobs that do run are the
ones that waited longest.

**The median**, because one job started before a shift change and closed the next
morning is eighteen hours to a mean and one observation to a median. With the
observation floor below, a mean would let a single row reprice every job for that
symptom.

**Rounded half up**, because Python rounds halves to even, and a rule that turns
47.5 into 48 and 46.5 into 46 is one nobody can reproduce with a pencil.

### 3. What is not evidence

- **`no_problem_found`.** A false alarm says nothing about how long the repair
  takes. It is excluded from the estimate and **counted separately, per rule and
  per symptom** - it is the only false-alarm signal this system will ever
  receive, and Loop 2 has no other input. It is counted where the outcome lives,
  on the work order, joined to the Finding for the rule that raised it; a work
  order deliberately carries no `rule_id` (ADR-030).
- **An order with no repair time.** Zero minutes is not a fast repair. It is an
  order nobody recorded segments against, or one whose whole length was waiting.
  Counted in, it drags the middle below anything anybody has ever taken.
- **Work no rule raised.** A reported fault that closed `no_problem_found` is
  reported with no rule against it rather than dropped or charged to one.

Both exclusions are reported on the proposal. A count of jobs that carried no
duration is a gap in the close-out screen, and it should be visible as one.

### 4. Two constants, both recorded decisions

In `config/policy.yaml`, never in code:

| | value | provenance |
|---|---|---|
| `min_observations` | 5 | this record |
| `max_change_ratio` | 0.20 | ADR-022, enforced by the config schema |

`min_observations` has no manual and no measurement behind it, and this record is
where it gets its third kind of source. Five is the smallest count that leaves
two observations either side of the median, so one unusual morning cannot *be*
the middle. That is an argument about the statistic and not a measurement of this
plant, and it is deliberately cautious: waiting costs a stale estimate, moving
too early costs a figure every shift is priced with.

`max_change_ratio` may not exceed 0.20, and the schema refuses a larger value at
boot. A bound that lives only in a document is one a later edit to `policy.yaml`
passes straight through.

### 5. Silence is a result

Nothing is proposed when there are fewer usable observations than the floor, and
nothing is proposed when the evidence lands on the value already in the playbook.
A queue item asking somebody to approve no change is how a review queue stops
being read.

### 6. Where it lives, and what it is not

`src/pdm/work/estimates.py`, beside the closed orders it learns from, and pure:
no connection reaches it, so the whole of it is tested against durations written
out by hand. It is on the no-I/O list in `.importlinter` for dispatch's reason -
a version of it that could open a connection could also be a version that writes
the estimate it just proposed.

Nothing is stored and nothing is scheduled. A proposal is computed when asked,
from rows that are already there, on the same argument as ADR-050. **This slice
adds no endpoint, no screen and no cadence**, and until those exist the loop is a
mechanism rather than a loop that turns. ADR-022 asks for weekly rather than
per-order adjustment; that belongs with whatever schedules it.

## Consequences

- **The first feedback loop in this system now has an answer to "what does the
  evidence say".** Nobody can yet act on it from a screen. That is the next
  slice, not this one.
- **A `no_problem_found` count exists for the first time.** Loop 2 - rule
  thresholds - is the consumer, and ADR-022 forbids it from proposing that a
  safety-linked threshold be loosened however large this count grows. Reporting
  the count is not proposing anything.
- **An estimate below three minutes cannot move**, because twenty percent of it
  rounds to nothing. Repairs are tens of minutes and `fallback_minutes` starts at
  twenty-five, so this is a boundary rather than a case; it is written down here
  so that finding it later is recognition rather than discovery.
- **`min_observations` is the number to revisit first.** When this project has
  its own closed work - from the plant or from the simulator - the honest move is
  to measure how much the median moves as observations accumulate, and to replace
  the argument above with that. Until then it is what it says it is.
- ADR-022's exception is now dead in practice. Reversing that is a new record,
  not a config edit.

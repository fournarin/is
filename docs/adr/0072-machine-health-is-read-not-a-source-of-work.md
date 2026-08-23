# ADR-072: Machine health is something read, and never a source of work

Sits beside
[ADR-020](0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md),
which owns prediction, and
[ADR-010](0010-work-orders-have-an-origin.md), whose three origins this record
deliberately does not extend.

## Context

Asked where to start, the advisor answered on 2026-08-23: **the assessment of
machine health - from the existing base as well as from the new sensor data.**
The same document carries his other addition, written into the diagram section:
input may not come from the signal source alone, but from the machine's existing
records, the probability of each machine failing, and so on.

Nothing in this system currently has that shape. Layer 1 is rules over single
signals producing per-event Findings (ADR-004, ADR-023). A Finding is about a
moment; health is about a machine, and it is standing rather than raised.

Two facts make this worth doing before anything else, and they are the two the
answer turns on.

**The existing base is data that exists today.** Sensor data is, in the
advisor's own words, still far off. Maintenance history is not: it lives in the
CMMS [ADR-070](0070-the-plant-has-a-cmms-and-what-that-changes.md) has just
confirmed the plant runs, in the same department as the technician, skill and
shift data the advisor said could probably be obtained. The two should be asked
for together, because they are one request to one team.

**And it is a different kind of evidence from a trend.** A machine that has
failed four times this year is telling us something no reading of its
temperature will, and it is telling it now, with no instrument installed.

## Decision

### 1. Health is a standing per-machine figure, computed when asked

Not stored as a score that ages, and not a Finding. Computed from what the
system already holds when somebody looks, for ADR-050's reason: a health figure
from last night is the wrong answer to a question about this shift, and a stored
one would need its own invalidation rules and its own way of being wrong.

### 2. Two contributions, reported separately and never blended into one number

**What this machine has done before** - time since its last failure, how often
it has failed, how much of its PM it has skipped, its age against its class -
and **what it is saying now** - open Findings, their severity, live trends and
their ETAs.

A single blended number is the failure mode this record exists to avoid. "MC-012
is at 61%" tells a supervisor nothing they can act on, and it hides which half
of the answer moved. The two are shown as two, with the figures under each,
because the actions they imply are different: history says schedule an
inspection, now says send somebody.

### 3. It creates no work, and there is no fourth origin

ADR-010's three origins stand: condition, scheduled, manual. Work born from a
statistical prior could not answer principle 3's question - *why this job, why
now* - with anything a technician would accept, and "this machine's class fails
about every 900 hours" is not a reason to send a person to it today.

What health does instead is make the **scheduled** origin better aimed: a PM
task on the machine health ranks first is the same kind of work it always was,
raised the same way, and now placed where the evidence points.

### 4. It is not a sixth term in the priority score

The score has five weighted terms and every one of them is measured in the
report (ADR-045 §1, `policy.yaml`). Adding health to it would do two bad things
at once: double-count severity and downtime, which health is partly computed
from, and change every number in the comparison already produced
(`docs/results/comparison.md`) so that slice 7.3's measurements would describe a
scheduler nobody had measured before.

Health ranks **machines**, for a person deciding what to look at. The score
ranks **work orders**, for a round deciding who goes where. Keeping them apart
is what lets either be argued about.

### 5. Measured against a synthetic history that carries its own answer key

The pattern ADR-032 and ADR-033 already establish: the generator knows which
machines it degraded and when, so "did the health ranking put the machines that
actually failed near the top" is answerable before any plant data arrives - the
same argument ADR-020 makes for prediction, and the same reason it is safe to
build this now.

### 6. The reading of "ประเมินสุขภาพ" this takes, and the one it does not

The advisor's phrase admits two readings: a standing indicator of how a machine
is doing, or a predictor of when it will fail. **This record takes the first.**

The second is already owned: ADR-020 predicts by trend extrapolation, carries an
ETA with a confidence interval, and is measured against synthetic ground truth.
A second predictor inside health would give the system two answers to "when will
this fail" with no rule for which to believe, and the one a technician saw would
depend on which screen they opened.

If that is not what was meant, this is one record to replace and no code to
unpick - which is why the assumption is stated here rather than left in a
commit.

## Consequences

- The request to the maintenance department is one request: technician, skill
  and shift data (ADR-027's four operational contracts, which the advisor has
  already said can probably be obtained) **and** the CMMS's work-order history.
  Asking twice, weeks apart, is how the second one does not arrive.
- A `MachineHistory` contract joins the eight, or the existing base is mapped
  onto `PMTask` and closed `WorkOrder` rows. That is the first thing the slice
  has to decide, and it should be decided against a real export rather than
  guessed - so the slice that builds this is written to work with a synthetic
  history first, in the shape our own closed work orders already have.
- `docs/results/` gains a third measurement beside prediction and retrieval:
  whether the health ranking finds the machines the generator broke.
- This is the advisor's answer to "where should I start", and it is recorded
  before it is built precisely because it is the piece most likely to be
  redirected once he sees a screen of it.

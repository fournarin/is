# ADR-087: The improvement loops get a screen, and deliberately no way to write

Slice 19.1, from [#107](https://github.com/fournarin/is/issues/107). The first of
the three slices [ADR-086](0086-what-this-term-does-not-do.md) leaves open for
this term. It gives [ADR-066](0066-what-the-finished-jobs-may-change-and-what-stops-them.md)
and [ADR-073](0073-what-a-false-alarm-may-propose-about-a-threshold.md) the
caller both records said was "the next slice", and it makes invariant 11 true of
running code rather than of a function nothing calls.

## Context

Loop 1 proposes a duration from the median of `repair_minutes` over closed
orders. Loop 2 proposes a separating threshold from the orders that closed
`no_problem_found`, and refuses outright for a rule marked `safety_critical`.
Both were built, tested against inputs written out by hand, and merged in August.
**Neither had a caller outside `tests/`.** `worker-runtime` registered two
handlers, dispatch and observe; no endpoint computed a proposal and no screen
showed one, so no engineer could approve one.

Both records said so at the time. ADR-066 §6: "This slice adds no endpoint, no
screen and no cadence, and until those exist the loop is a mechanism rather than
a loop that turns." ADR-073 repeats it. What neither of them did was become an
issue, and the unattended loop works only issues that exist. That is the history
in entry 32 of [decisions-to-defend](../decisions-to-defend.md), and it is why
this record exists a month later than the two it completes.

The gap had a second consequence, in the gate rather than in the behaviour.
`scripts/check_config_is_read.py` counted `safety_critical` as a field something
reads, because `work/thresholds.propose` has a parameter of that name. Nothing
carried the value from `rules.yaml` to it. The gate was passing on a coincidence,
and its own docstring said so.

## Decision

### 1. Computed when asked. No job, no table, nothing stored

`GET /loops/estimates` runs Loop 1 over every playbook that prices work.
`GET /loops/thresholds` runs Loop 2 over every rule in `rules.yaml`. Both read
rows that are already there, compute, and answer. Nothing is written, nothing is
scheduled, and no `JobKind` is added.

**Why not a job.** A `JobKind.IMPROVE` in `worker-runtime` was the other reading
of #107, and it was rejected for what it would drag behind it. A job's output has
to go somewhere to be seen, so it needs a `proposal` table; a stored proposal
needs a lifecycle - when it expires, what supersedes it when the next run
disagrees, what happens to a proposal whose playbook was re-approved underneath
it. ADR-071 built exactly that machinery for dispatch proposals, and it was worth
it there because a proposal is a decision about a person's afternoon that must
survive the round that made it. Here the proposal is a pure function of rows that
are still in the database: recomputing it costs a few reads and some arithmetic,
and it cannot be stale. That is ADR-050's argument - a read path that recomputes
cannot disagree with the writer - and ADR-066 pointed at it first: "Nothing is
stored and nothing is scheduled. A proposal is computed when asked."

**What is given up.** There is no record of what the loop proposed last week, so
nothing measures whether the estimates are converging. That is a real loss and it
is recorded rather than argued away; the evidence a proposal rests on - the
closed orders themselves - is still there, so the measurement can be made later
by a slice that wants it.

### 2. No cadence and no look-back window, and that is the decision

Each run reads **all** the closed work behind a playbook or a rule. There is no
window, and there is no schedule.

ADR-022 asks for weekly rather than per-order adjustment, and that property is
kept by where the arithmetic happens rather than by a timer: nothing changes
until a person changes it, so the rhythm is the rhythm at which an engineer opens
this screen. A cron entry would not have made the adjustment weekly. It would
have made the *computation* weekly and left the adjustment exactly where it is.

**A window was not chosen because it has no source.** Every constant in this
project needs a machine manual, a measurement of our own, or a recorded decision
(`policy.yaml`, top of file). "The last ninety days" has none of the three: no
manual states it, this project has no closed-work history to measure it from, and
a decision to prefer recent jobs would need to know how fast durations drift in
this plant, which is the thing nobody has measured. Ninety days would have looked
reasonable on the screen and meant nothing, which is the defect the provenance
rule exists to catch.

**What that costs, said plainly.** Over the whole history, a duration that
genuinely changed - new tooling, a different part - is corrected slowly, because
the old jobs stay in the median forever. The cap makes that worse, not better: a
change of more than 20% takes several cycles anyway. The moment there is enough
closed work to measure the drift, this is the decision to revisit, and the
measurement is the thing that would justify the window.

### 3. Approving writes nothing, because there is no route that could

Neither loop has a write path, and this is the decision rather than an omission.

- **Loop 1's number lives on a playbook row that carries an engineer's approval**
  (ADR-024): `approved_by`, `approved_at`, and the role held at that moment. The
  screen names the pair and the number, and the engineer enters it when they
  approve that playbook - the path that already exists and already records who
  changed it. A button here that wrote `estimated_minutes` directly would be an
  approval with no approver, on the one table where provenance is the point.
- **Loop 2's number lives in `config/rules.yaml`, which is a file, not a row.**
  #107 put it exactly: "there should not be a quiet one." The file is what layer
  1 boots from; it is reviewed like code, and a threshold that changed because
  somebody pressed a button in a browser would be a change with no diff. So the
  screen prints the edit to make - the rule, the old value, the new one - and a
  person makes it. Printing the line matters: a number retyped from memory is the
  mistake this whole screen exists to catch.

`tests/api/test_the_improvement_loops.py::TestThereIsNoWayToWriteEither` holds
the router to GET, so this stays a property of what the routes are rather than
of what the handlers happen to do.

### 4. Every rule appears, and so does every priced playbook

A rule with no closed work behind it is on the threshold list, with the named
refusal `below_floor` and `observations: 0`. A playbook with nothing to propose
is on the estimate list, with the number of closed orders read.

ADR-073 §5 already made this argument for the refusals - "the evidence says this
threshold is fine" and "there is no evidence" are not the same sentence - and it
applies just as much to a rule that is absent from the screen entirely, which
reads as a rule nobody had to think about. For the safety-linked rule the row is
the point: its refusal is permanent, and a screen that showed it only once there
were false alarms would hide the invariant until the moment it mattered.

**Loop 1's three silences are not distinguished, and the screen says so.**
`propose()` returns one `None` for too few usable jobs, for none at all, and for
a median that lands on the estimate already in the playbook. Telling them apart
on screen would mean a second copy of its rule for what counts as a usable job -
the thing ADR-066 was careful to keep in one place - so the screen reports what
it actually knows, the count of closed orders, and says that "no proposal" covers
three cases.

### 5. Invariant 12 does not arise, and invariant 11 becomes true

#107 asked which job class a loop job would be. No job is added, so the question
is moot; recorded here because the answer would not be obvious later. If one is
ever added it is `JobClass.RUNTIME` - the loops are arithmetic with no model
anywhere near them - and `worker-runtime` must still be unable to claim an
authoring job, which the `job_class` filter in `platform/jobs/repo.py::claim`
holds.

Invariant 11 is the one that changes. `rules.yaml` now carries `safety_critical`
into `thresholds.propose` through a real caller, and the refusal is tested
through the endpoint rather than by calling the function with the flag set by
hand. The test also checks the other side - a rule the file marks `false` gets a
proposal - because otherwise it would pass on a constant.

### 6. Who may read it

An engineer, who decides, and a shift lead, who does not. That is ADR-064's
argument for the review queue: somebody who cannot see a queue cannot ask why it
is not moving, and the shift lead is the person who notices that every rule is
producing false alarms. A technician and an operator are refused at the endpoint,
not by a missing link (invariant 6).

## Consequences

- The system still does not learn anything by itself, and it now shows what it
  would learn. The README and `docs/invariants.md` are updated to say the second
  rather than the first.
- `scripts/check_config_is_read.py` passes on `safety_critical` for a real reason
  now. Its docstring keeps the general warning - a name is not a read - and drops
  the example, which is no longer true.
- Loop 3 (#99) is closed for this term by ADR-086. Had it been built, this is
  where its proposals would have gone: a third route beside these two, computed
  the same way.
- Nothing about `dispatch()`, the simulator or `scripts/compare_policies.py`
  changes, so invariant 10 and the figures in `docs/results/` still describe this
  tree.
- The first time a proposal is acted on, the estimate it changes is one the
  scheduler prices every shift with. That is a decision for a person, which is
  what this record arranges, and it is entry 36 of
  [decisions-to-defend](../decisions-to-defend.md).

## What this does not do

- **It does not measure whether the loops help.** Nothing records a proposal, so
  nothing can compare the estimate before and after. §1 says what that buys.
- **It does not make the thresholds better by itself**, and could not: the
  evidence is one-sided. Nothing in this system counts the fault a higher
  threshold would have missed, so the loop can say a threshold is too tight and
  can never say it is too loose (ADR-073 §6). That sentence travels on every
  proposal to the screen.
- **It adds no cadence.** If a week goes by and nobody opens the screen, nothing
  has happened - which is the same as today, said honestly.

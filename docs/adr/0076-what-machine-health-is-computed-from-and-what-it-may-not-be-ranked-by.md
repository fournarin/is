# ADR-076: What machine health is computed from, and what it may not be ranked by

Builds [ADR-072](0072-machine-health-is-read-not-a-source-of-work.md), which
decided that health exists, that it is read rather than raised, and that it is
two contributions rather than one number. That record deliberately left four
things open, and its own Consequences section names the first of them as "the
first thing the slice has to decide". This is that decision, and the three
others it dragged in with it.

Sits beside [ADR-020](0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md),
which owns prediction and therefore owns the half of health this record measures
nothing about, and
[ADR-045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md),
whose five terms this must not become a sixth of.

## Context

ADR-072 was written before any of it was built, on purpose: it is the advisor's
answer to "where should I start", and it is the piece most likely to be
redirected once he sees a screen of it. Building it turns four of its sentences
into questions that have to be answered in code.

1. **What the history actually is.** ADR-072: "A `MachineHistory` contract joins
   the eight, or the existing base is mapped onto `PMTask` and closed
   `WorkOrder` rows."
2. **How the machines are ordered.** ADR-072 forbids blending the two
   contributions into one number, and a ranking is a number by another name.
   Saying what may not be blended does not say what the ordering inside each
   half is.
3. **What to do about the figures ADR-072 names that nothing here can compute.**
   Its history list ends "its age against its class", and this repository holds
   no machine register, no commissioning date and no per-class failure rate.
4. **What the measurement covers.** ADR-072 §5 promises a number against ground
   truth. The generator it points at writes maintenance history; the live half of
   health reads open Findings, which no history generator produces.

## Decision

### 1. No new contract: history is closed work orders and PM tasks

The second of ADR-072's two options. `MachineHistory` is not added to the eight.

The argument is the one ADR-072 made for itself and did not follow through:
the shape should be decided against a real export rather than guessed, and there
is no export. A contract invented now would be a guess with the authority of a
contract - the eight are described in `CLAUDE.md` as the things everything else
connects through, and one of them being provisional is worse than not having it.
A closed `WorkOrder` is not a guess: it is the shape this system already writes
when a technician finishes a job, so a CMMS export has something concrete to be
mapped *onto* when it arrives, and the mapping is a reader rather than a change
to the contracts.

What this costs is stated plainly: our own closed orders record less than a CMMS
export will. They carry no failure code, no downtime hours and no cost, and the
figures below are the ones that survive that.

### 2. Two contributions, two orderings, and never one list

ADR-072 §2 says the two are shown as two. A single ranking of machines is a
blend whatever it is computed from, so there are two orderings and a caller
picks one:

- **by history** - ordered by failures per hundred observed days, descending,
  ties broken by the most recent failure first.
- **by now** - ordered by the highest severity standing open, then by how many
  Findings are open, then by the soonest ETA.

Both are rates or counts over what the caller handed in, not scores. Nothing is
weighted against anything, because a weight is the blend §2 refuses, arriving
one multiplication at a time.

### 3. The history ordering is failures, and PM is reported beside it

`pm_overdue` and the false-alarm count are computed, carried and displayed, and
they are **not** in the ordering.

This is ADR-072 §2's own argument taken seriously: the two halves are kept apart
because the actions they imply differ, and the same is true inside the history
half. A machine that has failed four times wants somebody to look at it. A
machine with three PM tasks overdue wants those PM tasks scheduled - which
ADR-072 §3 says is exactly what health is for, and which is a different thing to
do. Folding them into one order would produce a list where nobody can tell which
of the two a row is telling them, and the answer to "why is MC-018 third" would
be arithmetic rather than a fact.

The false-alarm count is on the same footing for a sharper reason: a machine
whose orders keep closing `no_problem_found` has a rule problem, not a machine
problem, and ADR-073 already owns what to do about it. Ranking it up as though
it were failing would send somebody to a healthy machine on the strength of
having been sent there for nothing before.

### 4. A rate over the observed span, not a window from policy

Failures are counted over the span the caller's records actually cover - from
the earliest closed order handed in, or an `observed_from` the caller names, to
**the moment the reading is taken** - and reported as a rate per hundred days
beside the raw count and the span.

The far end is `now` and not the last closed order, which is the sharper half of
the choice. The weeks since a machine's last job closed are weeks it did not
fail, and ending the span at the last record would drop them out of the
denominator: a machine that has been quiet for three months would carry the same
rate it had on the day its last order closed, and a machine that failed once
last week would outrank it on a span of days. One span is used for every machine
in an assessment, so the rates compare - a machine whose first record is late did
not fail earlier, and that is a fact about the machine rather than about the
evidence.

The alternative was `health.window_days` in `policy.yaml`. It is refused because
it would be a number with none of the three provenances that file requires, and
because it would be the wrong shape of answer anyway: a fixed window silently
compares a machine installed last month against one installed in 2019 as though
their histories were the same length. The span is a fact about the evidence
rather than a policy about it, and it is carried on every figure so that "0.8
failures per hundred days over 41 observed days" cannot be read as though it
rested on a year.

**This slice therefore adds no constant to `policy.yaml`.** How much history to
load is the caller's decision and shows up in the answer.

### 5. Age against its class is absent, and says so

The one figure in ADR-072 §2's list that is not computed. There is no machine
register in this repository, no commissioning date on anything, and no per-class
failure rate to compare against; `plant.yaml` gives a machine a model and a
station and stops there.

It is not quietly dropped. Every `HistoryContribution` carries an `absent`
list naming the figures ADR-072 asked for that could not be computed and what
each would need, and the reason sentence a supervisor reads ends with it. That
is principle 5 held in a field rather than in a docstring: "not found - see the
manual or ask an engineer" beats a guess, and an invented machine age would be
a guess with a decimal point on it.

The register arrives with the CMMS export ADR-072's Consequences already ask
for, in the same request. This is the second thing that request buys.

### 6. The measurement covers the history half, and says which half it does not

`docs/results/health.md` reports whether the history ordering puts the machines
the generator degraded at the top, against an answer key that records which
machines were degraded and between which moments.

It reports nothing about the live half, because there is nothing honest to
report: a maintenance-history generator writes closed work orders, not signals,
and inventing open Findings to go with them would be measuring the ranking
against Findings placed there to be found. The live half's ground truth already
exists and belongs to somebody else - ADR-020 measures ETA error against the
noise-free curve, and `docs/prediction-baseline.md` is where that number lives.

So the claim this repository can support is: **the history contribution finds
the machines that failed.** Not "health finds the machines that will fail",
which is ADR-020's sentence and not this one.

### 7. `health/` imports nothing that could turn a reading into a job

ADR-072 §3 and §4 are two prohibitions - health creates no work, and health is
not a term in the priority score - and both are the kind of rule that is obeyed
until the afternoon somebody needs one number in one screen.

They are stated in `.importlinter` instead: `pdm.health` may not import
`pdm.work`, `pdm.dispatch`, `pdm.triggers`, `pdm.playbooks` or `pdm.sinks`, and
`pdm.dispatch` may not import `pdm.health`. The first makes "creates no work"
structural - a module that cannot reach the work service cannot issue an order -
and the second makes "not a sixth term" structural, because a score that cannot
import health cannot read one.

`pdm.health.domain` joins the no-I/O list for the reason `work.thresholds` did:
it is arithmetic a person has to be able to check, and a version of it that
could open a connection could also be a version that answers by asking again.

## Consequences

- The request to the maintenance department gains a third item beside ADR-072's
  two: the machine register - commissioning date and class - without which §5's
  absent figure stays absent. It is the same request to the same team.
- A new top-level package, `pdm.health`, and a row in the module table of
  `design.md` that this record is the change request for, `docs-md/` being
  outside the checkout on purpose (the precedent is `baselines`, ADR-051).
- `fixtures/history/` is a second measuring instrument beside `fixtures/corpus/`,
  under the same rule: nothing in `src/pdm` may import it, because a synthetic
  failure record in the same store as real ones is a row somebody would read.
- The two orderings are what a reviewer should attack first. If §2 or §3 is
  wrong, this is one record to replace and one module to rewrite; nothing else
  in the system reads either, by §7's construction, which is the property that
  makes it cheap to be wrong here.

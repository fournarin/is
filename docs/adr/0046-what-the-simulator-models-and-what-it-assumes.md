# ADR-046: What the simulator models, what it reads from config, and the one number it invents

## Context

ADR-021 requires the simulator to model line topology rather than a work queue,
and phase 2's deliverable is a table comparing dispatch policies on the same
scenarios. Building it raises four questions no existing record answers, and
three of them are about provenance rather than about mechanism.

**Where a simulated failure gets its properties.** A failure needs a severity, a
duration, and enough identity to become a ticket. Invented here, every one of
them would be a number in the report with nothing behind it - and the report is
what is graded.

**How the ticket is priced.** `load_ratio` is computed from `estimated_minutes`
and `required_technicians` (ADR-041). If the simulator priced its own tickets, a
comparison of policies would be partly a comparison of two pricing rules, and
the drift would be invisible because both sides would look reasonable.

**How the policies plug in.** The three things being compared are two baselines
(slice 7.2) and `dispatch()` itself. A simulator built around the signature of
the third would make the first two implementations of an interface designed for
their competitor.

**What a run may claim.** ADR-032 had to answer this for `SyntheticSource`
because its guarantees became premises of claims defended in a viva. The same is
true here, one layer along.

## Decision

### 1. Everything about a failure except its timing is read from configuration

A failure picks one of the rules `rules.yaml` declares for that machine's model
and takes that rule's `severity`, `component` and `symptom_code`. Its duration is
the `fallback_minutes` figure `policy.yaml` gives for that model and severity.

So the simulator has no vocabulary and no cost table of its own. When the plant
supplies real thresholds or real durations, the scenarios move with them, and
nothing in `pdm.sim` has to be found and updated.

### 2. The ticket is built by the work module, not by the simulator

`work.domain.from_finding`, with `playbook=None`. The estimate a policy schedules
against is the estimate a real ticket would have carried, including
`estimate_is_fallback` and an empty `required_skill` - because ADR-041 refuses to
guess a skill, and a simulator that guessed one would be measuring a matching
term the system does not have.

The consequence is worth stating plainly: **no scenario built this way exercises
skill matching**, so the w3 term of the score is not something slice 7.3 can
report on. That is a gap to name in the report, not one to close by inventing
which skill a simulated fault needs.

### 3. The true repair time is the estimate, and the simulator models no estimate error

The engine knows what a repair will take; the policy is shown only the estimate.
Today those are the same number. A spread between them could be modelled, and it
would be more realistic - but the spread would have no source, and every figure
derived from it would inherit that. ADR-006 keeps estimated and actual apart so a
real feedback loop can measure the gap; **this is not that loop**, and inventing
its input would produce a measurement of our own assumption.

### 4. Arrival rate is the one invented number, and it is declared per scenario

`ArrivalWindow.mean_hours_between_failures` stands in for a mean time between
failures nobody has measured. It has none of the three provenances `policy.yaml`
demands, and it is therefore:

- a required field with no default, so it cannot be inherited silently;
- declared in the scenario, where a reader sees it beside the claim it supports;
- **checked against ADR-011's bands rather than described in prose.** The shipped
  scenario asserts, across eight seeds, that its quiet window sits below
  `light_below` and its busy one at or above `heavy_at_or_above`. The band is the
  property being claimed; the rate is only how it was reached.

Slice 7.3 must report across several rates. One number from one assumed rate is
the same mistake ADR-021 refused for the buffer map, and the sensitivity is worth
more academically than the point estimate.

### 5. Policies arrive through a protocol the simulator does not implement

`Policy` is `choose(state) -> placements`. The engine imports no policy;
`.importlinter` keeps `pdm.sim` away from everything but contracts, work,
dispatch and platform.

`RoundState` carries what `dispatch()` takes as arguments - queue, roster, who is
unavailable, capacity, per-technician remainder, shift and date - so the adapter
in 7.2 is a translation and not a rewrite. It does **not** carry the true repair
time. A policy that could read it would schedule against the future and its
advantage in the report would belong to the instrument.

A placement naming a ticket nobody raised, somebody off the roster, a technician
already under a machine, or a crew of the wrong size raises rather than being
tolerated. Each describes a shift that could not have happened, and each would
show up in the comparison as an improvement.

### 6. What a run guarantees

- **Reproducible.** Same `(scenario, seed)`, same event log, compared with `==`.
  Arrivals are drawn from a generator seeded per `(seed, window, machine)`, so
  adding a machine leaves the others' failures where they were - the property
  ADR-032 gives signals, for the same reason.
- **Costed at the station.** ADR-021's formula, per outage: rate x
  max(0, downtime - buffer) x bottleneck multiplier.
- **Downtime starts when the machine stops**, not when a technician reaches it,
  and an outage still open when the shift ends is costed to the end of the
  window. Otherwise a policy that never reaches a machine appears to have cost
  nothing.
- **A machine with any unfinished ticket on it is down.** A second failure during
  a repair extends the outage rather than opening a second one; two overlapping
  outages would double-count the loss.
- **Time comes from `SimulatedClock`** (ADR-028), which refuses to move
  backwards - the one bug in an event loop that produces plausible output.

## Consequences

- `pdm.sim` may be imported by the comparison harness and by nothing in the
  runtime path. It is an instrument, in the same sense ADR-033 gives the manual
  corpus.
- Scenarios are code, not configuration (ADR-032's argument): they change per
  experiment, while `plant.yaml` changes when the plant is rearranged.
- Three things this deliberately does not model, each of which would need its own
  record: skill matching (§2), estimate error (§3), and technician travel time
  between stations.
- Any report figure derived from a run has to carry the arrival rate it was
  produced under. A table without that column is a table of assumptions
  presented as results.

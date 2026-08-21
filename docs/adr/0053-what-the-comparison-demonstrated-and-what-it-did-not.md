# ADR-053: What the comparison demonstrated, and what it did not

## Context

Slice 7.3 ran the two baselines and `dispatch()` over the same shifts and
committed the result. The headline is not the one the design predicted: **3C
reaches a machine in about half the time 3A takes, and 3A still loses about one
percent less production.** The pattern holds across every buffer setting and
every arrival rate in the sweep, so it is not a seed artefact.

`docs/results/README.md` reported that plainly, offered two explanations and
chose neither, on the ground that choosing needs somebody who can defend the
choice. That was the right thing to write on the day the table was produced. It
is not a thing to leave in a report, because one of the two explanations was a
finding about the gate - and a finding nobody chased is indistinguishable from
a defect nobody found.

Issue #27 put weight tuning out of scope in as many words: a weight that turns
out to be wrong is a finding to report, not something to quietly fix. This
record is that report. `scripts/diagnose_comparison.py` produces every figure
below and `docs/results/diagnosis.md` is its output; both are committed, because
a result nobody can reproduce is not evidence.

## Decision

**Five things are recorded as measured, and no weight in `config/policy.yaml`
moves.**

### 1. The harness is not what the comparison measures

`GateAndScore._starting_now` discards 416 of the 690 placements `dispatch()`
produced over twenty shifts - sixty percent - which looks alarming until it is
asked whether anybody could have started them. In **zero** of the 146 rounds
that dropped a placement was a technician left idle who could have taken one
(skill, minutes and crew size all checked). `_assign` sorts candidates by most
free capacity first, so it fills every free person before stacking a second job
on anyone; what the adapter drops is the queue in front of somebody already
working.

Priced directly, an adapter that re-dispatches until the round adds nothing
returns **identical** numbers - 1204.0 units lost, 18.23 minutes, to the digit.

### 2. The load gate costs nothing here, and one explanation is withdrawn

That explanation - the gate holding work while a technician is free, because
`load_ratio` counts everything open as committed rather than everything in
flight - is measurably not what happens on this scenario:

- with the gate **removed entirely**, admitting everything and leaving ranking
  and assignment untouched, units lost is 1204.0 against 1204.0. Response gets
  slightly *worse*, 18.23 to 18.63;
- of the 185 rounds that held something, **2** had a technician left idle who
  could have taken a held ticket.

The mechanism the explanation describes is real - `load_ratio` does count that
way, and ADR-045 §4 chose it deliberately - but on this scenario it costs
nothing, because the gate holds work when everybody is already under a machine.
The explanation comes out of `docs/results/README.md`. ADR-011 is untouched.

### 3. The two measures trade against each other, and neither policy dominates

With the gate excluded, what separates 3C from 3A is the ranking, and the
waiting weight locates it exactly. Moving w4 alone, everything else shipped:

| w_waiting | units lost | response (min) |
|---:|---:|---:|
| 0.3 (shipped) | 1204.0 | 18.23 |
| 3.0 | 1181.6 | 30.56 |
| 30.0 | 1176.8 | 32.85 |
| *3A* | *1178.9* | *37.38* |

As the score is made more oldest-first it acquires 3A's production and gives up
its own response. **That is the sentence the report should carry** - not
"first-come-first-served wins on units", which invites the reader to conclude
the scheduler is not worth having, and not "3C wins", which the units column
does not support. Oldest-first is a good approximation of "the machine that has
been down longest" and the cost function integrates downtime, so a policy that
spreads attention evenly keeps more outages under their buffer. This is the
first of the README's two explanations, and it survives.

No value in that column is a recommendation. `policy.yaml` says the five weights
are starting values; 3E, a queueing model, is the tool for setting them, and
ADR-045 already declined to guess twice.

### 4. The downtime term ranks correctly and changes nothing, and it is the arrival rate

Turning w2 off and turning it up to four moves units lost by well under one
percent at every layout in the sweep, including the unbuffered one. The
per-station breakdown says where the loss sits:

| station | 3A units lost | 3C units lost | 3A down-min | 3C down-min |
|---|---:|---:|---:|---:|
| st-01 buf 20 | 163.2 | 169.8 | 192.9 | 198.5 |
| st-02 buf 8 | 197.6 | 194.6 | 210.0 | 207.8 |
| **st-03 buf 0 ×3** | **648.4** | **647.7** | **216.1** | **215.9** |
| st-04 buf 12 | 169.6 | 191.9 | 195.6 | 215.0 |

st-03 - no buffer, bottleneck multiplier 3.0, the case ADR-021 exists for - is
54% of everything lost, and both policies lose the same amount there. Read that
far and the obvious conclusion is that the term does not work.

**It does work.** Splitting each machine's shift into waiting and repairing
shows the ranking doing exactly what it was designed to do:

| station | 3A waiting | 3C waiting | 3A repair | 3C repair | failures/shift |
|---|---:|---:|---:|---:|---:|
| st-01 buf 20 | 107.9 | 51.7 | 174.0 | 157.5 | 6.00 |
| st-02 buf 8 | 138.3 | 74.4 | 252.8 | 258.0 | 6.75 |
| **st-03 buf 0 ×3** | **189.7** | **101.9** | **285.8** | **387.0** | **7.35** |
| st-04 buf 12 | 147.9 | 19.5 | 138.0 | 73.0 | 6.80 |

At st-03, 3C nearly halves the waiting time and puts a hundred more
technician-minutes into the machine that matters most, taking them from st-04.
The score ranks the right station first and the assignment follows it.

**The outcome does not move because st-03 fails 7.35 times a shift.** A machine
is down while any unfinished ticket names it, so arriving sooner cannot be
banked: it has failed again before the benefit surfaces in an outage that has
already merged with the next one. Being twice as fast to a machine that stops
every half hour buys nothing this cost function can see.

That is a statement about the arrival rate, and it needs the competing
explanation ruled out.

### 5. It is not staffing, and the finding lands on the one unmeasured number

If the shift were simply short of people, adding people would give the term
room. `sim/scenarios.py` says of its three technicians that the roster size is
"the other half of every load ratio in this file" and that 7.3 is expected to
vary it; the committed sweep varies buffers and arrival rate and does not. It is
varied here:

| technicians | w2 off − w2 on | 3A − 3C | 3C response gain |
|---:|---:|---:|---:|
| 2 | +2.3 | −18.5 | +28.1 min |
| 3 (shipped) | +3.9 | −25.2 | +19.2 min |
| 4 | +2.3 | −9.2 | +9.8 min |
| 6 | +3.7 | −3.5 | +2.5 min |
| 8 | +0.0 | −2.2 | +0.5 min |

**The first column does not open up.** The downtime term is worth a few units at
every roster size, and the eight-technician shift - where mean response is 4.2
minutes and almost nothing waits at all - is where it is worth least. Staffing
is not the constraint.

What is left is `mean_hours_between_failures`, which ADR-046 §4 already names as
the one number in this project with no measurement behind it. **So the finding
is not that buffer-aware ranking fails. It is that whether it pays depends
entirely on a parameter nobody has measured, and this project cannot settle it
without the plant.** That is a considerably better sentence for a report than
either "the design was vindicated" or "the design lost".

The third column is worth keeping too. 3C's response advantage runs from 28.1
minutes at two technicians to 0.5 at eight: **scheduling is worth most exactly
when there are not enough people**, which is the condition a plant installs one
for. First-come-first-served's advantage on units shrinks the same way and for
the same reason - when nothing waits, no ordering of the queue matters.

## What this does not decide

**ADR-021 is not reversed and nothing about it is revisited.** That record
argues about what a stopped machine costs the line, which is a fact about the
plant. Section 4 measures the term ranking correctly and changing no outcome,
which is a fact about one arrival rate. Those are different claims and the
second does not touch the first.

The distinction is easy to lose in the other direction as well: buffers
themselves dominate this experiment completely. Across the sweep the same policy
loses 1247 units at zero stock and 840 at forty - a third of the loss removed by
the layout alone. What does not move the outcome is ranking *by* buffer at this
failure rate, which is a much narrower statement.

**The report may not present this comparison as a demonstration that
buffer-aware ranking saves production.** It is not one. What it demonstrates is
that buffer-aware ranking responds faster and reaches the critical station
sooner, and that at this arrival rate neither converts into units.

**Nothing here sets `mean_hours_between_failures`.** The finding points at it;
it does not measure it, and no value may be inferred from the fact that one
policy would look better at some other value. Choosing an assumption because it
makes the design win is the whole failure the arrival-multiplier column exists
to prevent.

**Two things this experiment cannot say anything about at all**, both already in
`docs/results/README.md` and repeated because they bound every sentence above:
the w3 skill term is never exercised (simulated tickets carry no required skill,
ADR-046 §2), and the simulator models no estimate error (ADR-046 §3), so every
policy schedules against a duration that turns out to be exactly right.

## Consequences

- `docs/results/README.md` loses the disproved explanation and gains what was
  measured in its place. The file keeps its structure: what was measured, what
  this is not, what the numbers say.
- `docs/results/diagnosis.md` joins `comparison.md` and `comparison.csv` as
  committed output, regenerated by one command.
- The ablation in `without_the_gate()` reaches into `pdm.dispatch.domain._admit`
  from a script. That is deliberate and confined: ADR-011 is a decision about
  how the system behaves rather than a setting, and giving the gate an off
  switch in production code would invite somebody to turn it off in a plant. The
  experiment is not the system (ADR-051), and a test asserts the ablation
  actually ablates - an ablation that quietly failed would report "the gate
  costs nothing" for the most convincing possible wrong reason.
- The roster size becomes an axis the diagnosis varies, which `sim/scenarios.py`
  said slice 7.3 would do and slice 7.3 did not. It stays in the diagnosis
  rather than joining the comparison grid: `comparison.csv` is the table of
  results and this is the table of why, and multiplying 1,080 runs by five
  roster sizes to answer one question would make the first file unreadable to
  serve the second.
- The report gains a defensible position on the result that looked bad, which is
  worth more at a viva than a table that flattered the design - and a concrete
  thing to ask the plant for, which is the failure rate at the bottleneck.

## References

- [ADR-011](0011-load-ratio-switches-dispatch-behaviour.md) - the load gate,
  unchanged by this record
- [ADR-021](0021-downtime-cost-at-station-level-with-buffers.md) - what a
  stopped machine costs, unchanged by this record
- [ADR-045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md) -
  the score, its five terms, and `load_ratio` counting what is open
- [ADR-046](0046-what-the-simulator-models-and-what-it-assumes.md) - what the
  simulator models and what it invents, §§2-5
- [ADR-051](0051-baselines-are-a-module-of-their-own.md) - the experiment is not
  the system

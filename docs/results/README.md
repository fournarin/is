# Results

Everything in this directory was produced by a script in this repository and can
be reproduced from a clean checkout:

```
uv run python scripts/compare_policies.py       # the table
uv run python -m scripts.diagnose_comparison    # why it says what it says
PYTHONPATH=. uv run python scripts/measure_health.py   # the health ranking
```

The first writes `comparison.csv` - every run - and `comparison.md`, which is one
reading of it. If you disagree with the reading, the rows are there to do your
own.

Two exceptions, both named rather than quietly filed among the rest.
`confirmations.md` reports a measurement that has no simulator behind it: its
rows come from a shift lead pressing confirm or reject on ADR-014's technician
trial, which has not been run, so that file carries the method and the endpoint
and states plainly that it has no figures yet (ADR-075). `health.md` prints
rather than writes, like `measure_prediction.py` does, and the figures are copied
into it by hand when they change - a measurement belongs in a document with a
date on it, and a number that changes silently on every commit is a number
nobody trusts.

## What was measured

Four scheduling policies over the same simulated shifts:

| | what it sees |
|---|---|
| **3A** first come first served | the order tickets arrived in |
| **3B** priority matrix | severity × line importance |
| **3C** gate + score | ADR-011's load gate and ADR-045's five-term score |
| **3D** gate + CP-SAT | the same gate, then a plan for the rest of the shift |

3D is not a fourth ranking. It runs the same gate and replaces only the greedy
assignment, minimising production lost to delay over the orders the gate
admitted (ADR-054). Where 3C asks *which job is worth most*, 3D asks *which job
is worth most per minute it holds somebody* - and the two disagree whenever a
long job at a well-buffered station outweighs a short one at the bottleneck.

One eight-hour shift on line A, three technicians, four machines, a quiet
four-hour window followed by a deliberately harsh one. Twenty seeds behind every
number, six buffer settings, and three arrival rates - 1,440 runs, a few minutes.

## What this is not

**No plant data has been seen.** Not one reading, not one failure record. Every
figure here comes from a generator whose parameters were chosen to produce the
two load bands ADR-011 defines, on a line layout that `plant.yaml` describes as
provisional throughout.

Specifically, and in decreasing order of how much it should worry a reader:

1. **The arrival rate is invented.** `mean_hours_between_failures` has no
   measurement behind it (ADR-046 §4). It is why there is an arrival-multiplier
   column at all: a single rate would be an assumption presented as a result.
2. **The buffer map is assumed.** ADR-021 says so in as many words. It is why
   there is a buffer sweep.
3. **The repair time is the estimate.** The simulator models no estimate error
   (ADR-046 §3), so every policy schedules against a duration that turns out to
   be exactly right. A real plant does not work like that, and the direction of
   the error is not obvious enough to guess.
4. **Skill matching is not exercised.** Simulated tickets carry no required
   skill (ADR-046 §2), so the w3 term of the score does nothing here. Any claim
   about that term is outside what this measures.
5. **One line, one shift, one roster size.** Three technicians against four
   machines is a scenario parameter, not a fact.

## What the numbers say, as of the run committed here

**3C responds fastest and 3A loses the least production.** The gate and score
reach a machine in about half the time first-come-first-served takes, and
first-come-first-served nevertheless comes out slightly ahead on units lost, by
roughly one percent. 3C beats the priority matrix on both.

That is a real result and it is not the one the design predicts, so it is worth
saying plainly rather than burying: **on this scenario, ranking work well does
not by itself save production.**

When this file was first written it offered two explanations and chose neither.
`diagnosis.md` has since taken the system apart one piece at a time, and the
choice can now be made from measurement rather than argument (ADR-053):

- **it is not the gate.** With the load gate removed entirely - admitting
  everything, ranking and assignment untouched - units lost is 1204.0 against
  1204.0, and of the 185 rounds that held something, 2 had a technician left
  idle who could have taken a held ticket. The explanation this file used to
  offer, that `load_ratio` counting everything open as committed lets the gate
  hold work while somebody is free, is withdrawn: the mechanism is real and on
  this scenario it costs nothing.
- **it is not the harness either.** `GateAndScore._starting_now` drops 60% of
  the placements `dispatch()` produces, and in none of those rounds could an
  idle technician have taken one. An adapter that re-dispatches until the round
  is full returns identical numbers.
- **it is the waiting term, and it is a trade rather than a defeat.** Raising w4
  alone walks 3C's units lost down to 1176.8 - past first-come-first-served -
  while its response climbs from 18.2 minutes to 32.9, back towards
  first-come-first-served's 37.4. **The two measures trade against each other
  here and neither policy dominates**, which is the sentence this result
  supports.

Nothing has been tuned. `policy.yaml` says the weights are starting values and
they still are; no number in `diagnosis.md` is a recommendation, and 3E is the
tool for setting them.

One further finding, and it is the one worth carrying into the report:
**ADR-021's downtime term ranks correctly and still changes nothing here.**
Moving w2 between zero and four shifts units lost by well under a percent at
every buffer setting. That looks like a broken term until the shift is split
into waiting and repairing: at st-03 - no buffer, bottleneck multiplier 3.0, the
case the record exists for - 3C cuts waiting from 189.7 minutes to 101.9 and
spends a hundred more technician-minutes there than first-come-first-served
does. The ranking works. The outcome does not move because **st-03 fails 7.35
times a shift**, and a machine is down while any unfinished ticket names it, so
arriving sooner cannot be banked before the next failure merges with the outage.

It is not that the shift is short of people: `diagnosis.md` varies the roster
from two technicians to eight and the term is worth a few units at every size,
least of all at eight. What is left is `mean_hours_between_failures` - the one
number in this project with no measurement behind it (ADR-046 §4). So this
directory does not show that buffer-aware ranking saves production, and it does
not show that it fails: **it shows that whether it pays depends on a parameter
nobody has measured yet**, which is a question for the plant rather than for
another sweep. ADR-053 records all of it.

### What 3D changes

The fourth policy is the one that moves the picture. Over the whole grid:

| | units lost | response (min) | unfinished |
|---|---:|---:|---:|
| 3A first come first served | 1106.4 | 35.04 | 20.32 |
| 3B priority matrix | 1121.4 | 19.39 | 22.27 |
| 3C gate + score | 1117.0 | 17.21 | 22.03 |
| **3D gate + CP-SAT** | **1101.3** | 17.59 | **20.88** |

**3D loses less production than 3C in all eighteen cells of the sweep** - every
buffer setting crossed with every arrival rate - and finishes more work, for 0.4
of a minute of mean response. Against first-come-first-served it wins on units in
eleven of the eighteen and responds in half the time; where it loses it loses
narrowly. So the trade-off above **narrows sharply and does not disappear**: 3D
comes close to dominating first-come-first-served rather than doing it, and the
cells it loses are the busy shifts with thick buffers - which is the same reading
as before, that when the bottleneck stops faster than anybody can reach it, no
plan helps either.

One more thing that table says, in passing: 3C's response advantage over
first-come-first-served is 28.1 minutes at two technicians and 0.5 at eight.
Scheduling is worth most exactly when there are not enough people, which is the
condition a plant installs one for.

## Files

| file | what it is |
|---|---|
| `comparison.csv` | every run: policy, buffer, arrival rate, seed, and the measures |
| `comparison.md` | means over the seeds, arranged for reading |
| `diagnosis.md` | why the table came out that way: the gate, the harness and two weights, each removed in turn |
| `confirmations.md` | how far the shift lead and the scheduler agree, and how much nobody answers - the method and the endpoint, with no figures until a trial has been run |
| `health.md` | whether the history half of a health reading ranks the machines a generator degraded above the ones it left alone, and which half of the reading it says nothing about |

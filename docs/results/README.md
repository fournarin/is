# Results

Everything in this directory was produced by a script in this repository and can
be reproduced from a clean checkout:

```
uv run python scripts/compare_policies.py       # the table
uv run python -m scripts.diagnose_comparison    # why it says what it says
PYTHONPATH=. uv run python scripts/measure_health.py   # the health ranking
```

That claim was tested on 18 September 2026, on a clean checkout and a different
machine, for the comparison as it stood then: [`reproducibility.md`](reproducibility.md)
reports 1,439 of 1,440 rows back byte for byte. The comparison has been re-run
twice since (ADR-110, ADR-124). On 3 October 2026 all three current grids
(`comparison.csv` here, in `technicians-2/` and in `technicians-1/`, 9,000 rows)
were regenerated on a clean checkout of `b9e5800` and came back byte for byte -
on the same machine, so it shows the run is deterministic, not that it travels;
ADR-110's deterministic solver budget is what is meant to make it travel.

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
number, six buffer settings, five arrival rates and an oracle - 3,000 runs per
roster size, under a minute.

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
5. **One line, one shift.** Three technicians against four machines is a
   scenario parameter, not a fact; one and two are swept beside it.
6. **Repair times are deterministic** and failures are exponential. Both are
   the simplest choices, not measurements.

## What the numbers say, as of the run committed here

**Since ADR-124 a stopped machine does not fail again.** Until then, failures
were drawn in calendar time and every one raised a ticket, so a machine already
down kept "failing" and stacking tickets - st-03 failed 7.35 times a shift, and
every earlier version of this section explained its result by exactly that.
An examiner pointed out that the deployed system does the opposite (one open
Finding per machine and rule, invariant 8) and that serial-line models count
failures in operating time. Arrivals that land while the machine is stopped are
now dropped, which for exponential gaps is the same as a failure clock that
only runs while the machine does. Everything below was measured with that model;
`failures_while_down=True` on `SimScenario` reproduces the old one.

Two further changes came with it: an **oracle** row (`0`, the same shift with
thirty technicians, so every ticket starts at the next round: the bound no
ordering of the real crew can beat), and a **roster sweep** (`technicians-1/`,
`technicians-2/`), because on a four-machine line three technicians are almost
never all busy. Five arrival multipliers now, 0.125 (eight times the failure
rate) to 2.0; twenty seeds; six buffer settings.

Grid-wide means, every buffer and multiplier:

| technicians | policy | units lost | response (min) |
|---|---|---:|---:|
| 3 (shipped) | 3A first come first served | 1081.7 | 6.14 |
| 3 | 3B priority matrix | 1081.0 | 6.18 |
| 3 | 3C gate + score | 1081.2 | 6.16 |
| 3 | 3D gate + CP-SAT | 1080.5 | 6.12 |
| 2 | 3A / 3B / 3C / 3D | 1189.4 / 1193.3 / 1194.1 / 1181.5 | 20.00 / 19.12 / 17.44 / 17.98 |
| 1 | 3A / 3B / 3C / 3D | 1427.8 / 1454.2 / 1445.6 / 1408.3 | 63.03 / 51.90 / 38.25 / 43.13 |
| any | oracle: nobody waits | 1050.8 | 2.61 |

What it supports, tested at the level of the seed with a Holm correction
(`seed-level-statistics.md` in each directory):

1. **With the shipped roster there is almost nothing for dispatch to recover.**
   The oracle loses about 3% less than any policy, and no policy differs from
   another at any multiplier after correction. Most of the loss is the repair
   itself, which no ordering shortens.
2. **With one technician the headroom is large and the policies still do not
   capture it.** The oracle loses 26% less than first come first served, yet no
   policy beats first come first served significantly at any multiplier.
3. **Ranking by severity can cost production.** With one technician the
   priority matrix loses significantly more than first come first served at the
   nominal rate (+44.2 units, 14 of 20 seeds worse, Holm p = 0.024), and 3C,
   which reaches machines in about two-thirds of the time, also loses more on
   most seeds. Responding sooner to the most severe job is not the same as
   stopping the line for less time.
4. **CP-SAT is better than the greedy score where it matters.** With one
   technician 3D loses significantly less than 3C at multipliers 0.125 and 1.0
   (18 of 20 seeds better in both, Holm p of 0.001 or less), because it
   optimises lost production directly; against first come first served it is
   ahead on average and not significantly.

The earlier reading, that the scheduler's benefit was cancelled by a machine
failing again before the gain could be banked, was an artefact of the old
model and is withdrawn. ADR-124 records the change and both sets of numbers.

## Files

| file | what it is |
|---|---|
| `comparison.csv` | every run: policy, buffer, arrival rate, seed, and the measures |
| `comparison.md` | means over the seeds, arranged for reading |
| `seed-level-statistics.md` | the same comparison with the seed as the unit: sign and Wilcoxon tests, Holm-adjusted (ADR-124) |
| `technicians-1/`, `technicians-2/` | the whole grid with one and two technicians, and its seed-level statistics |
| `diagnosis.md` | why the table came out that way: the gate, the harness and two weights, each removed in turn; `technicians-1/diagnosis.md` asks the same of the one-technician shift, where the policies actually differ |
| `confirmations.md` | how far the shift lead and the scheduler agree, and how much nobody answers - the method and the endpoint, with no figures until a trial has been run |
| `health.md` | whether the history half of a health reading ranks the machines a generator degraded above the ones it left alone, and which half of the reading it says nothing about |
| `reproducibility.md` | whether the figures above come back on another machine, which of them are exact, and why one column of 3D's is not |

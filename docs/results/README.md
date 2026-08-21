# Results

Everything in this directory was produced by a script in this repository and can
be reproduced from a clean checkout:

```
uv run python scripts/compare_policies.py
```

That writes `comparison.csv` - every run - and `comparison.md`, which is one
reading of it. If you disagree with the reading, the rows are there to do your
own.

## What was measured

Three scheduling policies over the same simulated shifts:

| | what it sees |
|---|---|
| **3A** first come first served | the order tickets arrived in |
| **3B** priority matrix | severity × line importance |
| **3C** gate + score | ADR-011's load gate and ADR-045's five-term score |

One eight-hour shift on line A, three technicians, four machines, a quiet
four-hour window followed by a deliberately harsh one. Twenty seeds behind every
number, six buffer settings, and three arrival rates - 1,080 runs, a few seconds.

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
not by itself save production.** Two explanations fit the data and this
directory does not choose between them:

- oldest-first is close to "the machine that has been down longest", and the
  cost function integrates downtime, so a policy that spreads attention evenly
  may keep more outages under their buffer;
- the gate holds medium-severity work in the heavy band, and in a stress window
  with a large backlog it can hold work while a technician is free - the load
  ratio counts everything open as committed, not everything in flight.

The second one, if it is what is happening, is a finding about the gate rather
than about the scenario, and it belongs in the report either way. Nothing has
been tuned to make this table look better; `policy.yaml` says the weights are
starting values, and they still are.

## Files

| file | what it is |
|---|---|
| `comparison.csv` | every run: policy, buffer, arrival rate, seed, and the measures |
| `comparison.md` | means over the seeds, arranged for reading |

# Machine health, measured against a history that carries its own answer key

Reproduced from a clean checkout with:

```
PYTHONPATH=. uv run python scripts/measure_health.py
```

Run of 2026-08-23. Plan `line-a-one-year`: the four machines of
`config/plant.yaml`, 365 days of closed work orders ending 2026-08-01, 40 seeds.

## The question

Health has two halves and they are never blended into one figure
([ADR-072](../adr/0072-machine-health-is-read-not-a-source-of-work.md) §2), so
there are two orderings and this measures one of them:

> ordered by what these machines have done before, does `by_history` put the
> machines that were actually failing at the top?

The generator degrades two of the four inside windows it records, and the
windows are the answer key. Nothing in the ranking sees them.

## What came out

| machine | degraded | mean rank | mean failures /100d | firsts | PM overdue | closed with no fault |
|---|---|---:|---:|---:|---:|---:|
| MC-001 | no | 3.27 | 0.82 | 0 | 1.00 | 0.00 |
| MC-004 | no | 3.70 | 0.44 | 0 | 0.00 | 1.93 |
| MC-012 | **yes** | 1.65 | 2.92 | 15 | 0.00 | 0.00 |
| MC-018 | **yes** | 1.38 | 3.38 | 25 | 0.00 | 0.00 |

- The two degraded machines took **both** of the top two places in **39 of 40**
  draws.
- First place went to a degraded machine in **40 of 40**.
- Mean rank **1.51** degraded against **3.49** healthy, out of four.
- Mean failure rate **3.15** against **0.63** per hundred days - which is the
  reason they rank there, and is worth checking separately: a ranking that were
  right about the machines and wrong about why would be right by accident.

Two of the four rows are there to be *ignored*, and both were
([ADR-076](../adr/0076-what-machine-health-is-computed-from-and-what-it-may-not-be-ranked-by.md)
§3):

- **MC-001 has a PM task three intervals overdue** and finished last or
  second-last. Overdue PM is on the reading and is displayed; it is not a key in
  the ordering, because a machine with skipped PM wants those tasks scheduled
  rather than somebody sent to look at it.
- **MC-004 closes about two orders a year finding nothing wrong** and ranks
  bottom. A rule that keeps sending somebody for nothing is
  [ADR-073](../adr/0073-what-a-false-alarm-may-propose-about-a-threshold.md)'s
  problem, and ranking the machine up for it would send a technician to a
  healthy machine on the strength of having been sent there for nothing before.

MC-018 out-ranks MC-012 on the rate although its episode **ended four months
before the history stops** and MC-012's was still running. That is the ordering
doing what it says - failures per hundred days first, recency only as a
tie-break - and it is the clearest thing in this table for a reader to disagree
with. Both figures are on the reading, so a screen can show which put a machine
where.

## What this does not measure

**The other half of a health reading is not measured at all.** A maintenance
history generator writes closed work orders, not signals, so there are no open
Findings to rank and none were invented: Findings placed there by the instrument
would be Findings the ranking was guaranteed to find. The live half's ground
truth exists already and is somebody else's - ADR-020 measures ETA error against
the noise-free curve, and `docs/prediction-baseline.md` is where that number
lives (ADR-076 §6).

So the claim this file supports is **the history contribution finds the machines
that failed**. It is not "health predicts failure", which is ADR-020's sentence.

**No plant history has been seen.** Not one work order, not one failure record.
Every parameter of the plan is invented, and in decreasing order of how much it
should worry a reader:

1. **The baseline failure rate is invented** - one failure per hundred days per
   machine. It is the same gap in the same place as
   `mean_hours_between_failures` in
   [ADR-046](../adr/0046-what-the-simulator-models-and-what-it-assumes.md) §4,
   and it sets how much evidence a year contains: at a tenth of it, four
   machines over a year would produce a handful of orders and no ordering of
   them would mean anything.
2. **The degradation multiplier is invented** - six times the baseline inside
   the window. It is the size of the effect the ranking is being asked to find,
   so it is the number that decides whether 39 of 40 is impressive or trivial.
   A smaller multiplier would be a harder test and there is nothing to say which
   one is realistic.
3. **Four machines.** "The top two of four" is a weaker claim than it reads as;
   a plant with sixty machines is a different problem, and this table says
   nothing about it.
4. **One year, one draw of a Poisson process.** Failures arrive with exponential
   gaps, which is a modelling choice rather than an observation, and it is the
   assumption that makes a rate the right summary in the first place.
5. **Age against the machine's class is not in the reading at all.** ADR-072 §2
   asked for it; nothing in this repository holds a commissioning date or a
   per-class failure rate, so every reading names it as absent rather than
   guessing it (ADR-076 §5). It arrives with the CMMS export.

## Files

| file | what it is |
|---|---|
| `fixtures/history/generator.py` | the plan, the generator, and the answer key |
| `src/pdm/health/domain.py` | the two contributions and the two orderings |
| `scripts/measure_health.py` | this measurement |

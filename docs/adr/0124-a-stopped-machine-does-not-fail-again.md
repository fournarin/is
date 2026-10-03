# ADR-124: A stopped machine does not fail again

Written on 2026-10-03 after a strict examiner's review of the report. Revisits
ADR-046 (what the simulator models) and the readings in ADR-053 that rested on
it.

## Context

The simulator drew each machine's failures in advance as a Poisson stream in
calendar time, and every arrival raised a ticket, even on a machine that was
already stopped. The machine stayed down until every one of those tickets was
repaired. At the nominal rate st-03 "failed" 7.35 times a shift, much of it while
it was already down. The report's explanation of the scheduling result - "the
machine fails again before the gain can be banked" - was this artefact.

The deployed system does the opposite: one open Finding per (machine, rule)
(invariant 8). Serial-line models count failures in operating time (Buzacott and
Shanthikumar 1993; Gershwin 1994). The examiner also asked for:
- the bound no dispatch policy can beat;
- a sweep that finds where ordering pays;
- statistics with the seed as the unit and a multiplicity correction.

## Decision

1. **An arrival that lands while its machine is stopped is dropped.** The gaps
   are exponential, so dropping them is exactly a failure clock that runs only
   while the machine does. `SimScenario.failures_while_down=True` reproduces the
   old model.
2. **An oracle row:** the same shift with thirty technicians, so every ticket
   starts at the next round. The gap between a policy and it is the most any
   ordering of the real crew could recover.
3. **The arrival sweep reaches busier plants** (multipliers 0.125, 0.25, 0.5,
   1.0, 2.0), and `--technicians` runs the grid with a smaller roster.
   One-technician and two-technician grids are committed.
4. **`scripts/seed_level_statistics.py`** averages the six buffer settings per
   (policy, multiplier, seed). It then runs exact sign and Wilcoxon signed-rank
   tests on the twenty paired differences, and Holm-adjusts across every row of
   a measure. The per-cell t-intervals stay, as description.

## What it found

| roster | finding |
|---|---|
| 3 technicians (shipped) | The oracle loses about 3% less than any policy. No policy differs from another after correction. Most of the loss is repair time. |
| 1 technician | The oracle loses 26% less than first-come-first-served. No policy beats it significantly. The priority matrix loses significantly more at the nominal rate (Holm p = 0.024). CP-SAT loses significantly less than the greedy score at multipliers 0.125 and 1.0. |

The earlier claims are withdrawn:
- "CP-SAT reduces loss against greedy in every case";
- 9 of 18 significant cells;
- buffer-aware ranking being cancelled by repeated failure.

## Consequences

- The report's scheduling chapter and the second paper are rewritten on these
  numbers.
- `reproducibility.md` describes the comparison as it stood on 18 September. It
  has not been repeated since ADR-110 or this record, and says so.
- Repair times remain deterministic and skills uniform; both are listed in
  `docs/results/README.md` as what the simulator is not.

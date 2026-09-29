# ADR-104: Numbers the report can stand on

Written on 2026-09-29, from an advisor-perspective review of the report draft.

## What the review found

Three headline numbers in the report were true and did not say what they were
read as saying:

1. **"ETA error under three minutes inside three hours"** was a signed mean over
   one seed, in which early and late cancel. The same bucket's worst case was
   270 minutes early, and there was nothing to compare the method against.
2. **"CP-SAT beats the greedy score in all 18 cells" and "beats FIFO in 11 of
   18"** compared cell means. The spread between seeds in a cell is hundreds of
   units; the gaps between policies are five to thirty.
3. **The fifth requirement had no direct evidence for its second half** -
   lower-priority work released when the shift is quiet - because the simulator
   had no scheduled maintenance in it. The gate's PM logic was tested in unit
   tests and never seen working across a shift.

## Decision

1. `scripts/measure_prediction.py` pools 21 seeds and reports, per horizon, the
   signed mean (kept, for the direction ADR-020 wants), the mean absolute error,
   the 90th percentile of |error|, and a baseline: a straight line through the
   first and last reading of the same window, asked at the same moments. The
   result is added to `docs/prediction-baseline.md` as a dated section.
2. `scripts/paired_statistics.py` reads `comparison.csv` and writes
   `docs/results/comparison-statistics.md`: per cell and per pair of policies,
   the mean paired difference over seeds with its 95% t-interval and the count
   of seeds each way. Standard library only; the t quantile is tabulated.
3. **The simulator takes scheduled maintenance** (`SimScenario.maintenance`, a
   tuple of `PMTask`). A task enters the queue when it falls due, priced by
   `from_pm_task` like any other order. It never opens an outage and never
   keeps one open: the simulator does not model a planned stop, and says so.
   The default is empty, so `comparison.csv` is unchanged.
4. `scripts/trace_the_gate.py` runs the shipped 3C on the morning shift with
   the PM tasks `plant.yaml` declares for line A, due at 06:00 and at 12:00,
   and writes every round of seed 0 to `docs/results/gate-trace.md`. On all 20
   seeds of both it checks that no PM job is placed in a round that is not
   light and no condition job is held in a round that is light, and exits
   non-zero if either happens.

## What the numbers now say

- One to three hours ahead the trend's MAE is 22 minutes (P90 52); the
  baseline's is 42. The report no longer says "under three minutes".
- CP-SAT is lower than the greedy score on 101 seeds and higher on 9, but the
  interval excludes zero in only 9 of 18 cells. Against FIFO it excludes zero
  in 3 cells; response time is 17.5 minutes faster, clearly.
- Across 40 runs the gate placed no PM job outside a light round and held no
  condition job inside one. Due at 06:00, all three PM jobs start at once; due
  at 12:00, at most one does.

## Found on the way

`scripts/worked_example.py` walks one job through the shipped functions,
signal to dispatch round, for the report's worked example. Its output showed a
PM job's `priority_reason` reading "if this job waits the line loses about 22
cars". A PM job's machine is running while it waits, so that sentence was false
on every PM ticket. The figure is what *doing* the job costs the line, and a
scheduled order now says that instead.

**Not changed, and a question for the owner:** the score still adds that
figure for PM work with a positive weight, so of two PM jobs the one that stops
the line for longer ranks higher. For condition work that is right; for
scheduled work it is arguably backwards. Changing it changes the policy the
comparison measured, so it is left as it is and named here.

## Is fusion needed? (`scripts/measure_first_stage.py`)

The owner asked whether RRF, or the sparse half, is needed once a reranker
decides. Measured as recall into the 120-chunk cut, on all three sets: dense
alone, RRF and a plain union all reach every answer page; sparse alone misses
most Thai questions, because the full-text index cannot segment Thai. The
shipped hybrid is kept - see `docs/results/first-stage.md` for why - and the
report states that it shows no measured benefit on these corpora.

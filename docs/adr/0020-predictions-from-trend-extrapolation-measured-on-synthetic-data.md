# ADR-020: Deliver prediction through trend extrapolation, measured on synthetic data

## Context

The advisor opened with a system to "**monitor and predict** maintenance" -
prediction is the first requirement stated. But the plan had chosen threshold
rules and condition-based monitoring, both of which are *detection*, and had
placed layer 1 last in the build order with a week-9 decision point to cut it as
future work.

The sum of those choices meant that in the most likely situation - sensor data
never arriving - we would deliver **nothing at all** against the advisor's first
requirement. That was never a decision anybody made; it accumulated from
prioritising one step at a time.

## Decision

Add trend extrapolation: fit the signal's trend forward to where it meets the
threshold, with a confidence interval, producing a `Finding` with
`kind = predicted`, an `eta` and an `eta_confidence`. Move layer 1 ahead of layer
3 in the build order. Change the week-9 decision from "cut layer 1" to "deliver
layer 1 measured on synthetic data and state the limitation in the report".

## Reasons

1. **It does not hit the label problem that makes supervised prediction
   impossible here**, because it does not learn from failure history - it
   computes from the signal's trend against a threshold already in the manual.
2. **`SyntheticSource` supplies ground truth by definition.** ADR-002 already
   requires it to model a motor heating gradually until it fails, which means we
   know the true failure time from the moment the data is generated, and can
   measure ETA error immediately without waiting for the plant. This is precisely
   what the author's earlier project lacked when its predictive feature was cut.
3. It does not contradict ADR-004, because it is not supervised learning. It is
   deterministic, explainable line by line, and corrected by changing a number -
   which matches every reason ADR-004 gave.
4. **It also helps layer 3.** Work predicted in advance is the clearest example
   of the lower-priority work a quiet shift should absorb. Without predicted
   Findings, that behaviour could only be tested against scheduled maintenance.
5. **It changes what can be said to the advisor**: "the prediction mechanism
   works, here is its measured accuracy on simulated data, awaiting real data to
   confirm" rather than "prediction is not done".

## Consequences

- `Finding` needs `kind`, `eta` and `eta_confidence`, and `priority_reason` must
  read differently in the two cases, because a technician treats "over threshold"
  and "expected to cross in six hours" differently.
- ETA error must be reported per forecast horizon. Accuracy falls with distance,
  and a single figure hides that.
- **The scope conversation with the advisor has to happen in week 1**: the
  accuracy delivered this term is measured on simulated data, not on Ford's
  machines.
- Trend extrapolation cannot catch sudden failures with no leading trend. The
  report must say so rather than leave an impression that everything is
  predictable.

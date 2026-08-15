# ADR-043: How a trend becomes a prediction, and what its interval means

## Context

ADR-020 committed this project to delivering prediction by trend extrapolation
and to **measuring its error on synthetic data, per forecast horizon**. It did
not say how the line is fitted, when a fit is allowed to become a `Finding`, or
what the confidence interval on an ETA is a confidence interval *of*.

The last one decides what the report can claim. `eta_confidence` reaches a
technician as "expected in about six hours, give or take two", and ADR-020 and
`ui.md` 2.2 both forbid dropping it - so it has to mean something. A fraction of
the horizon dressed up as an interval would be a number with no source, which
`workflow.md` 4.1 rejects, and it would be the number a person plans around.

There is also a collision waiting in the lifecycle. ADR-023 says a detection
supersedes an open prediction for the same (machine, component), and separately
that only one live Finding may exist per (machine, **rule**). If a prediction
carried the rule id of the threshold rule it extrapolates, the detection that
should supersede it could not be written at all: the unique index from slice 5.1
would refuse it first.

## Decision

### 1. Ordinary least squares over a time window, in plain Python

Fit `value = intercept + slope × hours` over the samples in the last
`window_minutes` (`policy.yaml`), requiring at least `min_samples`. No
dependency: the closed form is six lines, and ADR-008 forbids adding one without
a record - which this would be, for six lines.

The window is the same in-memory structure the debounce is, kept by the loop and
forgotten on restart (ADR-042 §1). A restart costs one window of samples.

### 2. A prediction is raised only when the whole interval lands inside the horizon

Three conditions, and the third is what keeps noise out:

1. the slope points at the threshold;
2. the value has not already crossed it - that is a detection, and the two must
   not both fire;
3. **the earliest and the latest crossing the interval allows are both in the
   future and within `max_horizon_hours`.**

The third replaces the obvious alternative - a significance test on the slope,
comparing it against some multiple of its standard error - which would need a
multiplier, and a multiplier is a number with no source. Requiring the whole
interval to fit inside the horizon uses only values `policy.yaml` already
carries, and it is strictly the more conservative rule: a slope indistinguishable
from noise has an interval wider than any horizon, so it cannot qualify.

### 3. The interval is one standard error of the fit, propagated to the crossing

Not a 95% interval. A t-distribution table for a handful of samples is more
machinery than the number deserves, and "one standard error" is a claim that can
be stated in one line of the report and checked against the measurement.

Concretely: the residual standard error of the regression gives the standard
error of the slope; the crossing time is `(threshold − intercept) / slope`, and
the interval is the crossing times implied by `slope ± SE(slope)`. Where the
slope's lower bound points away from the threshold, the interval is open-ended
and rule 2 rejects it.

**This is reported as what it is.** "Give or take two hours" from one standard
error is not a promise that the event falls in that window most of the time, and
the report says so rather than letting the phrase imply it.

### 4. A predicted Finding carries its own rule id: `<rule_id>/trend`

Derived, not configured. It keeps the suppression key distinct so a prediction
and the detection that supersedes it can both exist (ADR-023 §2 and §7 stop
colliding), and it reads clearly in a log: `R-motor-temp-high/trend` is
recognisably the forecast belonging to `R-motor-temp-high`.

`config/rules.yaml` gains nothing. Every threshold rule is extrapolatable by
construction, and a flag to turn prediction off per rule is a knob with no user
(`lessons_carried.md` 4.4).

### 5. Error is measured against the curve, not against the samples

`SyntheticSource.ground_truth()` returns the crossing time of the noise-free
curve (ADR-032 §1). The error of a prediction is `predicted_eta −
true_crossing`, signed, so that late and early predictions do not cancel in the
mean - and the exponential profile predicts **late**, which is the whole reason
ADR-020 requires the error to be reported per horizon.

Reported per horizon bucket, with the count in each, because a mean error over
mixed horizons is a number whose meaning depends on the mixture.

## Reasons

**The interval is the part that reaches a person.** A technician deciding whether
to stop the line tonight or tomorrow morning is acting on the width of that
window, and a width invented to look reasonable is worse than no prediction: it
is a number with the authority of a measurement and the provenance of a guess.

**Rejecting on the interval rather than on a significance threshold keeps the
constants in `policy.yaml`.** Every number in this decision already exists in the
file, with a recorded reason, and none was added to make the mechanism work.

**The derived rule id is the smallest change that unwedges the lifecycle.** The
alternative - relaxing the unique index to allow one live detection and one live
prediction per rule - would weaken the defence that makes the alarm flood
impossible, to solve a naming problem.

## Consequences

- **A prediction and a detection can both be live for one machine**, which is
  correct and is what supersession then resolves. The queue shows both until the
  detection arrives.
- **`occurrence_count` on a prediction counts re-fits**, not re-detections: every
  window that still predicts the same crossing updates the record rather than
  raising another. Whether that number means anything is a question for the
  measurement, not for this record.
- **The horizon cap makes short-fuse failures invisible to prediction.** A curve
  that crosses in ten minutes with a wide interval is rejected by rule 2 and will
  be caught by the detection rule minutes later, which is the correct outcome and
  not a silent one - the decision is visible in the trend's own reason string.
- **Step failures remain unpredictable**, as ADR-032 §4 built them to be, and the
  report has to say that trend extrapolation cannot catch a sudden failure with
  no leading trend (ADR-020's last consequence).
- The measurement script and its baseline document are part of this slice, not a
  later one: a prediction mechanism with no measured error is exactly what
  ADR-020 was written to prevent shipping.

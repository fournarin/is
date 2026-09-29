# ADR-106: A printed ETA says how far to trust it

Written on 2026-09-29. Amends what ADR-043 section 3 shows a technician; the
interval that gates a forecast is unchanged.

## What was measured

`scripts/measure_prediction.py` now reports, per horizon, how often the
"give or take" printed on a forecast ticket contained the true crossing. The
interval was one standard error of the fitted slope, which nominally covers
about 68%. Over 21 seeds of the synthetic scenario it covered:

| horizon | printed ± (median) | mean absolute error | covered |
|---|---:|---:|---:|
| 0-1 h | 1.3 min | 9 min | 18% |
| 1-3 h | 6.0 min | 22 min | 37% |
| 3-6 h | 15 min | 46 min | 48% |
| 6-12 h | 45 min | 158 min | 46% |
| 12 h+ | 100 min | 609 min | 2% |

A technician reading "± 6 minutes" would trust it far more than it deserves.
The slope's standard error leaves out the intercept, the correlation between
successive readings, and the bias of a straight line through a curve.

## Decision

1. **The interval that gates a forecast stays the slope's own** (ADR-043): it
   decides whether a crossing is inside the horizon, and it is right for that.
2. **What a ticket prints is the wider of that interval and a fraction of the
   lead time**, the fraction per horizon band from `triggers.trend.eta_error` in
   `policy.yaml`. Empty means the old behaviour.
3. **The fractions are learned, not chosen.** `scripts/calibrate_eta.py` takes
   the 80th percentile of |error| / lead time per band on seeds 0-9 and measures
   coverage once on 11 held-out seeds (split conformal). Held out, the printed
   interval now covers 74-81% against an 80% target
   (`docs/results/eta-calibration.md`). The two bands at 74% were left as
   measured.

## Consequences

- Printed intervals are several times wider: about ±40 minutes one to three
  hours ahead instead of ±7. They are now true about four times in five.
- The fractions describe the synthetic curves, not the plant. The plant
  recalibrates by running the same script over its own closed forecasts, which
  is the data ADR-020 anticipated.
- Nothing else reads `eta_confidence` to decide anything: expiry uses the ETA
  and `eta_grace_minutes`, and the score's urgency term uses the ETA alone.

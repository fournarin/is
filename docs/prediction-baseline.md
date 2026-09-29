# Prediction baseline

Produced by `scripts/measure_prediction.py`. CI does not run it, for the reason
the other baselines give: a measurement belongs in a document with a date on it,
and a figure that changes silently on every commit is a figure nobody trusts.

**Measured 13 August 2026** · trend extrapolation, ordinary least squares over a
120-minute window, minimum 10 samples, 24-hour horizon (`policy.yaml`) ·
scenario `line-a-twelve-hours`, seed 20260813 (ADR-032) · ground truth is the
crossing of the **noise-free curve**, not of the emitted samples

This is the answer to the advisor's first requirement - "monitor **and
predict**" - and to ADR-020's promise that the accuracy would be measured before
any plant data arrived.

## Across 21 seeds, in magnitude, against a baseline - 29 September 2026

The table below this one is one seed and a signed mean, and "under three
minutes inside three hours" read from it is a mean in which early and late
cancel: the same bucket's worst case is 270 minutes early. This run pools seed
20260813 and seeds 0-19, and adds the mean absolute error, the 90th percentile of
|error| and a baseline. The baseline is a straight line through the first and
last reading of the same window, with no fit and no interval gate, asked at the
same moments the trend answered, so the two are paired.

| horizon | n | signed mean | MAE | P90 of \|error\| | worst | baseline MAE | baseline P90 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0-1h | 3065 | −0.0 min | **9.1** | 17.1 | −439.3 | 15.2 | 29.8 |
| 1-3h | 6688 | +2.4 min | **22.3** | 51.8 | −413.6 | 42.4 | 64.8 |
| 3-6h | 9371 | +9.3 min | **45.6** | 126.5 | −358.6 | 100.7 | 165.9 |
| 6-12h | 4770 | +151.6 min | **158.4** | 366.7 | +448.4 | 342.9 | 538.9 |
| 12h+ | 2226 | +608.6 min | **608.6** | 799.0 | +917.0 | 1913.4 | 1893.5 |

Predictions on a channel that never crosses: 614, all `MC-018/R-cycle-time-drift`.

**What this changes.** Inside one to three hours a technician should expect a
forecast to be about 20 minutes off, and one in ten to be off by nearly an hour;
"under three minutes" is not a claim this system can make. The fitted trend's
error is about half the baseline's in every bucket, so the regression and its
interval gate earn their place. Beyond six hours both are hours out, which is
why the horizon gate exists. The data is still synthetic and the ground truth is
the curve that generated it (ADR-032): this measures the method against shapes
it was built for, not a plant.

## ETA error by forecast horizon

Error is **signed**: positive is late, negative is early. Magnitudes taken before
the mean would hide the direction, which is the thing that says which shapes of
degradation this method is wrong about.

| horizon | n | mean error | median | worst |
|---|---:|---:|---:|---:|
| 0-1h | 162 | **−2.5 min** | −0.2 | −30.5 |
| 1-3h | 327 | **−0.2 min** | +1.5 | −270.3 |
| 3-6h | 399 | **+12.5 min** | −6.2 | −219.0 |
| 6-12h | 236 | **+136.7 min** | +149.9 | +435.7 |
| 12h+ | 139 | **+608.1 min** | +630.7 | +859.3 |

Channels: `MC-001/R-motor-temp-high` (linear drift),
`MC-004/R-servo-current-high` (exponential), `MC-018/R-fan-rpm-low` (falling
linear). The 12h+ bucket is the servo alone.

## What the table says

**Accuracy falls with distance, exactly as ADR-020 predicted it would.** Inside
three hours the mean error is under three minutes in either direction; twelve
hours out it is ten hours late. A single headline figure - "mean ETA error 90 minutes" - would be
true, meaningless, and the reason ADR-020 required this to be reported per
horizon.

**The far bucket is the accelerating curve, and it is late.** A straight line
through an exponential always crosses later than the curve does, and the error
grows with the distance being extrapolated. That is the profile ADR-032 §4 built
in for this purpose: on a linear curve alone one figure would have done, and the
report would have overstated what the method can do.

**The early errors are noise, not bias.** The −270 and −219 minute worst cases in
the middle buckets are single fits where scatter tipped the slope steeper than
the curve. The medians there are close to zero while the means are not, which is
what a few large one-sided errors in a few hundred predictions looks like.

## The false alarms, which are the more interesting number

**21 predictions on a channel whose curve never crosses its threshold:**
`MC-018/R-cycle-time-drift`.

That channel is steady with noise (ADR-032 §4), so every one of those is a
forecast of an event that was never going to happen. In a twelve-hour scenario
with a sample a minute, 21 false forecasts on one channel is roughly one every
thirty minutes while the window is full.

Three things follow, and the report has to say all three:

1. **The interval gate is not a significance test.** ADR-043 §2 rejected
   inventing a multiplier and used "the whole interval must fit inside the
   horizon" instead. On a steady channel with enough scatter, a slope's interval
   can still fit - and does, here.
2. **Suppression is what makes this survivable rather than fatal.** One live
   Finding per (machine, rule) means those 21 forecasts are one record with an
   occurrence count, not 21 work orders (ADR-023, invariant 8). Without slice
   5.1 this figure would be the alarm flood.
3. **It is a number to reduce, and reducing it needs a decision nobody has
   made.** The obvious moves - requiring the slope to exceed some multiple of its
   error, or requiring N consecutive agreeing forecasts - both introduce a
   constant with no source, which is what `workflow.md` 4.1 forbids and what a
   later measurement should settle rather than a guess now.

## What changed after review

The first version of these figures extrapolated from the **last raw reading**
rather than from the fitted line, which ADR-043 §3 had specified and the code had
not done. Fixing it moved the near horizons from +1.9 and +7.7 minutes to −2.5
and −0.2, and took the false alarms from 27 to 21 - because a single noisy sample
at the end of a window was setting the answer while the interval, computed from
the slope, stayed narrow. Both sets of numbers were produced by the same
scenario and seed; only the estimator changed.

## What this cannot do

**Sudden failures are invisible.** The interlock channel in the same scenario
jumps from 1.0 to 0.0 in one sample, and produced **zero** predictions - which is
correct, and is asserted as a test rather than left to be noticed. Trend
extrapolation catches degradation with a leading trend and nothing else, and
ADR-020's last consequence requires the report to say so rather than leave an
impression that everything is predictable.

**All of this is measured on generated data.** The curves, the noise and the
thresholds are ours. What the figures establish is that the mechanism works and
how its error behaves with horizon; what they cannot establish is how a real
motor degrades. That sentence belongs in the report next to the table
(ADR-020's third consequence).

# ADR-032: What `SyntheticSource` guarantees, and what it deliberately cannot

## Context

ADR-002 requires `SyntheticSource` to model a motor heating gradually until it
fails. ADR-020 then made it the thing ETA error is measured against, which
changes what it is: not a test fixture but **the instrument every accuracy figure
in the report is produced by**. A number quoted as "MAE of 40 minutes at a
six-hour horizon" is as much a statement about this generator as about the
extrapolation.

Four questions had no answer anywhere, and each of them silently decides what
that number means:

1. The emitted samples carry noise. So what exactly is "the true time the
   threshold is crossed" - the first noisy sample above it, or something else?
2. Where do scenarios live? A fourth config file, or code?
3. Which time axis do the timestamps come from - the scenario, or the `Clock`?
4. Which shapes of degradation exist, and what does each one prove?

## Decision

### 1. Ground truth is the noise-free curve

Every profile provides `value_at(t)` and its analytic inverse
`time_until(value, comparison)`. Noise and spikes are applied to emitted samples
only and **never move the ground truth**. The true crossing time of a rule's
threshold is the inverse evaluated at that threshold; the true failure time is
the inverse evaluated at the profile's failure value.

The inverse takes the comparison, not just the value, because a threshold is
crossed in a direction: the step failure attains no value between its two
levels, so "when does it reach 1200" and "when does it fall below 1200" have
different answers, and only the second one is what a rule asks.

### 2. Scenarios are code, not a fourth config file

Frozen models in `signals/domain.py`, constructed by whoever runs them.
`config/` keeps its three files.

### 3. `SyntheticSource` does not take a `Clock`

`Signal.timestamp` comes from the scenario's own start time and sample interval.
That is *source* time (ADR-028). Pacing a stream against decision time is the
caller's job, not the generator's.

### 4. Four profiles, one of them deliberately unpredictable

Steady, linear drift, exponential (accelerating), and step. Plus per-channel
gaussian noise and optional single-sample spikes.

## Reasons

1. **Ground truth taken from the noisy samples would measure the wrong thing.**
   The first sample to exceed a threshold is a draw from the noise distribution,
   so the "error" of a prediction would include a term describing the generator's
   random number stream rather than the predictor. Defined on the underlying
   curve, the target is fixed and the effect of noise appears where it belongs -
   in the spread of the predictions, not in the thing they are compared against.
2. **Scenarios change per experiment; config changes when the plant changes.**
   That is the criterion design.md 13.1 already uses to decide config against
   table, and it puts scenarios outside config. A fourth YAML would also add
   boot-validation surface for a file no service reads, which is the pattern
   lessons_carried.md 4.4 warns about. If the simulator later needs to sweep
   scenarios from a file, that is a new decision with a consumer behind it.
3. **Point 3 is the first place ADR-028's two axes actually meet.** A generator
   that read the `Clock` would produce different data for the same scenario under
   a compressed demo run, which destroys the guarantee that (config + seed)
   determines the outcome - the guarantee the whole simulator rests on.
4. **Each profile earns its place by a claim it supports or bounds:**
   - *steady* - the detector must raise nothing on a healthy machine. Without a
     scenario that never crosses, "no false alarms" is untested.
   - *linear drift* - ADR-002's heating motor, and the case extrapolation should
     get right.
   - *exponential* - where a straight-line fit predicts **late**. This is exactly
     the error that grows with distance, which is why ADR-020 requires it
     reported per horizon rather than as one figure.
   - *step* - the sudden failure with no leading trend. ADR-020 says the report
     must state this limitation; as a profile it has a test behind it instead of
     a sentence.
5. **Noise is seeded per channel**, from (seed, machine, metric). Adding a
   machine to a scenario then leaves every other machine's data byte-identical,
   so a measurement taken last week stays comparable to one taken today.
6. **Spikes are included now, not with their consumer.** Every rule carries
   `for_seconds` so that one noisy sample is not a work order. Without transient
   excursions in the generated data, that debounce cannot be tested on synthetic
   data at all - and being untestable is the one thing this slice exists to
   prevent.

## Consequences

- **Every ETA accuracy figure in the report is against the noise-free crossing
  time, and must say so.** On real data no such target exists and the same number
  cannot be computed the same way. That is the honest limit of what ADR-020
  delivers this term.
- **The four profiles are an assumption about what degradation looks like**, and
  nothing validates that assumption until real data arrives. A predictor tuned
  until it fits them well may be a predictor tuned to fit our own guess.
- Ground truth exists only where a profile can be inverted in closed form. A
  future profile without one needs a numeric solve or has no ground truth at all,
  so adding a profile is a decision rather than an implementation detail.
- **A debounce shortens the odds of a false alarm; it does not remove them.**
  Spikes are independent per sample, so two landing together is unlikely rather
  than impossible, and a rule with a two-sample debounce will occasionally fire
  on a healthy machine. That rate is a number to be measured when the rule
  engine exists, not a property to be assumed here - and a test asserting "never
  two in a row" would be asserting something false.
- **Curves are timed to fail near the end of their window.** Nothing models what
  a machine does after it has failed, so a scenario running hours past that
  point emits invention in the shape of measurement.
- **`ReplaySource` and `LiveSource` have no ground truth.** Anything that
  measures ETA error must therefore hold a `SyntheticSource` explicitly rather
  than reach it through the `SignalSource` port, which is the one thing in the
  system that is deliberately not source-agnostic.

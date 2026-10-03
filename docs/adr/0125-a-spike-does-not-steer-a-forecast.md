# ADR-125: A spike does not steer a forecast

Written on 2026-10-03 after the examiner re-fitted the report's worked example.
Revisits ADR-043 (how a trend becomes a prediction).

## Context

The worked example printed a slope of +7.35 °C/h and a crossing at 16:09 ± 2.4 h.

- **The generator's truth:** a slope of 3.0 °C/h and a crossing at 20:40. The
  printed interval excluded the truth.
- **The cause:** three +25 °C glitch readings among 49.
- **Why the fit was exposed:** the detection rule ignores a spike because a
  breach must persist for `for_seconds`. The least-squares fit had no such
  protection, and the synthetic channels inject spikes on purpose (ADR-032).

## Decision

**A Hampel filter runs before the line is fitted** (`trend.without_spikes`).

- **The test:** a reading is dropped when it departs from the median of its
  neighbours by more than three robust standard deviations of those neighbours.
  The neighbours are three on each side, and the deviation is the MAD × 1.4826.
- **Why a Hampel filter:** a drift moves every reading together and survives,
  while a glitch leaves its neighbours and does not.
- **Cost and determinism:** linear in the window, deterministic, and no
  dependency is added (ADR-008).
- **Interval bands:** the printed-interval bands in `policy.yaml` were
  re-calibrated on the filtered forecasts (`scripts/calibrate_eta.py`).

## What it changed

Measured with `scripts/measure_prediction.py` on the same 21 seeds:

| measure | before | after |
|---|---:|---:|
| MAE, 0-1 h | 9.1 min | 5.4 min |
| MAE, 1-3 h | 22.3 min | 15.2 min |
| worst error, 0-1 h | 439 min early | 28 min late |
| false forecasts | 614 | 517 |

The worked example's first forecast is now 17:56 ± 4.4 h, made at 13:10 from ten
readings. The interval contains the true crossing.

## Consequences

- Two adjacent glitches in a window of seven can survive. The worst error in
  1-3 h is still 417 minutes early.
- A genuine step change loses its first reading to the filter and is then
  followed, because its neighbours move with it.

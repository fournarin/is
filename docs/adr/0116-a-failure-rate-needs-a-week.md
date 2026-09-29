# ADR-116: A failure rate needs a week of history

Written on 2026-09-29, from an acceptance walk on a fresh stack: the line
overview's machine health printed "MC-001 41647.5 ครั้งต่อ 100 วัน" from three
minutes of closed orders.

## Context

The history half of a health reading (ADR-076) divides failures by the span
since the earliest closed order and scales to 100 days. It refused only an empty
span. A span of minutes is an extrapolation, not a history: one failure in three
minutes is tens of thousands per hundred days, and a supervisor comparing
machines would be comparing noise.

## Decision

Below `MINIMUM_OBSERVED_DAYS` (7) the rate is `None`, and the sentence says the
history is too short to give a rate, how long it is, and how many failures it
holds. Provenance: recorded decision - a week holds every shift pattern once.
`by_history` already sorts machines with no rate last, as "nothing is known yet",
not "nothing has happened". The counts and the last failure are still shown.

## Consequences

- A new installation shows counts and no rates for its first week.
- `scripts/measure_health.py` observes 365 days and is unaffected, and so are
  the figures in the report.

# ADR-131: A predicted job's waiting costs less than a stop already happening

Written on 2026-10-04. Amends ADR-021 and ADR-054 for predicted work, as ADR-127
did for scheduled work, and replaces the half of ADR-128 §2 that left the
predicted stop's weight in the score unchanged. Decided by the agent on the
owner's delegation (ADR-090), from the fifth trial.

## Context

In trial run 5 an operator reported MC-012 stopped: severity high, about 180
units lost. It ranked below a predicted job on MC-004 (about 37 units, machine
still running, forecast crossing hours away), 2.04 to 2.10. The technician's
`/work` put the predicted job first and the urgent report under "งานถัดไป".

The downtime term ranks an order on the production lost while it waits, divided
by the largest in the round (ADR-045 §1). ADR-128 changed the predicted job's
sentence to "ถ้าเครื่องหยุดตามที่พยากรณ์ ..." because its machine is running,
but kept the term at the full stop cost. So a stop that has not happened was
priced as one that has, and the ETA term was added on top: the predicted job's
urgency was counted twice.

## Decision

1. In 3C's score a predicted order's delay cost is zero, as a scheduled order's
   is (ADR-127). How near the forecast stop is, the ETA term already carries.
   Pricing the stop by its probability would need a number nobody has
   (ADR-128 §2); zero needs no constant. Detected and manual orders are
   unchanged and are normalised against each other as before.
2. In 3D's objective a predicted order's rate is zero. 3C's score breaks the
   tie, as for scheduled work and for a machine the layout cannot price
   (ADR-048).
3. The stop cost stays in the ranking sentence as a stated fact, in ADR-128's
   words, appended after the reasons that moved the rank.
4. A technician's own list (`/work-orders/mine`) already ranks by the score
   frozen on the order. It now breaks a tie by reference, as the board does, so
   both screens put the same scores in the same order.

## Consequences

- A stop already happening outranks a forecast one of the same severity, even
  when the forecast machine would cost the line more.
- `comparison.csv` and every figure derived from it are unchanged: the policy
  comparison simulates detected failures and PM work only, never a forecast.
  `docs/results/gate-trace.md` is unchanged; `docs/results/worked-example.md`
  is regenerated (its predicted job's stop clause moves to the end).
- This fixes trial run 5's first finding.
- `tests/dispatch/test_a_forecast_stop_is_not_a_stop.py` pins the order (greedy
  and CP-SAT), the term, the solver's rate and the sentence.

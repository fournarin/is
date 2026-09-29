# ADR-105: One fault, one ticket, while the shift lead decides

Written on 2026-09-29, from an acceptance walk on a stack built fresh from
`origin/main` (d549ca3). Every role was played through a real browser.

## What was seen

After forty minutes the shift lead's board held three tickets for the same fault
on MC-004 (SYM-021, servo axis 1 current) and two for MC-001 (SYM-014). Each one
named a technician the shift lead could send.

There were two causes.

1. **A prediction's ticket survived its detection.** ADR-023 §7 has the detection
   supersede the prediction, and the runtime then withdraws the prediction's
   ticket. `cancel_untouched_for_finding` withdrew only `queued` orders. Since
   ADR-071 a new ticket spends its first minutes in `proposed`, waiting for the
   shift lead, so the withdrawal found nothing. The prediction's ticket stayed
   open beside the detection's ticket. A `proposed` order is expired back to
   `queued` when the shift lead does not answer, and a later round proposes it
   again, so it never went away.
2. **A forecast was raised for a crossing already detected and still open.**
   The belt motor was over 85 °C with its detection open. `worker-runtime`
   restarted, the synthetic scenario started again at its head start, and the
   readings were back under the threshold and still rising. The trend forecast
   the crossing again under `R-motor-temp-high/trend`, and that forecast issued
   a new ticket. Plant data does the same thing when a reading dips under a
   threshold for a moment while the trend keeps rising.

## Decision

- **`proposed` counts as untouched.** Nobody holds it, because the shift lead
  has not released it. Withdrawing a Finding's tickets now cancels `queued` and
  `proposed` orders. The pending proposal for each cancelled order is closed as
  `expired`, so it leaves the board. `assigned` and anything later stays where it
  is, as before: a ticket in somebody's hand is not taken back.
- **No forecast of a crossing already detected and open.** When the threshold
  rule's detection for the same machine is live, the trend rule's decision is
  `suppressed`, with the reason. Once the detection resolves, forecasting resumes
  under the usual cooldown.

The first rule applies to expired predictions too, through the same path.

## What this does not change

- ADR-023 §7 still has a detection supersede the prediction. This decision
  makes the withdrawal reach the tickets that ADR-071 added a state for.
- A machine under repair still gets forecasts for *other* rules. The docstring
  of `forecast` says why, and that reasoning holds.
- A restart still starts the synthetic scenario from its head start. That is
  a demo convenience (ADR-094). It no longer creates duplicate tickets.

Tests: `tests/dispatch/test_the_confirmation_gate.py::TestAPredictionOvertakenWhileItWaits`
and `tests/triggers/test_finding_lifecycle.py::…::test_no_forecast_of_a_crossing_already_detected_and_open`.
Both failed before the change.

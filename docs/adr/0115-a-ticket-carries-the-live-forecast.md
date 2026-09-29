# ADR-115: A ticket carries the live forecast

Written on 2026-09-29, from an acceptance walk on a fresh stack: for one fault
the shift lead's board said the crossing was "5 ชม. 13 นาที" away while the line
overview said 7 minutes.

## Context

A forecast is re-fitted on every reading, and ADR-042 moves the Finding's ETA
with each re-fit. The work order issued from it carries its own copy of the ETA
and its interval, because dispatch never reads a Finding (ADR-030). Nothing moved
that copy, so the ticket kept the crossing time believed at issue: the board
printed it, the round ranked by it, and the overview - which reads the Finding -
disagreed with both. In a test, a trend that steepened left the ticket five hours
twenty minutes behind its own Finding.

## Decision

1. `triggers.repo.refresh_prediction` returns the Finding it moved, and a batch
   reports its re-fitted forecasts as `Observation.refreshed`, keeping only the
   last answer per Finding.
2. The runtime worker carries each onto the open work orders of that Finding
   (`WorkOrders.follow_forecast`): queued, proposed, assigned, in progress or
   handed over. The worker is the one place that already speaks to both layers;
   the trigger layer still writes no work order and dispatch still reads no
   Finding.
3. A closed or cancelled order is not touched: it records what was believed when
   it ended (ADR-018).
4. The `reason` sentence is not rewritten. It is written once at issue (ADR-005)
   and says what the system believed then; the live ETA is what the screens and
   the round's urgency term read.

## Consequences

- The board, the technician's card and the overview agree on when a forecast
  crossing is expected, and a forecast that turns urgent rises in the ranking as
  it does.
- One extra UPDATE per re-fitted forecast per batch.

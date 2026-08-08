# ADR-025: Work orders support shift handover and multi-person jobs

## Context

`WorkOrder` had a single assignee and computed duration as close time minus start
time, neither of which matches two situations that occur constantly in a plant:
work unfinished when the shift ends, and work needing more than one technician.

## Decision

- One assignee becomes a list, each with a role of primary or helper. The
  scheduler matches skills against the primary and reserves the helper's time as
  well.
- `Playbook.required_technicians` (default 1) enters the capacity calculation.
- Add a `handed_over` status and a `handover_note` field.
- Actual duration is the **sum of work segments**, not the difference between
  first and last timestamp.
- Blocked time is recorded separately and subtracted before anything feeds back
  into estimates.

## Reasons

1. **`required_technicians` is not a detail; it is capacity.** A two-person job
   of sixty minutes costs the shift 120 person-minutes. Counted as sixty,
   `load_ratio` always reads low and the gate releases more work than there are
   people for - exactly the failure ADR-011 exists to prevent.
2. **Handover happens every day.** Without the status, the afternoon technician
   finds an open order with no idea how far the morning got and starts again from
   step one. The note is a small burden that saves the next person a great deal.
3. **Duration as first-to-last is wrong the moment a job crosses a shift.** A job
   started at three in the afternoon and finished at nine the next morning records
   eighteen hours, which destroys the estimate for that symptom from a single row.

## Consequences

- The estimate loop must compute from the sum of segments minus blocked time,
  never from raw elapsed duration.
- The interface needs a handover button that requires a short note before it can
  be pressed.
- Work handed over and not picked up must return to the queue with its waiting
  time still running, which the waiting term in the score already accounts for.

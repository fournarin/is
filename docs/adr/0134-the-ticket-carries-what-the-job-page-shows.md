# ADR-134: The ticket carries what the technician's job page shows

Written on 2026-11-16. Extends ADR-005 (every ticket explains itself), ADR-093
(screens each role already knows) and ADR-133 (one design system). Decided by
the agent on the owner's delegation (ADR-090), after the review of the rebuilt
technician screens found them faithful in form and thin in content.

## Context

The job page passed at GATE 2 shows more than the steps: the station by its
name with the line as lamps beside it, the reading behind the ticket (now,
threshold, slope), the last jobs closed on the same machine, who approved the
steps and when, "step 2 of 6, started 10:05" with a button that resumes there,
and on a job with no steps the engineer to ask. The first build left these out
because the ticket did not carry them, and the page fell back to a paragraph of
prose. The reviewers scored it 3.5/5 for that reason. Every one of these facts
is already recorded somewhere: it was only never put on the ticket.

## Decision

1. **`GET /work-orders/{ref}` grows seven fields**, each read from a record the
   system already keeps:
   - `station_name` and `machine_model`, from `plant.yaml`. Stations get an
     optional `name` there, which is a label and never a key.
   - `started_at`: the first work segment.
   - `reading`: from the Finding's `evidence`. A forecast's evidence now also
     keeps the reading the fit ends on (`value`, `unit`, `metric_name`,
     `measured_at`), because the slope alone cannot say where the machine is
     now. Rules get an optional `metric_title` ("อุณหภูมิมอเตอร์").
   - `history`: the last three jobs closed on the same machine, with outcome,
     minutes, who worked them and what they wrote.
   - `approval`: the snapshot's approver and time. The revision number is shown
     only while the served playbook is still the one the snapshot was taken
     from, so a new number is never printed over older steps.
   - `engineer`: whoever last approved a playbook for this model, or for any
     model, as the person to ask when there are no steps.
2. **Where a job's steps have got to is kept.** `POST
   /work-orders/{ref}/progress` stores one mark per order in
   `work_step_reached`, overwritten as the technician moves. It is a bookmark,
   not part of what the order instructed, so it lives beside the order and
   `playbook_snapshot` stays untouched. Only somebody on the job may move it,
   and only to a step the snapshot has. "Done, next" posts the mark; the job
   page reads it back as "ขั้น 2/6" and "ทำต่อขั้น 2".
3. **`GET /line/lamps`** gives every role each station's state and nothing else.
   It is the same fold of live Findings onto the layout that `/overview/line`
   draws for the lead, minus the shift's load and the held work, which stay
   the lead's.

## Consequences

- One table (migration 0020) and two optional config fields. No contract
  type changed; `Station` gains an optional `name`.
- Where the Finding did not record a value, the page leaves that box out rather
  than showing a figure. Older forecasts show threshold and slope only.
- The page no longer phrases anything itself. Every sentence and figure on it
  is still written by the backend or read from a record (ADR-005).

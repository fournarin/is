# ADR-117: What the technicians wrote reaches the engineer

Written on 2026-09-29, from an acceptance walk on a fresh stack: the note a
technician types when closing a job (`technician_feedback`) was stored on every
close and read by nothing.

## Context

The four-layer loop ends "technician - accept, close, propose corrections ->
back into the store". The close screen asks for an optional note, and it is
where a technician says what the procedure got wrong ("step 3 needs a 13 mm
socket, not 10"). No endpoint returned it and no screen showed it, so that half
of the loop was a text box that wrote to a column nobody queried.

## Decision

1. `GET /loops/notes` returns the latest 200 non-empty closing notes, newest
   first, with the symptom they concern (from the order's Finding, its PM task,
   or the playbook it was priced from), the machine, the outcome and when it
   closed, plus the plant's time zone. Engineers and shift leads may read it, as
   with the other improvement-loop reads (ADR-087).
2. A new engineer tab, "บันทึกจากช่าง" (`/notes`), groups them by symptom, the
   groups ordered by their newest note.
3. Nothing on the screen changes a playbook. A note that should become a step
   goes through the review queue, which records who approved it (ADR-064).

## Consequences

- The correction loop the architecture describes now has an input an engineer
  can read. It is still a person who turns a note into an approved step.
- Notes older than the latest 200 stay on their closed orders; this is a feed,
  not an archive.

# ADR-118: A ticket without steps names where to look

Written on 2026-09-30, from an acceptance walk on a fresh stack (finding A9): a
job with no approved playbook told the technician "ให้ดูคู่มือของเครื่อง หรือโทรถาม
วิศวกร อย่าเดาขั้นตอนเอง" and named no manual and no page.

## Context

Principle 5 is written as a sentence a ticket should be able to say: "Not found
- see manual page X or ask an engineer". The screen said the second half and
not the first. The system knows more than it said: which manuals are in service
for the machine's model, and - when an engineer has asked for a draft - which
pages that draft was read from.

## Decision

1. `GET /work-orders/{ref}` carries `where_to_look` when the order has no steps:
   first the pages cited by the draft waiting for review on the order's
   (symptom, model), at most three, each marked `from_unapproved_draft`; then
   every manual in service for the model.
2. The symptom comes from the order's Finding or PM task. A reported job with no
   symptom gets the manuals only.
3. Nothing is retrieved at use time and nothing is guessed. Retrieval runs only
   in the authoring worker (ADR-003); this reads rows that already exist.
4. A draft's page is a page to read, never a step to follow: the screen says it
   is from a draft an engineer has not yet approved.

## Consequences

- A technician on an uncovered job is pointed at the right manual, and often at
  the right page, instead of being told only not to guess.
- The step screen shows the manuals and pages in the block it already shows
  when there are no steps, with the draft's pages marked as unapproved.

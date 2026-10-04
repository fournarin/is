# ADR-132: The shift lead confirms to somebody else

Written on 2026-10-04. Extends ADR-071 (a round proposes, a person decides) and
ADR-120 (the shift lead's board). Decided by the agent on the owner's delegation
(ADR-090), from the owner's fifth trial.

## Context

A handover note said "ต้องใช้ช่างไฟฟ้าดูต่อ". The order carried no required
skill, so the round proposed วิชัย ("งานนี้ไม่ต้องใช้ทักษะเฉพาะ ใครว่างก็รับได้").
The shift lead knew the job was พิมพ์ชนก's and had two buttons: confirm the
wrong person, or set the job aside for the shift. Neither is what a lead at a
whiteboard does, which is move the card to the right name.

## Decision

1. `POST /dispatch/proposals/{ref}/confirm` takes an optional body
   `{"assignee": "<user id>"}`. With it, the job is confirmed to that person in
   the same transaction that queues its delivery (ADR-071 §5). Without it,
   nothing changes. Only a supervisor may call it, as before.
2. The person must be an active technician, rostered on the shift running now,
   holding the order's `required_skill` if it has one - the conditions a round
   crews by. Otherwise 422 with a Thai sentence naming the person and what is
   missing, before anything is written. Free minutes are not checked: the lead
   overruling the scheduler is often the lead knowing something the roster
   does not.
3. The chosen person becomes the primary. A crew keeps its size; if the lead
   picked the proposed helper, the proposed primary becomes the helper.
4. The proposal settles as a fifth state, `reassigned`, with the chosen crew in
   `dispatch_proposal.confirmed_assignees` beside the proposed `assignees`
   (migration 0019). It counts as answered and **not** as agreement, so
   `confirmed_share` falls exactly as it would for a rejection; the report lists
   every reassignment with both crews. Naming the proposed primary is a plain
   confirmation.
5. `GET /dispatch/proposals` gives each proposal `others`: the shift's
   technicians who pass the same check, minus the proposed primary, with their
   display names. The board shows "👷 ให้คนอื่น" with that list beside
   "✓ ยืนยัน", only when the list is not empty, and the banner after reads
   "ส่งงาน … ให้ <name> แล้ว".

## Consequences

- The agreement figure in `docs/results/confirmations.md` is over confirmed,
  rejected and reassigned; a lead who moves cards to other people is visibly
  disagreeing with the scheduler rather than inflating its agreement.
- The handover note still does not set a required skill on the order. The round
  can propose the wrong person again; this record gives the lead the move, not
  the round the knowledge.

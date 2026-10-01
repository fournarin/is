# ADR-120: The shift lead's board after the second trial

Written on 2026-10-01, from the owner's second trial of the rebuilt screens
(ADR-092; `docs/results/owner-trial.md`, run 2). Replaces ADR-071 §4 and the
consequence in ADR-056 that a handed-over order is not re-placed by a round.

## What the trial found on the board

1. **"Not now" did nothing visible.** ADR-071 §4 returned a rejected proposal to
   the queue, and the next round, five minutes later, proposed it again. To the
   shift lead the card they had just refused came straight back. The record's
   argument - a second rejection is evidence about the score - assumed a person
   willing to refuse the same card every five minutes. Nobody is.
2. **The board showed the machinery.** Each card said "if you do not answer by
   22:37 it goes back to the queue". The page was not read again after it was
   opened, so at 22:50 the sentence was false, and the expiry it described
   re-proposed the same pairing anyway, so nothing visible happened when it was
   true.
3. **A job put down disappeared.** A technician pressed "ทำไม่เสร็จ? ส่งต่อให้คนถัดไป".
   The order became `handed_over`, which no round places (ADR-056) and no
   technician's screen lists (the technician's list is their own work). The
   board showed it as "ยังไม่มีคนรับ" with nothing to press. ADR-056 said such an
   order "is picked up by a person rather than by the scheduler" and no screen
   ever let a person do that.

## Decision

1. **A rejection sets the job aside for the rest of the shift.** The order still
   returns to `queued` at once, so its crew is free. A round leaves it alone
   while the latest rejection made since the shift started has not been taken
   back. The shift is the lifetime: the person who said no goes home when it
   ends, and the next lead is asked afresh. The test is when the rejection was
   made, not the shift the proposal was made in.
2. **The lead can take it back.** The board has a "คุณพักไว้" column, shown only
   when it has something in it, listing each job with the reason the lead gave
   and a button that brings it back; the next round ranks it like any other.
   `dispatch_proposal.resumed_at` and `resumed_by` record that.
3. **A job put down with nobody left on it goes back to the queue with its
   note.** The next round offers it to the shift lead like any other job; the
   card, the technician's job card and the step screen all print the note.
   Orders already stranded as `handed_over` with nobody on them are returned to
   the queue by migration 0016. `handed_over` stays in the enum for the orders
   that carried it before.
4. **The board reads itself again every thirty seconds**, never while somebody
   is typing or has a form open. The expiry sentence is gone; the expiry
   (ADR-071 §6) still frees an unanswered proposal's crew.

`dispatch()` is handed the set-aside jobs on the queue, as it is handed the
released ones (ADR-059): it still may not read a table. A set-aside job stays in
`committed`, because the work has not gone away; it is left out of the ranking
and reported in `Round.set_aside`.

## Consequences

- The proposal record (ADR-075) still holds every rejection with its reason. It
  no longer holds a second rejection of the same card in the same shift, which
  was the evidence ADR-071 §4 wanted; in practice that evidence would have been
  a lead refusing to keep refusing.
- A job set aside at the end of a shift reappears for the next lead. That is
  intended, and the reason the first lead gave is in the record, not on the
  next lead's card.

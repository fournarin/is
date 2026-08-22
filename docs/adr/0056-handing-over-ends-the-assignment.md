# ADR-056: Handing over ends the assignment

Revisits [ADR-025](0025-work-orders-support-handover-and-multi-person-jobs.md),
which added the handover status and the segment list but did not say what
handing over does to `assignees`.

## Context

ADR-025 gave a work order a list of assignees, a `handed_over` status and a list
of work segments, and left one question unanswered: when the morning technician
hands a job to the afternoon, are they still one of its assignees?

The question is not cosmetic, because layer 3 reads that list.
`dispatch/domain.py` treats `handed_over` as a status that means *somebody has
this job* and subtracts `estimated_minutes` from every assignee of such an order
before deciding what else they can be given. A technician who handed a job over
on Monday and is still listed against it therefore loses an hour of capacity on
every shift they are rostered for afterwards, for work they are not going to do,
and nothing anywhere reports it. The scheduler simply hands them less.

The second unanswered question is the role of a person who accepts a job
somebody else already has: ADR-025 says the scheduler matches skills against the
primary and reserves the helper's time as well, but not who becomes which.

## Decision

1. **`assignees` names who holds the order now. `work_segments` is the record of
   who worked on it.** The two are different questions and this is the split
   between them.
2. **Handing over removes the handing-over technician from `assignees`**, and
   closes their open segment at the clock's time. Their work stays in
   `work_segments`, where the evidence belongs.
3. **The order becomes `handed_over` only when nobody is left on it.** A helper
   stepping off a two-person job that the primary is still working leaves the
   status where it is. The note is recorded either way, because the next person
   needs it whether they are joining or restarting.
4. **Accept decides the role by count**: the first person on an order is the
   `primary`, everyone after is a `helper`, and an order already holding
   `required_technicians` people refuses further accepts. Accepting an order one
   already holds changes nothing rather than failing - a second press on a phone
   at a machine is not an error worth a red screen.
5. **Closing an order closes every open segment**, not only the closer's. An open
   segment contributes zero to `actual_minutes` (`WorkSegment.duration`), so a
   segment left open at close silently discards the time somebody worked.
6. **`blocked_minutes` may not exceed `actual_minutes`, and the transition
   refuses rather than clamping.** `repair_minutes` already floors at zero, which
   keeps the arithmetic safe and would hide the input that was wrong: a close
   claiming ninety blocked minutes on a forty-minute job is a mis-tap or a
   misunderstanding, and Loop 1 learns from these numbers.

## Reasons

1. **A stale assignee is a capacity leak with no error.** It is the same class of
   defect as an unpriced order (ADR-041): nothing fails, the shift merely reads
   differently from the truth, and the gate then releases the wrong amount of
   work. ADR-025 already said handed-over work "must return to the queue"; a
   person who has gone home is not holding it.
2. **Removing the assignee loses nothing.** ADR-025 moved duration onto the
   segments precisely so that who worked, and for how long, is recorded
   independently of who is assigned. Asking `assignees` to answer both questions
   is what made them collide.
3. **Role by count is the only rule that needs no inference.** Deciding the
   primary from skills would mean layer 4 re-deriving a match layer 3 already
   made, and disagreeing with it on the shift where it matters.

## Consequences

- `WorkOrders.hand_over` writes the note, closes the segment and drops the
  assignee in one transaction. A handover that recorded the note without
  releasing the person would be worse than none, because it would look complete.
- **A `handed_over` order is not re-placed by a round.** `dispatch/repo.place()`
  writes only over `status = 'queued'` (its idempotence, ADR-045 §4), so an order
  nobody accepts sits with its waiting time running and is picked up by a person
  rather than by the scheduler. That is what this slice implements; whether a
  round should re-place it is a decision for layer 3 and needs its own record.
- The four transitions are the only writers of `assignees` besides
  `dispatch/repo.place()`, which is the round assigning the technician it
  selected. Both write the same shape, and neither touches `playbook_snapshot`.

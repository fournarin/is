# ADR-122: A reporter sees their reports, and the line reads in Thai

Written on 2026-10-01, from the owner's second trial (`docs/results/owner-trial.md`,
run 2, rows 1 and 7).

## Context

**A report could not be found again.** "I reported it - where did it go?" The
report screen said "รับเรื่องแล้ว WO-000017" and forgot it. The order reached the
shift lead's board as a proposal, but the person who reported it had no screen
that could show them that. The reporter was written into the reason sentence and
nowhere else, so nothing could answer the question even if a screen asked.

**The line overview did not say what it was for.** "What is this page for?" It
printed station codes, symptom codes and component labels in English
("SYM-014 · belt_motor", "unknown"), a history list of "ยังไม่มีช่วงเวลาให้หาร"
on a stack with nothing closed, and a block about what it cannot compute, at
the same weight as the faults.

## Decision

1. `work_order.reported_by` records who reported a manual order (migration
   0017), and the reason sentence names them by the name the board prints rather
   than by their sign-in.
2. `GET /work-orders/reported` returns the caller's own reports, newest first,
   each with a sentence saying where it is: waiting for the shift lead, proposed
   to whom, sent to whom, being repaired, or closed and what the technician
   found. The sentences are the backend's (ADR-063).
3. The report screen lists them under the form, and re-reads itself.
4. The line overview opens with one line saying what it is for and that the
   decisions are on the board. Each fault reads as machine and symptom title,
   with the station beneath it; codes and component labels are gone from the
   screen. With nothing closed, the history list is not drawn at all and one
   sentence says why. The caveats move into a closed "what are the limits of
   these numbers" section beside the figures they qualify (principle 5 keeps
   them on the screen; it does not make them the headline).

## Consequences

- Manual orders reported before migration 0017 carry no reporter and do not
  appear in anybody's list.
- A report is still refused while its machine has work open unless the reporter
  names that work (ADR-077 §3); the list does not change that.

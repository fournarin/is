# ADR-128: The round plans the shift

Written on 2026-10-04. Amends ADR-054 on which assignment the deployed round
makes, and ADR-021's reason sentence for predicted work. Decided by the agent on
the owner's delegation (ADR-090), from the second examiner's review.

## Context

ADR-054 built 3D - CP-SAT after the same gate - as a drop-in for 3C: the same
arguments and the same `Round`. Since then it has been compared and nothing
else. The deployed round (`dispatch/service.py`) still called 3C's `dispatch()`.
The second examiner put it plainly: the policy the system ships is the one the
evidence says does not beat first-come-first-served and loses significantly
more than 3D when staff are short, and the report never said which one runs.

What ADR-124's seed-level tests show (`docs/results/seed-level-statistics.md`,
`technicians-2/`, `technicians-1/`):

- With three technicians, 3C and 3D give the same shifts to within a fraction of
  a percent.
- With one or two technicians, 3D loses less production than 3C in all ten
  conditions (two rosters times five arrival rates). The difference is
  significant after Holm's correction in three of them, and 3D is significantly
  worse in none.
- 3D's response is significantly slower in one condition (two technicians,
  multiplier 0.125: +2.8 minutes). It optimises production lost, not response.
- ADR-110 bounded the search by a deterministic budget: 1.4 to 8.6 seconds at
  10 to 200 orders, inside the 300-second round. It also starts from 3C's plan,
  so a round is never worse than greedy by the solver's own objective.

The same review found a sentence problem that ADR-127 fixed for scheduled work
but left for predicted work. A predicted job's machine is still running, so "if
this waits, the line loses about 25 units" describes a stop that has not
happened.

## Decision

1. `policy.dispatch.planner` names the assignment the deployed round makes:
   `cp_sat` (3D, the default) or `greedy` (3C). Gate, score, reasons and
   proposals are the same either way. `dispatch.service.planner()` is the only
   code that reads the setting.
2. A predicted job's downtime clause reads "ถ้าเครื่องหยุดตามที่พยากรณ์
   สายการผลิตจะเสียราว N คัน". Its weight in the score is unchanged: pricing a
   predicted stop by its probability would need a number nobody has, and the
   ETA term already carries how near it is.
3. What CP-SAT adds to a reason or a summary is in Thai and carries no minute:
   "แผนของกะให้เริ่มงานนี้ทันที" or "...ต่อจากงานที่ช่างถืออยู่" in front of the
   score's reason, and the number left for the next round when there is one.
   Until now nothing showed 3D's text to a person, and it read "the shift plan
   starts this in 40 min; ... (optimal)" - English (ADR-093) and a frozen time
   (ADR-126). The start minute stays on the placement as `starts_in_minutes`.

## Consequences

- The shift lead's board shows CP-SAT's plan. When people are plentiful it is
  the greedy plan; when they are short it may hand a technician a job at the
  bottleneck ahead of a more severe one elsewhere, with the same reasons
  printed.
- A plant that wants the assignment a person can redo by hand sets `greedy`.
- The report says which planner runs. Its figures do not change, because the
  comparison runs both policies directly.
- `tests/dispatch/test_the_round_plans_the_shift.py` pins the default, the
  switch and the predicted wording.

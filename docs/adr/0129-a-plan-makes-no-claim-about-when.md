# ADR-129: A plan makes no claim about when

Written on 2026-10-04. Amends ADR-128 decision 3. Decided by the agent on the
owner's delegation (ADR-090), from the fourth trial (`docs/results/owner-trial.md`).

## Context

ADR-128 put CP-SAT's part of a reason in front of the score's: "แผนของกะให้
เริ่มงานนี้ทันที" for a job at minute 0 of the plan, "...ต่อจากงานที่ช่างถืออยู่"
otherwise. The minute is relative to the round that planned it. A proposal is
read for up to half an hour, while later rounds plan again around it, and a
technician already under a machine still has their first planned job at minute
0. The fourth trial found three cards for one technician, each saying "start
now" - a sentence that is true when written and false on the board.

## Decision

The plan's clause is "จัดตามแผนทั้งกะ" for every placement: it says the
assignment came from the shift's plan and makes no claim about when. The start
minute stays on the placement as `starts_in_minutes`, for anything that reads
it live.

## Consequences

- No card can contradict another about order. The order a shift lead sees is
  the board's, not a sentence's.
- `tests/dispatch/test_the_solver.py` pins the new clause, and the worked
  example is regenerated.

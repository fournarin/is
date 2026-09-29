# ADR-110: CP-SAT starts from the greedy plan, on a budget every machine agrees on

Written on 2026-09-29. Amends ADR-054 section 4. Decided by the agent on the
owner's delegation, from the findings recorded in ADR-107.

## Context

ADR-107 found that 3D spent its whole 5-second wall-clock limit in five of six
queue sizes, never proved a bound beyond ten orders, and with 50 orders and 8
technicians returned a plan whose objective was 2.7 times what a larger budget
found. A wall-clock limit also made the plan depend on the machine: one of
1,440 comparison runs changed on a faster computer, and the same ten-order model
came back OPTIMAL in one probe and FEASIBLE in another an hour apart.

## Decision

1. **The solver starts from 3C's round** (`_start_from`). `dispatch()` has
   already assigned the admitted orders to people in rank order without
   exceeding anybody's minutes; laid end to end per person that is a complete
   schedule, handed to CP-SAT as a hint. 3D can therefore no longer return a
   plan worse than the greedy one. With 50 orders and 8 technicians the
   objective halved (13.8M to 7.2M). It is not a guarantee of beating unhinted
   search: with 50 orders and 3 technicians the unhinted search happened to
   find a better plan, because the hint anchors the search near greedy.
2. **The search is bounded by CP-SAT's deterministic time**
   (`dispatch.solver_budget`, 0.5), not by the clock, so the same inputs give
   the same plan on any machine. On the development machine 0.5 took 1.4 to
   8.6 s at 10 to 200 orders, inside the 300 s round.
3. **`solver_seconds` becomes a safety cap** (30 s), set above what the budget
   takes on a long queue so that it does not bind.
4. **Symmetry breaking between identical technicians was not added.** The hint
   addressed the measured problem; symmetry constraints interact with mixed
   skills and crews and were not needed to reach the result above.

## Consequences

- The 3D column of the policy comparison changes, so `compare_policies.py` and
  `paired_statistics.py` are run again and the report's 3D figures are replaced.
- Reproducibility (ADR-054 section 4) now holds across machines, not only across
  runs on one machine.

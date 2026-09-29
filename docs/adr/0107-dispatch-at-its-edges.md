# ADR-107: Dispatch at its edges, and what CP-SAT reaches in five seconds

Written on 2026-09-29, from a pass over the dispatch round: edge cases written as
tests first, the round timed as the queue grows, and the solver probed under
larger budgets.

## Tested (`tests/dispatch/test_at_the_edges.py`)

Nobody on shift; a technician with no minutes left; load exactly at 0.5 and
0.8; fifty orders at once through both `dispatch()` and `schedule()`; a job
longer than anybody's shift; the same inputs twice. Every invariant held: no
order placed twice, nobody given more minutes than they have, no division by
zero, the same round for the same inputs, 0.5 is normal and 0.8 is heavy.

## Found

1. **The held-PM reason said something the code does not check.** It read
   "if this job were released the load would exceed 50%", but the gate checks
   whether the load *has reached* 50% before adding a job. The sentence now says
   what was checked and the load the round reached.
2. **The job that crosses the PM ceiling is released.** The ceiling is checked
   before a scheduled job is added, so one long job can take a quiet shift well
   past it: a 90-minute PM on a technician with 100 minutes left moves the load
   from 0% to 90%, the heavy band. Pinned by a test and **not changed**: when PM
   is released is the policy the comparison measured. Question for the owner.
3. **A round's time.** `docs/results/round-time.md`: 3C takes milliseconds at 200
   orders. 3D takes its whole 5-second limit in five of six cases, so a round
   costs about 5.1 s against a 300 s cadence.
4. **CP-SAT never proves a plan optimal beyond ten orders, and the 5-second plan
   is far from the best it can find.** `docs/results/solver-budget.md`: the
   proved bound is 0 in every case, so the model gives the solver nothing to
   prune with. With 50 orders and 8 technicians the objective after 5 s is 2.7
   times the one found with a larger budget. "3D" in the comparison is "CP-SAT
   with five seconds", and on long queues it may be close to its starting point.
   A deterministic budget would make it reproducible but, on this machine, costs
   36-144 s of wall time at 50-200 orders.

## Not changed, and recommended

Anything that changes what the solver returns changes the 3D column of the
comparison, which is the owner's call, and would need the comparison run again.
In order of expected value:

- **Hint the solver with 3C's assignment** (`AddHint`), so its first solution is
  the greedy plan and it can only improve on it.
- **Break the symmetry between identical technicians**, and give the objective a
  lower bound (for example the sum of weights times the earliest possible start),
  so the solver can prove something.
- **Then switch to a deterministic budget**, calibrated so a typical round fits
  its cadence, and re-run `compare_policies.py`.

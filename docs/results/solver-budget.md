# What CP-SAT reaches in its budget

**Produced by `scripts/probe_solver_budget.py` on 2026-09-29 (this machine). Minimisation: lower objective is better.**

| orders | technicians | budget | status | objective | proved bound | wall s | det |
|---:|---:|---|---|---:|---:|---:|---:|
| 10 | 3 | wall 5s (shipped) | FEASIBLE | 413100 | 0 | 5.1 | 0.98 |
| 10 | 3 | deterministic 1 | FEASIBLE | 413100 | 0 | 3.6 | 1.00 |
| 10 | 3 | deterministic 5 | OPTIMAL | 413100 | 413100 | 12.6 | 2.61 |
| 10 | 3 | deterministic 20 | OPTIMAL | 413100 | 413100 | 11.2 | 2.61 |
| 10 | 3 | wall 60s | OPTIMAL | 413100 | 413100 | 10.2 | 2.61 |
| 50 | 3 | wall 5s (shipped) | FEASIBLE | 5396100 | 0 | 5.0 | 0.34 |
| 50 | 3 | deterministic 1 | FEASIBLE | 5388090 | 0 | 11.0 | 1.00 |
| 50 | 3 | deterministic 5 | FEASIBLE | 5343060 | 0 | 35.7 | 5.06 |
| 50 | 3 | deterministic 20 | FEASIBLE | 5343060 | 0 | 118.6 | 20.00 |
| 50 | 3 | wall 60s | FEASIBLE | 5343060 | 0 | 60.0 | 9.39 |
| 50 | 8 | wall 5s (shipped) | FEASIBLE | 16129785 | 0 | 5.0 | 0.14 |
| 50 | 8 | deterministic 1 | FEASIBLE | 10069071 | 0 | 24.7 | 1.00 |
| 50 | 8 | deterministic 5 | FEASIBLE | 6561930 | 0 | 90.2 | 5.00 |
| 50 | 8 | deterministic 20 | FEASIBLE | 6077895 | 0 | 242.5 | 20.00 |
| 50 | 8 | wall 60s | FEASIBLE | 6607965 | 0 | 60.1 | 3.46 |
| 200 | 3 | wall 5s (shipped) | FEASIBLE | 76541070 | 0 | 5.0 | 0.16 |
| 200 | 3 | deterministic 1 | FEASIBLE | 73069985 | 0 | 36.1 | 1.00 |
| 200 | 3 | deterministic 5 | FEASIBLE | 68254380 | 0 | 144.0 | 5.00 |
| 200 | 3 | deterministic 20 | FEASIBLE | 64569000 | 0 | 592.9 | 20.00 |
| 200 | 3 | wall 60s | FEASIBLE | 69934455 | 0 | 60.4 | 2.40 |

# Is the comparison reproducible?

`README.md` in this directory opens with a claim: "Everything in this directory
was produced by a script in this repository and can be reproduced from a clean
checkout." Nobody had tested it. This is the test.

**Measured 18 September 2026** on a clean checkout of `main` at `9fa0a07`,
Linux, Python 3.12, `ortools` 9.15.6755 as `uv.lock` pins it. The committed
figures were produced on a different machine on 23 August 2026 from the same
code.

## The short answer

**Three of the four policies reproduce exactly. The fourth reproduces its
headline measure exactly and one of its secondary measures approximately.**

| | units lost | response (min) |
|---|---|---|
| 3A first-come-first-served | identical | identical |
| 3B priority matrix | identical | identical |
| 3C gate + score | identical | identical |
| 3D gate + CP-SAT | **identical** (1101.29) | 17.587 against 17.584 |

Of 1,440 rows in `comparison.csv`, **1,439 came back byte for byte**. The one
that moved is 3D, no buffer, arrival multiplier 0.5, seed 14, and the only
column that moved on it is `mean_response_minutes`: 25.51 against 24.29.
`units_lost`, `downtime_minutes`, tickets raised, finished and unfinished, and
every round-band count are identical on that row too.

So nothing in `README.md`'s reading is at risk. The finding that 3D loses less
production than 3C in all eighteen cells rests on `units_lost`, which did not
move anywhere.

## Why the one row moved

Not run-to-run noise. Run eight times on this machine it returns 24.29 every
time, to the last digit. The difference is between **machines**, and the cause is
in `solver.py`:

```python
solver.parameters.max_time_in_seconds = seconds   # config: 5.0
solver.parameters.num_workers = 1
solver.parameters.random_seed = 0
```

The comment above those lines explains why the parallel portfolio was turned
off: with several workers "the first worker to prove optimality wins, so several
of them make the *solution* depend on how the machine was loaded that
afternoon - which would make every figure in `docs/results/` unreproducible, and
quietly". That reasoning is right, and it applies to the line above it as well.
**`max_time_in_seconds` is wall-clock seconds, so a faster machine searches
further inside the same five seconds and can return a different answer.**

`policy.yaml` says of that budget: "on the scenarios measured here, an order of
magnitude more than the model needs. It is a ceiling, not a duration: an optimal
answer stops the search." Instrumenting every call in that one cell says
otherwise:

| | |
|---|---|
| solver calls in the cell | 15 |
| proved `OPTIMAL` | 13 |
| returned `FEASIBLE` at the ceiling | **2** |
| wall time on those two | 5.001s, against a 5.0s limit |

For thirteen of fifteen solves the comment is exactly right and the answer is
machine-independent. For two of them the ceiling binds, and what comes back is
wherever the search had got to when the clock ran out.

Sweeping the budget on that cell, with everything else held:

| budget | mean response |
|---|---|
| 0.2s | 27.58 |
| **0.5s** | **25.51** - what the committed run produced in 5.0s |
| 1.0s | 24.46 |
| 2.0s | 24.29 |
| 5.0s | 24.29 - what this machine produces |
| 20.0s | 26.87 |

`units_lost` is **1639.04 at every one of those budgets**. That is the whole
finding in one line. CP-SAT is minimising production lost to delay
([ADR-054](../adr/0054-what-cp-sat-optimises-and-what-it-may-not-touch.md)) and
response time is not in the objective, so among plans that lose the same
production it is a free variable. A longer search does not improve it; it lands
somewhere else. Twenty seconds is worse than two.

**The reported response figure for 3D is therefore not a property of the policy.
It is a property of which equally-optimal plan the solver happened to return.**
Over the whole grid that is worth three thousandths of a minute, so the table in
`README.md` is not misleading - but the number should not be read as something
3D would reproduce on other hardware, and a reader who reruns the sweep and gets
17.584 should find this page rather than conclude the rest is unreliable.

## What would make it deterministic

`ortools` has `max_deterministic_time`, a budget in units of search work rather
than seconds. It is in the pinned version. Setting it, with the wall-clock limit
left high enough to be nothing but a hang guard, removes the machine dependence:

| wall limit | as it is now | with a deterministic budget of 2.0 |
|---|---|---|
| 0.5s | 25.51 | 25.51 |
| 2.0s | 24.29 | 24.29 |
| 5.0s | 24.29 | 24.29 |
| 20.0s | 26.87 | **24.29** |

Whichever ceiling binds first still wins, which is why the 0.5s row does not
move: the clock stops the search before the work budget is spent. The budget
only becomes machine-independent once the wall-clock limit is a safety net
rather than the operative bound.

Two things follow for whoever takes this up, and neither is decided here.

**The wall-clock limit cannot simply be removed.** ADR-054's reason for bounding
the search at all is that a round is 300 seconds and a solver that could run for
a whole one "would leave the queue unranked until the instant it is replaced".
That argument is about a plant running rounds, not about a measurement script, so
the two may want different budgets.

**Raising the budget does not buy optimality here.** At deterministic budgets of
2, 4, 8 and 16 the same two solves come back `FEASIBLE`, so those two instances
are not going to be proved optimal at any budget worth spending on a shift that
turns over every five minutes. The answer settles at 24.29 for a budget of 2 and
at 26.87 for anything from 4 upwards. **A deterministic budget does not remove
the arbitrariness; it makes it the same arbitrariness everywhere**, which is
what reproducibility needs and is all it needs. The budget then joins
`mean_hours_between_failures` ([ADR-046](../adr/0046-what-the-simulator-models-and-what-it-assumes.md) §4)
on the list of parameters this project chose rather than measured, and says so.

## What was checked and what was not

Reproduced exactly from a clean checkout, against the committed documents:

- `scripts/measure_prediction.py` - every cell of the ETA table in
  `docs/prediction-baseline.md`, 36 days after it was written: mean error
  -2.5, -0.2, +12.5, +136.7, +608.1 minutes over n = 162, 327, 399, 236, 139.
- `scripts/measure_health.py` - the two degraded machines take the top two
  places in 39 of 40 draws, first place in 40 of 40, exactly as
  `docs/results/health.md` records.
- `scripts/compare_policies.py` - 1,439 of 1,440 rows, as above.

Not checked here, because both need a database, an object store and an indexed
corpus rather than a clean checkout alone: `scripts/measure_retrieval.py` and
`scripts/measure_drafting.py`. `docs/loop-log.md` records the stack reproducing
the drafting table on 26 August 2026.

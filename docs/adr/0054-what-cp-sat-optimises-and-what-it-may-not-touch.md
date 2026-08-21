# ADR-054: What CP-SAT optimises, and what it may not touch

## Context

`plan.md` names 3D as the main target and the part with academic weight. ADR-011
split scheduling into a gate and a score; ADR-045 fixed the score's five terms
and made assignment greedy down the ranking. Greedy is a good answer computed one
order at a time, and it answers a smaller question than a shift asks: given these
people, these skills and these minutes, **what is the best plan for the rest of
the shift**. Greedy cannot see that starting a two-hour job now blocks two
half-hour ones on the machine that matters more.

A constraint model is also the place in this system where code can look right,
run, and be wrong in a way no test catches unless somebody already knows the
answer. Four things therefore have to be decided in writing before the model is
worth having: what it may see, what it optimises, what it does when it fails, and
what makes it give the same answer twice.

## Decision

### 1. The gate runs first, unchanged, and is not part of the objective

`schedule()` calls `dispatch()` and optimises over what came back admitted -
the orders it placed **and** the ones it admitted and could not crew. Everything
before assignment is the same code producing the same answer: `load_ratio`, the
band, admission in score order, the five normalised terms.

Folding the load term into one objective was the alternative and is refused for
the reason ADR-011 gives: it produces weights nobody can explain to a shift lead,
and it costs the sentence that record exists to protect - "this shift is at 92%,
four non-urgent jobs are being held". A supervisor overruled by an optimiser that
cannot say why stops using it, and `plan.md` treats that as the failure mode that
matters most.

So 3D replaces exactly one stage, ADR-045 §5's greedy assignment, and inherits
the rest. That is also what makes §3 below honest.

### 2. The objective is production lost to delay, in the currency ADR-021 set

Each admitted order has a **rate**: the production lost for every minute it is
delayed, which is ADR-021's `downtime_units` divided by the repair's length. The
model minimises

```
Σ  rate_i × (the minute job i starts)
```

over all admitted orders, with an order that is not scheduled this shift counted
as starting at the end of the horizon.

Three things about that:

**It is the same quantity the comparison scores.** `docs/results/` measures units
of production lost, so the objective and the measure are the same currency, and
3D's column can be read as "how close to the best plan this scenario allows".
An objective in some other unit would make that comparison an argument rather
than an arithmetic.

**The unscheduled case needs no constant.** "Not doing it costs you the whole
shift's delay" is in the same currency as every other term. A big-M penalty would
be a number with none of the three provenances this project accepts.

**A machine the layout cannot price gets a rate of zero** (ADR-048), which makes
the solver indifferent about when it runs rather than eager to run it last. "We
cannot speak for this machine" is not "this machine costs nothing", and the
difference is why the 3C score - which does know about severity and waiting -
breaks the tie, at a scale small enough that a whole unit of production per
minute outranks any difference in it.

### 3. No answer in time means 3C's answer, never no answer

The solver gets `policy.dispatch.solver_seconds`. A round that reaches the limit
without a feasible schedule returns the `Round` `dispatch()` already computed,
unchanged - not an error, not an empty plan.

A round that answered "no plan" would leave a shift with a queue nobody is
working, which is strictly worse than a good-enough ranking. This is only cheap
because of §1: 3C's answer is already in hand by the time the model is built, so
the fallback costs nothing and cannot itself fail.

`solver_seconds` is 5.0. Provenance: recorded decision, bounded by
`round_seconds` above it and by a measurement below it. A round is 300 seconds
and a solver allowed to run for a whole one would leave the queue unranked until
the instant it is replaced, so the ceiling has to be a small fraction of the
cadence.

How small is measured rather than guessed. Over 66 solver calls on five shifts of
the committed scenario - at most nine admitted orders in a round, 3.1 on average -
the model took a median of 1.4 milliseconds, 42 at the 95th percentile and 318 at
its worst. Five seconds is sixteen times the worst case observed, which is the
margin a ceiling should have and not a duration anything is expected to reach:
an optimal answer ends the search.

The margin is against instance size, and the number that moves it is how many
orders a round admits. A shift several times larger than anything measured here
would want this checked again rather than assumed.

### 4. One worker and a fixed seed, or the results are not reproducible

CP-SAT's default is a parallel portfolio, and the first worker to prove
optimality wins. With several of them the *solution* depends on how loaded the
machine was that afternoon: every figure in `docs/results/` would stop being
reproducible, and would do it quietly, because each individual run still looks
fine. `num_workers = 1` and `random_seed = 0`, and a test asserts the same shift
twice gives the same plan.

The rest of invariant 10 is unchanged: `now` is an argument, nothing opens a
connection, and every loop runs over a sorted sequence.

### 5. A `Placement` gains a start time, and only the solver fills it in

`starts_in_minutes` is `None` from `dispatch()` and means it. A ranked queue says
who a job belongs to and nothing about when it begins; a zero there would be a
promise greedy never made. `schedule()` sets it because a solver that places work
over a horizon knows the answer, and 8.2's counterfactual will need it.

Nothing is persisted differently: `repo.place()` writes assignees, score and
reason, and the plan is a decision the round returns rather than a schedule the
database holds.

### 6. The ranking is offered as a function, so the explanation survives

An order the gate admitted and greedy could not crew comes back from `dispatch()`
as a `Withheld` - a reference and a sentence. 3D places some of exactly those,
and their tickets have to carry the same five terms as everybody else's, because
ADR-005 is about every ticket and not about the ones greedy happened to like.

`ranking()` is therefore public: the same function of the round's arguments that
`dispatch()` uses on its way to a decision. `schedule()` ranks a second time and
that costs a sort. The alternative was a second implementation of the score,
which is wrong the first time a weight changes and silent about it.

### 7. The plan is a rolling horizon, not a commitment

Each round plans the whole remaining shift and only the placements starting at
minute zero are acted on; the next round plans again from what is true then.
Work already accepted is never re-planned (ADR-045 §4) - it is read, it consumes
its assignee's capacity, and it is not in the admitted set.

This is what lets the plan improve as the shift reveals itself without ever
reordering a queue under a technician who is walking to a machine, which is the
property design.md 6.2 asked for and the reason the queue is believable at all.

## What it came out as

Reported here because the record would otherwise be a design with no result.
1,440 runs, means over twenty seeds:

| | units lost | response (min) | unfinished |
|---|---:|---:|---:|
| 3A first come first served | 1106.4 | 35.04 | 20.32 |
| 3B priority matrix | 1121.4 | 19.39 | 22.27 |
| 3C gate + score | 1117.0 | 17.21 | 22.03 |
| **3D gate + CP-SAT** | **1101.3** | 17.59 | **20.88** |

Two claims, at the strength the numbers support and no further:

**3D loses less production than 3C in all eighteen cells** of the sweep - every
buffer setting crossed with every arrival rate - and finishes more work. It pays
0.4 of a minute of mean response for it. That is consistent rather than a seed
artefact, and it is the result the slice was built to get.

**Against first-come-first-served it wins on units in eleven of the eighteen**,
and where it loses it loses narrowly (1180.0 against 1178.9 at the shipped
layout). It responds in half the time throughout. So ADR-053's finding - that
response and production traded against each other and no policy dominated -
**narrows sharply with 3D in the table but does not disappear**: 3D is close to
dominating 3A rather than doing it.

The pattern in which cells it wins is worth the report's attention: 3D takes all
six of the quiet cells (arrival multiplier 2.0) and loses only in busy shifts
with thick buffers. That is consistent with ADR-053's reading - when the
bottleneck is stopping faster than anybody can reach it, no plan helps - and it
is the same measurement pointing at the same unmeasured number.

None of this is a comparison of adapters. ADR-053 established that
`_starting_now` costs 3C nothing at the shipped layout, so 3C is not being
handicapped by the seam it reaches the simulator through.

## What this does not decide

**It does not settle whether 3D is worth its dependency.** Fifteen units of
production in eleven hundred, on a scenario whose arrival rate has no
measurement behind it, against `ortools`, `pandas` and eight minutes of grid
time. That is a judgement about a plant, and the plant has not been asked.

**It does not tune anything.** The five weights are untouched and the objective
introduces no sixth.

**It does not model estimate error.** The solver plans against
`estimated_minutes` and the simulator makes that exactly right (ADR-046 §3), so
nothing here says how a plan behaves when a job runs long. That is the obvious
next question about 3D and it is not answered by this record.

**It does not decide how the counterfactual is computed.** That is 8.2 and
design.md 6.3; this record only makes it possible by keeping start times and
solving over a set small enough to re-solve.

## Consequences

- `ortools` joins the runtime dependencies. ADR-008 already names it, so no new
  technology decision is being made - but two costs are worth writing down: it
  pulls in `pandas` and `absl-py`, and it moves `protobuf` from 7.x down to 6.x.
  Both `onnxruntime` (`>=4.25.8`) and `qdrant-client` (`>=3.20.0`) accept that,
  so the retrieval stack is unaffected; the image is the thing that grows, and
  ADR-026's split means it grows for all three roles that share one image.
- `docs/results/` gains a fourth column and the grid grows by a third.
- `capacity_left`, `downtime_or_unknown` and `ranking` become public in
  `pdm.dispatch`. All three were already the single definition of something; the
  change is that the solver uses them rather than copying them.
- `policy.yaml` gains `dispatch.solver_seconds`.

## References

- [ADR-008](0008-technology-stack.md) - OR-Tools was chosen here
- [ADR-011](0011-load-ratio-switches-dispatch-behaviour.md) - the gate and the
  score are two mechanisms, and this record keeps them that way
- [ADR-021](0021-downtime-cost-at-station-level-with-buffers.md) - the currency
  the objective is written in
- [ADR-045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md) -
  §5 is the stage this replaces; §4 and §6 are inherited unchanged
- [ADR-047](0047-a-policy-may-not-spend-minutes-the-shift-does-not-have.md) -
  the no-overlap and capacity constraints
- [ADR-048](0048-a-work-order-outlives-the-layout-it-was-created-under.md) - the
  machine the layout cannot price
- [ADR-053](0053-what-the-comparison-demonstrated-and-what-it-did-not.md) - what
  the comparison this joins can and cannot show

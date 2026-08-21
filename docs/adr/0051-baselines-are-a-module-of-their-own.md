# ADR-051: The baselines are a module of their own, not part of the instrument

## Context

Phase 2's deliverable is a table comparing three scheduling policies on the same
scenarios: two baselines - first come first served, and a severity by line
importance matrix - against `dispatch()`. ADR-046 built the simulator that runs
them and said in §5 that the two baselines would be "written against the same
protocol from outside the package", so that neither is shaped by the interface
of the thing it is being compared to.

Writing them raises a question that record did not: where do they live. Three
places were possible.

**Inside `sim/`.** The simulator is the measuring instrument, in the sense
ADR-033 gives the manual corpus - not part of the system, present so that
something can be measured. A baseline is a *subject* of the measurement. Putting
one subject inside the instrument while the other two live outside it is an
asymmetry that would have to be explained in the report, and explained again
every time somebody asked why `dispatch()` is not in there too.

**Inside `dispatch/`.** Immediately wrong: it is the competitor.

**Their own module.** One more name in the tree, which `tests/test_package_layout.py`
and design.md §2 both deliberately make expensive.

## Decision

**`pdm/baselines/` is a module, and the module list gains a row.**

It may import `contracts`, `sim` (for the `Policy` protocol and `RoundState`)
and `work`, and it may import nothing else. `.importlinter` gains a contract
saying so, naming `pdm.dispatch`, `pdm.platform.db` and `psycopg` explicitly:

- **not `dispatch`**, because a baseline written against the interface of what
  it is compared to is not a baseline. It is that thing with pieces removed, and
  the comparison then measures the pieces rather than the approach.
- **not the database**, for the reason ADR-046 §5 keeps the true repair time out
  of `RoundState`: a policy that could read the world outside the round it was
  handed would have an advantage belonging to the instrument rather than to the
  policy.

`sim/` gains `pdm.baselines` on its own forbidden list, so the engine still
imports no policy - the property ADR-046 §5 claims, now structural in both
directions.

## Reasons

**The comparison is the deliverable, and its credibility rests on the three
being alike in every way except how they decide.** Three policies in three
different places, one of them inside the thing doing the measuring, invites
exactly the question a viva is for. Three policies, one instrument, and an
import rule that says none of them can see the others is a structure that
answers it before it is asked.

**The cost is one row in a table.** The module list is deliberately expensive to
change, because `.importlinter` refers to modules as literal strings and a
renamed module makes its rules go quiet instead of failing. That expense is a
reason to add modules rarely, not a reason never to add one.

## Consequences

- **design.md §2's module table needs the same row**, and this record is the
  only place that can say so: `docs-md/` is outside version control on purpose,
  so an agent working from this checkout cannot edit it. Anybody syncing the two
  should read this record as the change request.
- `tests/test_package_layout.py` lists `baselines` with a comment pointing here,
  which keeps the reason attached to the line rather than living only in a
  commit message.
- Slice 7.3's adapter over `dispatch()` does **not** belong here. It is the
  third subject and it must import `dispatch`, which this module may not; it
  belongs with the comparison harness that owns the experiment.
- If a third baseline is ever written - a plant that schedules by machine
  criticality, say - it lands here and needs no new decision.

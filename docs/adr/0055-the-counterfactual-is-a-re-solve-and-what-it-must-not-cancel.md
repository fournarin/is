# ADR-055: The counterfactual is a re-solve, and what it must not cancel

## Context

ADR-045 §8 gave 3C its explanation for free: the score is a weighted sum, and
opening the five terms costs nothing, so every ticket says why it is where it is
without anybody asking. ADR-054 replaced the assignment stage with a constraint
model and did not replace that.

3D therefore has a hole where 3C's answer was. The reason a job is third in the
plan lives inside CP-SAT, and "the optimiser decided" is not an answer - it is
the sentence that makes a technician stop believing the system. `plan.md` treats
that as the failure that matters most, because a system nobody uses has failed
whatever its objective value, and design.md 6.3 named the fix: re-solve with the
job forced late and report the difference.

Three things had to be decided to build it, and one of them was got wrong first
in a way worth recording.

## Decision

### 1. One shift, resolved once, questioned many times

`Explainer` takes exactly `schedule()`'s arguments and holds the resolved shift:
the gate's `Round`, the admitted set, the roster's remaining minutes and the
ranking. The plan is solved on first use; each question is solved on first use;
both are memoised, and `solves` counts the times CP-SAT actually ran so the
caching is a property a test can assert rather than a claim in a docstring.

This is what the issue asked for - "lazily, when somebody asks, then cached" -
and re-solving for every ticket in every round is not affordable. It is also why
`_shift()` exists in `solver.py` rather than the resolution being repeated: a
counterfactual measured against a second reading of "the same" shift is the copy
that stops being the same without saying so.

### 2. The difference is measured between schedules, in production, not between objective values

The objective ADR-054 §2 minimises carries a tie-break for orders the layout
cannot price. Quoting its value would report production **plus something that is
not production**, in a sentence that says "units".

So both schedules are priced directly - `Σ rate × start`, with an unscheduled
job at the end of the horizon, the same convention the objective uses - and the
answer is the difference. It comes out in units of production, which is what
`docs/results/` measures and what a shift lead already thinks in.

### 3. Where a constraint decided, name the constraint

A job that is not in the plan is not a job that scored badly, and the four cases
are four different sentences, in the order they are checked:

| | the sentence says | who fixes it |
|---|---|---|
| nobody rostered holds the skill | "Nobody rostered on this shift holds electrical" | a supervisor, by rostering |
| skilled, none with the minutes | "…and none of them has the 60 minutes it needs left" | a supervisor, by capacity |
| crew cannot be made | "needs 2 technicians together and only 1 could take it" | a supervisor, by pairing |
| eligible, no room | "the shift is fuller with other work than it would be with this" | nobody - it is next |

"Nobody rostered on this shift holds hydraulics" is something somebody acts on
within the hour. "It scored lower" is not, and answering the second question when
the first one applies sends somebody to argue about weights.

A job the **gate** held never reached the model at all, and the gate's own
sentence is returned verbatim. ADR-011 wrote that sentence to be acted on, and
nothing the solver could add improves it.

### 4. Every sentence is assembled, never generated

ADR-003 keeps the LLM out of anything a technician reads while standing at a
machine. That has always been about repair steps; it applies here for the same
reason and with less excuse, because this text is a fact about a solved model
rather than a summary of a document. A test asserts the same question gives a
byte-identical sentence, which is true of assembly and need not be true of
anything else.

### 5. "Forced to the end" pins the rest of the plan, and this is the part that was wrong

The obvious model of "what if this went last" is: add `start[this] ≥ finish[j]`
for every other job, and re-solve. It is wrong, it runs, and it produces a
confident smaller number.

`start[this] ≥ finish[j]` is trivially satisfied by **not scheduling j at all**.
A solver minimising cost will do exactly that, and on the two-job shift in the
tests it did: it deleted the 120-minute job rather than moving the 30-minute one
behind it, and answered "0 minutes later, about 225 units" instead of "120
minutes later, about 335 units". Both numbers are arithmetic on a real schedule.
Only one of them answers the question that was asked.

**So every job the plan scheduled is pinned present in the re-solve**, and the
ordering constraint is unconditional over those. Jobs the plan did not schedule
stay free, and the job being asked about stays free too - if going last means it
does not fit at all, "this would be left undone this shift" is the honest answer
and the sentence says so.

The failure is worth recording rather than just fixing, because of its shape: a
counterfactual that quietly relaxes the thing it is holding fixed will always
under-report, and under-reporting is the direction that makes an explanation
reassuring. Nothing about the code looked wrong. The number was simply the answer
to a different question.

## What this does not decide

**It does not put the explanation on a screen.** `Explainer` returns an `Answer`
with a sentence and the same answer in numbers; where that is rendered, and
whether a technician or only a supervisor may ask, is layer 4's and not settled
here.

**It does not cache across rounds.** An `Explainer` is one round's worth of
answers and the next round builds another. Anything longer-lived would have to
decide when an answer stops being true, and the answer stops being true the
moment the queue changes - which is every five minutes (ADR-054 §7).

**It does not explain 3C.** 3C already opens its terms (ADR-045 §8) and needs
nothing here.

**It says nothing about how expensive this is at plant scale.** One extra solve
per question, on rounds that took a median of 1.4 ms in the measurement behind
ADR-054 §3. That is a measurement of the scenarios in this repository, and a
shift several times larger wants it taken again.

## Consequences

- `pdm/dispatch/explain.py` joins the package; `Explainer`, `Answer` and
  `Reason` are exported from `pdm.dispatch`.
- `solver.py` gains `_shift()`, `_build()`, `_run()` and `_plan_of()` as
  separable steps, so the model is constructed by one piece of code and used by
  two. `schedule()` is unchanged in behaviour and its tests were not touched.
- `_Plan` does **not** carry the objective value. It would be the natural thing
  for a counterfactual to subtract, and §2 says why it must not.

## References

- [ADR-003](0003-no-llm-generated-repair-text-at-runtime.md) - nothing a
  technician reads at a machine is generated
- [ADR-005](0005-every-ticket-carries-its-reason.md) - every ticket explains
  itself; this is that promise kept for 3D
- [ADR-011](0011-load-ratio-switches-dispatch-behaviour.md) - the gate writes
  its own sentence, and it is returned unchanged
- [ADR-045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md) -
  §8, the explanation 3C gets for free
- [ADR-054](0054-what-cp-sat-optimises-and-what-it-may-not-touch.md) - the model
  this re-solves, its currency and its determinism

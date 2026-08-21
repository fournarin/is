# ADR-047: A policy may not spend minutes the shift does not have

## Context

ADR-046 §5 lists four placements the engine refuses: a ticket nobody raised,
somebody off the roster, a technician already under a machine, and a crew of the
wrong size. Each describes a shift that could not have happened, and the argument
for refusing rather than tolerating is that every one of them would appear in the
comparison as an improvement.

There is a fifth, and it was left out. `RoundState` carries `capacity_minutes`
and `remaining_minutes` - ADR-046 §5 names them as part of what the state offers
so that the slice 7.2 adapter is a translation rather than a rewrite - but
nothing checks a placement against them. A policy may hand a technician with
twenty minutes left a ninety-minute job, and the run will report it as work done.

This is not symmetrical between the three things phase 2 compares.
`dispatch()` refuses to place an order on somebody without
`estimated_minutes` free (ADR-045 §5), because a load gate that admitted work
nobody had time for would be a gate that does not gate. The two baselines in
slice 7.2 have no such rule and no reason to invent one.

So the table slice 7.3 produces - the deliverable of phase 2 - would be
comparing a policy that respects the roster against policies that do not, and
the difference would read as the gated policy being slower to respond. The
measurement would be of the constraint, not of the policy, and nothing in the
run would say so.

## Decision

**A placement that puts a technician past their remaining minutes for the shift
is refused, as the four in ADR-046 §5 are.** It becomes the fifth entry in that
list.

The two numbers compared are the ticket's `estimated_minutes` and that
technician's `remaining_minutes`, which are the same two numbers `dispatch()`
compares (ADR-045 §5). No policy is judged against a rule its competitor is not.

**The estimate, not the true repair time.** The policy is not shown how long the
repair will take - ADR-046 §5 keeps it out of `RoundState` on purpose, because a
policy that could read it would schedule against the future. Judging a placement
by a number the policy was not allowed to see would penalise it for the
instrument's knowledge rather than for its decision. Today the two are the same
number anyway (ADR-046 §3); when estimate error is modelled, this is the record
that says which one the rule uses.

**A job that does not fit the shift is not started.** The simulator does not
model ADR-025's handover: a job runs from its start to its finish and is not set
down. So there is no way to start a ninety-minute job with twenty minutes of
shift left and hand the rest over, and pretending otherwise would credit a policy
with capacity nobody had. The loss shows up where it belongs - as downtime on a
machine still waiting - rather than as a shift that did more work than it had
people for.

## Reasons

**The engine already offers the number.** Nothing new is measured, modelled or
invented here; a constraint the state carries is enforced rather than left as
advice. That is why this is a correction to ADR-046 rather than a new model of
anything, and why it needs no source for a constant - it introduces none.

**Refusing loudly is the established answer.** ADR-046 §5's four all raise. A run
that quietly allowed the fifth would produce a plausible number, which is the
failure mode this project treats as worse than a crash: a report defended in a
viva on figures nobody could tell were wrong.

**It constrains the baselines, which is the point.** Slice 7.2's two baselines
now have to read `remaining_minutes`. That is not a burden the comparison should
avoid - a baseline that ignores the roster is not a scheduling policy, it is an
upper bound on what a scheduler could do with infinite people, and comparing
against it would flatter nothing but itself.

## Consequences

- Every policy - the two baselines and the `dispatch()` adapter alike - reads
  `remaining_minutes` before placing. The driving policy in `tests/sim` does.
- A ticket whose estimate exceeds any single technician's whole availability can
  never be placed in that shift. It stays pending and is costed as downtime,
  which is the honest outcome: the shift genuinely could not have done it.
- When handover is modelled, this record is the one to revisit - the rule above
  is a consequence of jobs being indivisible, not of anything about capacity.
- `remaining_minutes` deducts the *actual* minutes of finished work while this
  rule spends the *estimate*. ADR-046 §3 makes those the same number today, so
  the two cannot drift apart yet. They can once estimate error exists, and the
  paragraph above says which side the rule takes when they do.

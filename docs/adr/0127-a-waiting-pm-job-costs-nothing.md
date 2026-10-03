# ADR-127: A waiting PM job costs nothing

Written on 2026-10-03. Amends ADR-021 and ADR-054 for scheduled work, and
closes the question ADR-104 left open. Decided by the agent on the owner's
delegation (ADR-090).

## Context

ADR-021's downtime term prices an order at the production its machine loses for
the length of the repair, net of the station's buffer. For a condition job that
is the cost of delay: the machine is stopped, and every minute the job waits the
line loses more.

For a scheduled (PM) job it is not. The machine is running while the job waits;
the figure is what *doing* the job costs. ADR-104 corrected the sentence a shift
lead reads ("if this waits the line loses N" became "this job stops the machine;
done during production it costs about N"), and recorded that the score still
added the figure as a positive term. So of two PM jobs alike in every other way,
the one that stops the line longest ranked first - the opposite of what a shift
lead would choose - and 3D's objective did the same through its per-minute rate.
The fix was deferred because it changes a compared policy. The comparison
(`compare_policies.py`) has no scheduled work, so that reason does not hold.

## Decision

1. In 3C's score the downtime term ranks a scheduled order on the cost of
   delaying it, which is zero. The normalisation divides by the largest delay
   cost in the round, so condition jobs are ranked against each other exactly
   as before.
2. In 3D's objective a scheduled order's rate is zero: the solver is indifferent
   to when it runs, and 3C's score breaks the tie, as it does for an order whose
   machine the layout cannot price (ADR-048).
3. The stop cost stays in the ranking sentence as a stated fact, appended after
   the reasons that moved the rank, because it is what a shift lead weighs before
   releasing the job (ADR-104).

Not decided here: ranking PM work by a *negative* stop cost - preferring the job
that disturbs the line least. That would be a new weight with no source, and
when a PM job is done is already governed by the light-band gate (ADR-011,
ADR-109).

## Consequences

- `comparison.csv` and every figure derived from it are unchanged; the
  comparison has no scheduled work.
- `docs/results/gate-trace.md` and `docs/results/worked-example.md` are
  regenerated.
- Tests in `tests/dispatch/test_gate_and_score.py::TestAWaitingPmJobCostsNothing`
  pin the term, the tie and the solver's rate.

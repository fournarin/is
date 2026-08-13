# ADR-042: What the rule engine remembers, and what it has to be told

## Context

ADR-023 settled the `Finding` lifecycle in unusual detail - the suppression key,
the cooldown, the supersession, and the rule that a higher-severity alarm is
never suppressed. It settled none of the mechanics, and three of them decide
whether the rule engine can be tested at all.

**A rule fires on sustained excess, not on a sample.** `config/rules.yaml` gives
`for_seconds` per rule, and the corpus rule for motor temperature is two minutes.
Something has to remember that the last two minutes were all above the threshold,
and where that memory lives is a decision with a failure mode either way: in
memory it is lost when the worker restarts, and in the database it is a write per
sample per rule - at one sample a minute per channel, on a plant's worth of
machines, that is a table growing faster than the signals it summarises.

**Suppression during repair needs to know what is under repair** (ADR-023 §4),
which is a fact about work orders - layer 4. Layer 1 asking layer 4 a question
inside the evaluation would put a database read inside the only part of this
system that could otherwise be a pure function, and it is the part that most
needs to be exhaustively testable: the safety case in ADR-023 §5 is a rule firing
*while* the machine it belongs to is being repaired.

**And "higher severity always passes" needs an ordering.** `Severity.rank`
exists for the load gate (ADR-011); this is its second reader.

## Decision

### 1. The sustained-excess window lives in memory, in the loop, and a restart forgets it

Keyed `(machine_id, rule_id)`, holding only what the rule needs: when the excess
started and how many samples it has seen.

**A restart therefore restarts the clock on a rule mid-sustain.** For a
two-minute rule on a machine that is genuinely overheating, the cost is that the
Finding is raised up to two minutes later than it would have been, once, after a
deploy. The alternative costs a write per sample per rule for ever, to make an
event that was going to happen anyway happen slightly sooner.

Stated rather than hidden, because it is the kind of thing that looks like a bug
when somebody notices it in a log two months from now.

### 2. Everything else the engine needs is passed in, not looked up

`evaluate()` takes the signals, the rules, the open Findings for those keys, the
set of machines under repair, and the clock's `now`. It returns what should
happen. It reads nothing.

That is the same rule `dispatch()` lives under (invariant 10) and it is here for
a stronger reason: **the case that has to be exhaustively tested is the safety
case** - an interlock failing while the motor beside it is being repaired
(ADR-023 §5). A function that fetched its own state could only be tested by
constructing that world in a database; one that is handed it can be tested in a
line, and so it can be tested in every combination.

It also keeps `triggers/` from importing `work/`. The loop joins them, which is
the same shape as `Ingest.withdraw` not knowing the playbook table exists.

### 3. Suppression is by rule, never by machine

Directly from ADR-023 §4 and §5, restated here because this is where it becomes
code: a machine under repair suppresses **the rule that produced the repair**,
and any rule of higher severity fires anyway.

Blanket suppression during repair is how somebody gets hurt: a technician is
inside the machine and the interlock alarm is swallowed because "this machine is
being repaired". The comparison is on `Severity.rank` and the test for it names
that scenario.

### 4. A repeat firing updates the record; the update is one statement

`occurrence_count = occurrence_count + 1` and `last_seen_at = now` in a single
`UPDATE ... WHERE machine_id = %s AND rule_id = %s AND status IN ('open',
'acknowledged')`. Not read-then-write: two evaluations racing on one machine
would each read the same count and write it back, and the number that tells an
engineer a threshold is too sensitive would be the number of workers rather than
the number of firings.

### 5. `evidence` carries the numbers the reason will be built from

The value that fired it, the threshold, the comparison, and how long the excess
has held. `work/` turns those into the sentence on the ticket (ADR-041), and
nothing downstream has to re-derive them from a signal stream that has moved on.

## Reasons

**The memory decision is a trade between a rare, bounded cost and a permanent
one.** Every other arrangement of this - a durable window, an event log, a
materialised view - buys back at most two minutes of latency after a restart.

**The purity decision is about what can be proved.** ADR-023's most important
paragraph is the one about suppression during repair, and a rule engine that
reaches for its own state can only be tested against a database fixture. The
combinations that matter - open, acknowledged, resolved-within-cooldown, under
repair, higher severity - are a handful of lines each when the state is an
argument.

## Consequences

- **The trigger loop is stateful and the evaluation is not**, so the loop is the
  only thing that needs restarting carefully and the part with the safety rules
  in it can be tested exhaustively.
- **A Finding needs a reference**, from a sequence, for the same reason a work
  order does: the alternative is a key built from a machine and a time.
- **Nothing here decides when the loop runs.** The dispatch tick is five minutes
  (design.md 6.2) and the trigger loop must be faster than the shortest
  `for_seconds` in the rules, but the number belongs with the loop, in the slice
  that builds it.
- **Prediction is not in this record.** Trend extrapolation produces Findings
  through the same lifecycle (ADR-020), and what it takes to fit a trend and
  measure its error is its own decision.

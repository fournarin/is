# ADR-067: What a false alarm may propose about a threshold, and what it may not

## Context

ADR-066 built Loop 1 and, on the way, started counting the one signal Loop 2
needs: `no_problem_found`, per rule and per symptom. This record is Loop 2. A
rule that keeps sending somebody to a machine that turns out to be fine is a rule
whose threshold is too tight, and the closed orders are the only place that has
ever been written down.

ADR-022 defines the loop's shape and one prohibition: a loop must never propose
that a safety-linked threshold be loosened, however many false alarms it
produces. What ADR-022 does not settle is what the proposal is a proposal *of*.
Four things had to be decided before any arithmetic could be written.

1. **What number moves?** A rule has two ways to fire less - a looser threshold
   and a longer `for_seconds` - and the evidence supports one of them and not the
   other.
2. **What is a firing?** ADR-023 makes one Finding stand for an unbroken run of
   breaching samples. Counting the samples would be counting something else
   entirely.
3. **How is the new number derived?** A percentage of the old one is arithmetic
   that would run on any input and mean nothing.
4. **What does this evidence structurally fail to say?** This is the important
   one, and it is the reason the record is longer than the code.

## Decision

### 1. The threshold, not `for_seconds`

The evidence is a set of Findings, each carrying the reading the rule fired on
(`evidence.value`, ADR-042 §5). It carries no readings from the samples either
side, because ADR-042 §1 deliberately keeps the debounce window in memory and
writes nothing per sample.

So the recorded evidence can say what a different threshold would have done at
the moment of firing, and can say nothing at all about what a different
`for_seconds` would have done - that question needs the samples, and the samples
are gone. A loop proposing a duration it has no observations of would be
inventing a number, which is the defect this project treats as equal to an
unapproved playbook.

### 2. One Finding is one observation. Occurrence counts are not firings

ADR-023's suppression key means an oscillating sensor produces one Finding with
`occurrence_count` in the dozens, not dozens of Findings. Weighting by
`occurrence_count` would let a single flapping sensor supply an entire evidence
set on its own, and the resulting proposal would describe that one sensor's
morning while reading as though forty jobs supported it.

The unit of evidence is therefore **one closed work order**, joined back to the
Finding for the rule and the reading. It is the same unit ADR-066 counts false
alarms in, so the two loops cannot disagree about how many there were.

Predicted Findings (`<rule_id>/trend`, ADR-043 §4) are excluded and counted
separately. A forecast that came to nothing is evidence about the trend fit, not
about the threshold - the reading it carries is a slope, not a value - and
charging it to the threshold would move a number for a mistake made somewhere
else.

### 3. The proposal is a separating threshold, and it is bounded

Not a percentage: the proposed value is the tightest threshold that would still
have fired on **every** closed order where a technician found something, chosen
so that it excludes as many false alarms as the evidence allows.

For a rule that fires `above` its threshold, with `mildest_fault` the lowest
reading behind an order that found a fault:

- consider only false alarms that read **below** `mildest_fault` - the ones a
  higher threshold could have excluded without losing a real one;
- the proposal is the **highest** of those readings. A rule fires strictly above
  its threshold and never at it (`triggers.domain.breaches`), so a threshold set
  to that reading excludes it and everything below it;
- `below` rules are the mirror image.

This construction has a property a percentage does not: **it cannot silence a
confirmed fault**, and it says so on the proposal by listing the orders it still
fires on by reference. Where no such value exists - every false alarm read
further out than the mildest real fault - there is no separating threshold, and
that is reported rather than approximated. Two populations that overlap are two
populations a threshold cannot tell apart, and the honest answer is that this
rule needs another condition rather than a looser one (ADR-022 reason 2).

The move is then bounded by `max_change_ratio` of the current threshold's
magnitude, as a cap on the proposal in exactly the sense ADR-066 §1 established.
A capped proposal reports what the evidence separated at, so a reviewer sees that
the loop wanted to move further than one cycle allows.

### 4. Two constants, both recorded decisions, and neither is 11.1's

In `config/policy.yaml` under `thresholds:`, never in code:

| | value | provenance |
|---|---|---|
| `min_observations` | 10 | this record |
| `max_change_ratio` | 0.10 | this record, enforced by the config schema |

**`min_observations` is 10 and not ADR-066's 5.** The floor there guards a
median, and five is the smallest count leaving two observations either side of
the middle. Nothing about that argument transfers, because this number is not a
middle: a separating threshold is decided by exactly two observations - the
highest excluded false alarm and the mildest fault above it - and every other
order in the set only says the boundary is not somewhere else. A floor here buys
something different: confidence that the rule has been seen doing both of the
things it does, often enough that the mildest fault in the set is plausibly near
the mildest fault the rule catches.

Ten is twice five, deliberately, and the reason is which of the two loops can
afford to be wrong. Loop 1's error announces itself - the estimate is off, the
shift is priced wrong, the next batch of durations says so. Loop 2's error is a
fault that no longer fires, and nothing in this system will ever report it. When
one error is self-correcting and the other is silent, the silent one gets the
higher floor. That is an argument, not a measurement, and this record is its
source.

**`max_change_ratio` is 0.10, half of ADR-022's bound for durations**, for the
same asymmetry and for one more reason. `rules.yaml` says the real thresholds
come from the machine manuals, so a proposal to move one is a proposal to
disagree with the manufacturer. Ten percent is about as far as an argument built
from ten work orders can carry against a document written by the people who built
the machine; further than that, the proposal to make is not a new number but a
conversation with the manufacturer, and the reviewer is the person who can have
it. The schema refuses a larger value at boot, so raising it is a new record
rather than an edit to `policy.yaml`.

### 5. Silence and "no change needed" are different answers

Loop 1 returns nothing when it has nothing to say. Loop 2 always answers, because
its refusals are the interesting half and each of them means something a reviewer
would act on differently:

| | means |
|---|---|
| `safety_critical` | ADR-022 forbids it. No count changes this |
| `below_floor` | not enough closed work behind this rule yet |
| `no_false_alarms` | the evidence says this threshold is fine - not that there is none |
| `no_confirmed_fault` | every order behind this rule found nothing. A threshold above all of them silences the rule, which is a decision to stop watching a machine and not one a loop may propose |
| `no_separating_threshold` | the false alarms and the real faults overlap |
| `cap_excludes_nothing` | the evidence separates, and one cycle may not move far enough to reach it |

### 6. The evidence is one-sided, and every proposal carries that where it is read

`no_problem_found` counts the times the rule was wrong to fire. **Nothing in this
system counts the times a higher threshold would have failed to fire at all.**
There is no record of a fault that was never alerted; if there were, the fault
would have been alerted.

So the evidence available to this loop can only ever say "too tight" and can
never say "too loose", and a loop that runs every cycle on evidence with one
sign walks the thresholds towards silence one approval at a time. The proposal
therefore carries the limitation as a field rather than leaving it to this
document: it is read by somebody looking at a number, not by somebody reading
ADRs, and a caveat that lives only here is a caveat that is not present at the
moment it matters.

The limitation names a second gap in the same sentence. The reading recorded is
the one the rule fired on, not the peak of the excursion, so "would not have
fired" is properly "would not have fired *then*" - a signal still climbing might
have crossed a higher threshold a minute later. Both belong in front of the
reviewer.

This is what makes the human approval ADR-022 requires load-bearing here in a way
it is not for durations. The person approving is the only thing in the loop that
knows what the loop cannot see.

### 7. Where it lives

`src/pdm/work/thresholds.py`, beside `estimates.py` and for the same reason: the
outcome lives on the work order, and a layer-1 module reading layer 2's table to
find out what happened to its own Findings is the coupling ADR-030 spends the
`machine_id` copy to avoid (ADR-066 §3). It is pure and on the no-I/O list in
`.importlinter` - a version of it that could open a connection could also be a
version that writes the threshold it just proposed, and that threshold is one
layer 1 fires on.

The rule's own facts - its threshold, its comparison, its safety flag - are
arguments rather than a `RuleConfig` import, so the arithmetic is tested against
rules written out by hand and `work/` keeps its distance from the rules file.

`work.repo.firings_behind_rules` groups the evidence per rule and reports, per
rule, the Findings that carried no usable reading. **This slice adds no endpoint,
no screen and no cadence**, on the same argument as ADR-050 and ADR-066 §6:
composing the groups with the rules that name each threshold belongs with
whatever asks the question.

## Consequences

- **Loop 2 exists as a mechanism and turns nowhere.** Nothing schedules it and
  nothing displays it, so no threshold can move until a person builds the screen
  that shows a proposal and a way to approve one. That ordering is deliberate:
  the mechanism is the cheap half here too.
- **A rule with no confirmed fault behind it can never produce a proposal**,
  however many false alarms it accumulates. That is the intended behaviour and it
  is also the case where the loop is least useful, because a rule firing on
  nothing but nothing is exactly the rule somebody wants to loosen. The answer
  the loop gives instead is that the rule has never been shown catching anything,
  which is a better question to put to an engineer than a number.
- **`min_observations` is the first number to revisit**, and unlike ADR-066's
  there is a path to replacing it with a measurement: ADR-020's synthetic source
  knows the true failure time, so a scenario can be run twice - once at the rule's
  threshold, once at a proposal - and the failures the proposal misses can be
  counted. That measurement is the missing half of this loop's evidence, and it
  can be made without the plant. It is not in this slice.
- **The proposal is addressed to an engineer, not to the config file.** Where a
  threshold came from a manual, an approved proposal is a documented disagreement
  with that manual, and the person approving is accepting it in that form.
- ADR-022's prohibition on safety-linked rules is now enforced by code rather
  than by intention, and `safety_critical` in `rules.yaml` is the flag it reads.

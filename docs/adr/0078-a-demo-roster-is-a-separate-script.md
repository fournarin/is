# ADR-078: A demo roster is its own script, and what it is allowed to invent

Builds [ADR-024](0024-roles-and-approval-authority.md), which forbids a demo with
authentication turned off and therefore made `scripts/seed_demo.py` an ordinary
operation rather than a fixture. Extends the rule
[ADR-032](0032-synthetic-signals-are-generated-from-a-named-scenario.md) and
[ADR-044](0044-what-drives-the-trigger-loop.md) §5 apply to invented signals -
that invented data announces itself - to invented **people**. Read beside
[ADR-011](0011-load-ratio-switches-dispatch-behaviour.md) and
[ADR-071](0071-a-round-proposes-and-a-person-decides.md), which are the two
things a demo cannot show without one.

## Context

`docs/demo.md` records the gap in its own words: "Dispatch needs a roster - a
technician record with skills, and a shift assignment - and `seed_demo.py`
deliberately creates neither... A demo roster is a separate thing that does not
exist yet."

What that costs is the middle of the system. With nobody to place work on,
`dispatch()` ranks a queue and assigns none of it, so the shift lead's screen has
no proposal to confirm and the technician's screen says there is no work - on a
plant that has just raised five Findings. Layers 3 and 4, the load gate, the
five-term score and the confirmation record are all invisible.

A census of the stack that had been running here for three days makes the shape
of the gap plain: `technician` held one row and `shift_assignment` one, both left
behind by `web/check-the-technicians-screen.py` seeding its own world. Not a
roster anybody put there, and not one that survives the next check.

## Decision

### 1. A second script, `scripts/seed_demo_roster.py`, and not a flag on the first

The two scripts differ in what they are allowed to assert.

`seed_demo.py` writes two kinds of row and both are defensible on the plant's own
machine. **Accounts** are a real operation: ADR-024 refused a mode with
authentication off, so a demo needs real accounts with real roles, and creating
them is administration rather than fiction. **Manuals** are the synthetic corpus,
every page of which declares itself invented (ADR-033), and a document is
evidence a person reads with the real manual open beside it - the kind of
invention that corrects itself the moment somebody looks.

A technician row is neither. It is a **person**, and work is placed on it: the
load gate computes capacity from it, the score ranks against it, a delivery is
addressed to it, and a real technician's screen can end up showing a job handed
over by somebody who does not exist. It is also the one table here the plant
will certainly replace - the roster arrives with the same export ADR-070 and
ADR-076 §5 already ask for. Putting invented people in the operator's own script
would seed the table that looks most authoritative with the rows least able to
declare themselves.

So the roster gets its own script, which says what it is every time it runs, in
the tone `worker-runtime` uses about `SIGNAL_SOURCE=synthetic`.

### 2. Three technicians, not one

One technician makes the load gate a straight line: every job fits or does not,
and `load_ratio` moves in one step per job. Three is the smallest roster where
ADR-011's three bands are reachable inside one shift at the synthetic scenario's
arrival rate, so the behaviour the advisor described most concretely - hold the
non-urgent work when the shift is heavy, release it when it is light - is
something a demo can actually make happen rather than describe.

It is also the roster `docs/results/comparison.md` measured against. A demo and a
measurement that disagree about the shape of a shift are two claims about
different plants.

Each one gets an account, because work placed on somebody nobody can sign in as
is work the demo cannot open.

### 3. Between the three of them they hold every skill in `plant.yaml`

Not "the skill the demo needs", because that is not knowable in advance: a
playbook's `required_skill` is chosen when the draft is assembled, from the same
config list, and the demo's path through the corpus can change with a manual.

So the roster covers all four, and the script refuses to write anything if it
names a skill `plant.yaml` does not have - checked before the first insert,
because a roster that is half right is worse than none. A round that finds
nobody with a required skill correctly leaves the job unassigned with a reason,
and that correct answer is indistinguishable, on a demo screen, from a bug.

### 4. Half a shift is available for repair work, and that is an assumption

`available_minutes` is **240 of a 480-minute shift**. Provenance: this record - a
decision, not a measurement. The argument is that a technician also walks the
line, runs PM rounds, hands over and eats, and that treating the whole shift as
repair capacity would make `load_ratio` read low and the gate release more work
than there are hours for.

The script prints it as an assumption every time it runs, and this record is
where it changes. `docs/results/comparison.md` used the same 240, so the demo
does not quietly contradict the measurement standing beside it.

### 5. The shift is resolved at the moment the script runs

Through `contracts.shift_at()`, which every other reader of this question already
uses. A demo at 09:00 files the roster under the morning shift; one at 23:00
files it under the night shift, against yesterday's date, because that is how a
roster is written (ADR-049 §3). A hardcoded shift id or date is a demo that works
on the afternoon it was written and fails silently at every other hour - and
"fails silently" here means an empty screen with no error on it.

### 6. It refuses to run where the demo accounts are not there

The one guard available that rests on a fact rather than on a hope. If
`seed_demo.py`'s four accounts are absent, this is not a demo database, and the
script exits without writing. It cannot ask "is this the plant's production
system?" - nothing in the schema answers that - but it can ask whether the world
it is meant to extend is present, and refuse when it is not.

## Consequences

- `scripts/rehearse.py` runs it after the re-seed step, never before: the screen
  checks truncate `account` and `technician` on their way through, so a roster
  seeded earlier would be deleted by the check that runs next.
- The demo can, for the first time, show a round proposing work, a shift lead
  confirming it, and a technician opening it - the three things ADR-071 exists
  for.
- One more row in the request to the maintenance department: the real roster,
  beside the machine register and the maintenance history. Same request, same
  team.
- A person who runs this against a plant database gets three technicians who do
  not exist. The name says demo, the output says it, and §6 refuses where the
  demo accounts are missing. That is as far as this goes, and it is stated
  rather than assumed away.

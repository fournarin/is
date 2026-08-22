# ADR-060: How the authoring queue is ordered, and what counts as a gap

## Context

`design.md` 4 says that a symptom arriving with no playbook is queued for
authoring **ordered by how often it is seen**, so the system works out for itself
which playbook is worth writing next. The mechanism has existed for several
slices - Findings are raised, proposals are filed, the cascade flags what a
replaced manual invalidated - and until slice 9.3 there was nowhere to look at
any of it. An engineer choosing what to write next was choosing from memory, and
that choice is what decides whether the store ever covers the long tail.

Writing the endpoint forced two questions the earlier records leave open.

**What is "how often it is seen"?** The finding table can answer it two ways. One
Finding is one event; `occurrence_count` on it is how many times the rule fired
while that event was open (ADR-023). A conveyor motor sitting over its threshold
all morning is one Finding with a count in the hundreds. A bearing symptom
arriving separately on three machines is three Findings with a count of one each.

**What counts as having an answer?** The playbook table holds `approved` and
`needs_review` rows and no drafts, because drafts live in the proposal table
(ADR-038). So a pair can be in three states, not two: served, served with a
warning, or nothing at all - and a pair with four pending drafts and no approved
row is in the third.

## Decision

### 1. The ranking counts Findings, not firings

`GET /overview/gaps` orders the first list by how many Findings carried the
symptom, whatever became of them. The summed `occurrence_count` is returned
beside it, and ranks only as a tie-break.

### 2. Resolved, expired and superseded Findings still count

No status filter. The question is which playbook is worth writing, and a symptom
seen six times and cleared six times has been seen six times.

### 3. A symptom has an answer if the playbook table has a row for its pair

Approved or `needs_review`, because both are served (ADR-018). A pair whose only
playbook is a draft appears in the gap list however many drafts are pending; the
number waiting is reported on the row so the screen can say "already queued"
rather than offering to queue it again.

### 4. `needs_review` playbooks are a list of their own

They are being served right now, with a warning. That is a debt, not a gap, and
mixing the two would make the first list unreadable in the one direction that
matters: the symptoms nobody can be given anything for.

### 5. Findings on machines the layout no longer holds are named, not dropped

Their symptoms cannot be filed under a machine model, so they cannot be drafted
for at all. They are reported as a list of machine ids, for the reason ADR-048
gives one screen up: a count that quietly discarded them would say the store
covers work nobody can even ask for.

## Reasons

**Ranking on firings would hand the queue to whichever channel is noisiest.** One
stuck sensor produces a count no genuine symptom can reach, and it would sit at
the top of the authoring queue until somebody fixed the sensor. Worse, it is
self-reinforcing: the same suppression that keeps a stuck channel from flooding
dispatch (ADR-023) is what concentrates its entire morning into a single row's
`occurrence_count`, so the mechanism that protects the scheduler would be the one
distorting the queue.

**Counting events matches what an engineer is deciding.** "This symptom has
arrived eleven separate times, on four machines" is an argument for writing a
playbook. "This symptom fired four hundred times" is an argument for looking at a
sensor, and is a different piece of work that this list should not disguise.

**Both numbers are shown because the tie-break is real.** Two symptoms seen three
times each are not equally urgent if one of them fired twice and the other four
hundred times, and a reviewer can see that without the ranking being decided by
it.

**Serving with a warning is still serving.** ADR-018 argues that a technician
with an out-of-date procedure is better off than one with none, while they can
tell which they have. Counting those rows as gaps would contradict the record
that put them in front of a technician in the first place.

## Consequences

- The first list is stable against a noisy channel and moves only when a symptom
  genuinely recurs.
- A symptom drafted repeatedly and never approved stays visible, which is the
  case ADR-038 section 6 wanted answerable: *why does this symptom still have no
  playbook, when the queue shows somebody looked at it three times*.
- Every figure on the response is a count of rows that already exist - Findings,
  proposals, flagged playbooks. There is no aggregate table and no scheduled
  recomputation, so the endpoint cannot disagree with the tables behind it
  (ADR-050).
- The three lists are bounded, and each reports its full total beside the rows
  returned, so a truncated screen never reads as an empty backlog.
- If the plant ever wants "how often" to mean firings - a plausible request from
  somebody looking at a maintenance load rather than an authoring queue - it is a
  new record, not a flag on this one.

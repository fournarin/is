# ADR-080: A draft already waiting for review answers the second ask

Extends [ADR-040](0040-what-happens-when-somebody-asks-twice.md), which
made `POST /playbooks/drafts` return the first job's id when the same pair is
asked for twice, and applies invariant 6's argument -
[ADR-038](0038-the-review-queue-is-a-table-and-the-served-table-holds-no-drafts.md)'s *checked
at the endpoint rather than by hiding a button* - to the stage after it.

## Context

The gaps panel grew a draft-request button, and hides it on a row whose
`proposals_waiting` is not zero: once a draft for that symptom is waiting for a
decision, there is nothing useful to ask for.

The endpoint did not know that. `request_draft` deduplicated against a **job**
still queued or running, which covers the minute between the press and the
proposal being filed, and nothing at all afterwards. A second ask for a pair
whose draft was already sitting in the review queue enqueued another drafting
job and eventually filed a second proposal beside the first - two rows for one
symptom, in a queue that merges nothing, at the cost of another pass on the one
GPU.

Reaching it took no ingenuity. The route handler's own docstring records that
before the button existed, `/docs` and curl were the only ways to call this
endpoint; they still are.

## Decision

`request_draft` checks for a proposal already awaiting a decision on the pair,
and when there is one, returns it instead of queueing anything:

```json
{ "proposal": 41, "symptom_code": "SYM-014", "awaiting_review": true }
```

**202, not 409.** ADR-040 refused a conflict for the repeated ask on the grounds
that it "would teach people to press again to find out", and the reasoning does
not change because the draft has arrived rather than being on its way. The
answer is the same shape of answer: not an error, and it says which of the three
things happened - queued now, queued already, or waiting for you in review.

The screen keeps its hidden button. The two are not redundant: hiding it is what
stops a person pressing something with no effect, and the check at the endpoint
is what makes the rule true for callers who never saw a screen.

`playbooks.repo.awaiting_review` is a targeted query rather than a filter over
`pending_by_pair`, which aggregates the whole queue to answer the same question
for every pair - what the overview needs and what this would be loading a queue
to read one row of.

## Consequences

- A caller that wants a fresh draft for a pair already in review has to decide
  the waiting one first - approve, send back, or dismiss it. Sending back
  already enqueues a redraft (ADR-038 §6), so the path exists and this record
  does not add one.
- `already=1` in the overview's query string becomes `already=queued` alongside
  a new `already=review`, because the screen now has three outcomes to report
  rather than two.
- The gap this closes was found by review rather than by anything failing: the
  button hides itself, so the duplicate proposal only ever appeared through an
  entry point nobody was watching. It is the second time invariant 6's argument
  has had to be made about a rule that looked enforced because a screen enforced
  it.

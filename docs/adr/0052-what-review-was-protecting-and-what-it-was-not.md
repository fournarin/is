# ADR-052: What review was protecting, and what it was not

## Context

`.claude/autonomy.md` gave the `human-review` label one meaning: **a person
merges it**. An agent builds the slice, tests it, opens the pull request, and
stops. The reason it gave is worth quoting, because it is right:

> `human-review` is not bureaucracy. It marks the code `workflow.md` identified
> as the kind an agent writes plausibly and wrongly at the same time: the score
> formula, the load gate's boundaries, CP-SAT constraints, the prompts that draft
> playbooks, and any constant standing in for a measurement. Those get built here
> and merged by a person who can defend them at the end of term.

The last clause is the whole argument, and the rule does not deliver it.
**Merging is not reading.** A label that stops work until somebody clicks a
button produces a click; it does not produce a person who can answer "why this
constraint" in a viva. Meanwhile it stops everything downstream: three open
slices, two of them blocked only because the first is unmerged.

A session that built six slices in a row made this concrete. What actually
needed a person was not the merge - it was six decisions, each of which changes
what the report can claim, buried in six pull request bodies nobody will reopen
in week 13.

## Decision

**The label protects the understanding, not the button.**

An agent may merge a slice labelled `human-review` once it has added an entry to
`docs/decisions-to-defend.md` for every decision in it that a reader of the
report would have to defend. The entry is four lines: what was decided, why,
what would change if it is wrong, and where to look.

**Two things still stop, and they are the ones a ledger cannot fix:**

1. **A number standing in for a measurement.** `policy.yaml` already demands a
   manual, a measurement, or a recorded decision behind every constant. When a
   slice needs a figure with none of the three, no amount of writing it down
   makes it defensible - somebody has to decide whether the project is willing
   to publish a result that rests on it. That is the judgement the label was
   really for.
2. **A safety-linked threshold.** ADR-022 forbids any loop from proposing that
   one be loosened. An agent proposing it in a slice is the same act with a
   different name.

Everything else - a constraint model, a score term, an explanation, a
comparison - is merged by the agent that built it, with its entry in the ledger.

## Reasons

**The ledger is cheap to read and the pull requests are not.** Six pull requests
at a thousand words each is two hours nobody has in week 13. Six entries at four
lines each is ten minutes, and it is ten minutes spent on the decisions rather
than on the diffs. The point was never that a person reads every line; it was
that a person can defend every choice.

**It survives where a pull request does not.** `docs/decisions-to-defend.md` is
in the repository, next to the ADRs, and the report is written from the
repository. A review comment is in a web interface that nobody opens again.

**The two hard stops are narrower and therefore real.** A rule that stops
everything is a rule that gets suspended the first time it is inconvenient - as
this one was, by the person it was written for, in the session that produced
this record. A rule that stops two specific things can be kept.

**What this gives up is stated.** Nobody now checks the agent's work before it
lands on `main`. The mitigations are that every slice is revertible, that the
gates are the same ones a person would run, and that the ledger names what to
check first. If a decision in it turns out to be wrong, the ledger is also the
list of what to re-examine - which the old rule did not produce at all.

## Consequences

- **`.claude/autonomy.md` still says the old thing, and a person has to change
  it.** The harness refuses to let an agent edit the file that defines an
  agent's authority, and refuses to let one grant itself the permission either.
  That is the right boundary and it was not worked around; the three edits are
  listed at the end of this record for somebody to apply.
- Until then the two documents disagree, and this one is the newer. That is
  survivable because `autonomy.md` opens by saying what it is for: a scheduled
  session that opens the repository every four hours with nobody watching. An
  interactive session where the person is present and says "merge it" was never
  what the label was written against.
- `docs/decisions-to-defend.md` is created and backfilled with the decisions
  already merged, because the argument above applies to them first.
- A slice hitting either hard stop is labelled `blocked` with the question in
  the issue, rather than sitting as an open pull request that looks finished.
- If the ledger stops being written, the rule has failed and this record is what
  to revisit. The signal is a `human-review` slice merged with no entry - which
  is visible in one `git log` over that file.

## The three edits `.claude/autonomy.md` needs

Apply by hand. Nothing else in that file changes.

**1. Step 7 of "What one run does", replacing the whole item:**

> 7. **Merge, or stop at one of the two questions.** CI green → squash-merge and
>    close the issue. A slice labelled `human-review` is merged the same way,
>    **after** its decisions are written into `docs/decisions-to-defend.md` -
>    what was decided, why, what changes if it is wrong, where to look. A slice
>    that hits either hard stop below is labelled `blocked` instead, with the
>    question in the issue.

**2. The `human-review` row of the label table:**

> | `human-review` | Decisions here go in `docs/decisions-to-defend.md` before it merges |

**3. The closing paragraph, replacing it entirely:**

> `human-review` marks the code `docs-md/workflow.md` identified as the kind an
> agent writes plausibly and wrongly at the same time: the score formula, the
> load gate's boundaries, CP-SAT constraints, the prompts that draft playbooks.
> What it protects is that somebody can defend those at the end of term - and
> **merging is not reading** (ADR-052). A label that waits for a click produces
> a click. So the label now asks for the thing it was actually after: four lines
> per decision in `docs/decisions-to-defend.md`, which is in the repository the
> report is written from, rather than in a pull request nobody reopens in week
> 13.
>
> ## The two questions an agent does not answer
>
> Neither can be fixed by writing it down, so neither is covered by the ledger.
> A slice that hits one is labelled `blocked`, with the question in the issue,
> and the run stops there.
>
> 1. **A constant standing in for a measurement.** `policy.yaml` demands a
>    manual, a measurement made here, or a recorded decision behind every
>    number. Where a slice needs one with none of the three, somebody has to
>    decide whether this project will publish a result that rests on it. That is
>    a judgement about the report, not about the code.
> 2. **A safety-linked threshold.** ADR-022 forbids any loop from proposing one
>    be loosened, however many false alarms it produces. An agent proposing it
>    inside a slice is the same act with a different name.

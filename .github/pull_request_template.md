<!--
One slice, one branch, one PR. This template exists because a PR in a solo
project is not for a reviewer: it is the one place the whole diff is seen at
once before it reaches main. Sections left as prompts are sections that were
skipped, and the two easiest to skip - what was deliberately not done, and how
to get back - are the two that cannot be reconstructed afterwards.
-->

## What this slice finishes

<!-- The definition of "done" written before the work started. Copy it across
     unchanged; rewriting it here to match what was built defeats the point. -->

## Changes, file by file

<!-- Not the diff retold. The per-file reason the diff cannot show: why this
     way, why not the obvious alternative, what was decided there.
     Test each line with one question: reading the diff on its own, would I
     already know this? If yes, leave it out. -->

| File | What | Why this way |
|---|---|---|
|  |  |  |

## ADRs and invariants touched

- **ADR:**
- **Invariants (design.md 12):**
- **If an invariant is touched, the test that enforces it lives in:**

<!-- An invariant with no test is a promise that dissolves within two months.
     If this slice touched one, name the file that would fail without it. -->

## How it was tested

<!-- Commands actually run, with their output pasted. Not the words "it
     passes". If something was not tested, say so and say why - a PR that is
     silent about tests and a PR that says it has none differ in that the
     second one can still be trusted six weeks later. -->

```
```

## Deliberately not in this PR

<!-- Keeps the scope from spreading, and records what is still outstanding.
     Week 13 has to explain why the system lacks certain features; without
     this, all that survives is "we didn't do it". -->

## Reverting

<!-- One line. Some PRs are not cheap to undo - a migration, a config format
     change, anything already read by another service - and that is worth
     knowing before the merge rather than after. -->

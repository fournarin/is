# ADR-085: What the unattended loop may merge, and a check that can stop it

Revisits [ADR-052](0052-what-review-was-protecting-and-what-it-was-not.md) and
narrows it. Written on 2026-09-19, before ADR-083 and ADR-084. Those two numbers
were reserved that day, for slice 16.1 (#90) and for #105, and this record is
the first to follow the rule in its own section 3.

## Context

**ADR-052 and `.claude/autonomy.md` have disagreed since 21 August.** ADR-052
decided that an agent may merge a `human-review` slice once its decisions are
written into `docs/decisions-to-defend.md`, and that only two things still stop
and wait for a person: a number standing in for a measurement, and a
safety-linked threshold. It ended with three edits for `autonomy.md`, "apply by
hand". Nobody applied them. `autonomy.md` kept the older rule, that a PR
labelled `human-review` is left for a person, and the unattended loop followed
`autonomy.md`: #71 and #77, the two improvement-loop slices, were merged by the
owner. The header of `decisions-to-defend.md` still states ADR-052's rule.
There were two documents and two rules, and the rule in force was the one the
records did not describe.

**What happened on 2026-09-19** all concerns what a check is worth:

- A batch of 21 commits was reported green on every gate from another machine.
  `ruff format` failed on the combined tree. The gates had been run on a branch
  that did not contain the failing file.
- `docs/invariants.md` said every enforcement point had been checked against
  the code. For invariants 4 and 13 that was not true, and the page merged to
  `main` in that state.
- The owner merged #104 at 14:44 UTC while a correction to it was being
  prepared. Before pushing, the session read the PR's state, which was
  `MERGED`. The read was printed beside a push that ran regardless, so the
  correction went to a branch that no longer led anywhere. This is the third
  merge to overtake a push, after #87 on 24 August and #98 on 18 September.
- The owner decided that #104, which touched CI, the invariants and three
  production bugs, needed `human-review` and a person to merge it, and merged
  #104 and #106 themselves.
- ADR numbers 083 and 084 were reserved in conversation. `autonomy.md` tells a
  run to take the "next free number in `docs/adr/`", and a reserved number is
  not in `docs/adr/` until it is written. An unattended run would have taken
  083.

Two smaller drifts of the same kind turned up in the same read:

- `autonomy.md`'s gate list is missing three gates CI runs: `check_doc_links`,
  `check_config_is_read` and `check_the_stylesheets_close_every_rule`. A run
  following it can push something CI rejects.
- The routine's prompt says "The backlog runs 9.1 through 11.1", which has been
  wrong for six weeks. The prompt lives on the routine, outside version
  control, which is how it drifted without anybody seeing a diff.

## Decision

1. **An issue labelled `human-review` is not eligible**, with or without
   `slice`. It is for a person or an interactive session to build or decide.
   Slice 16.1 is the example: its two judgements need somebody who can be
   questioned. A slice the loop may build but a person must merge says so in
   its body, and the run labels its PR `human-review`.
2. **A run never merges a PR that changes anything under `.claude/`,
   `.github/workflows/` or `migrations/`, or changes `docs/invariants.md`.** It
   labels the PR `human-review` and leaves it.
3. **An ADR number is taken only after looking in three places.** A run does
   `git fetch`, then takes one above the highest number found in `docs/adr/` on
   `main`, in the branch of any open pull request, and in any open issue that
   says "Reserves ADR-NNN". A number is reserved by writing that phrase on the
   issue.
4. **A state read that can say stop is a condition, not a printout.** Before
   pushing to a PR's branch, the push runs only if the state is `OPEN`:
   `[ "$(gh pr view N --json state --jq .state)" = OPEN ] && git push ...`. The
   same holds for any check whose answer is "do not proceed".
5. **Gates run on the commit being pushed, with a clean tree, and the PR body
   names that commit.** The gate list in `autonomy.md` is the list in
   `.github/workflows/ci.yml`, including the database tier.
6. **What stays from ADR-052:** the ledger. A `human-review` PR has its
   decisions in `docs/decisions-to-defend.md` before a person merges it, because
   that is what lets the person defend it in week 13. The two hard stops still
   make a slice `blocked` with the question on the issue. **What does not stay:**
   the agent's permission to merge a `human-review` slice. ADR-052's three edits
   are declined, and this record is where that is written down.

## Reasons

**Each failure of that day was a claim of checking that did not check.** A green
report from the wrong tree, a page asserting a verification it had not had, and
a state read that printed "stop" and did not stop. An unattended merge of
something nobody has read is one more claim of the same kind. The owner, who is
the only reviewer this project has, chose on the day to be the one who merges
work of that weight.

**The four paths are where a mistake is silent or permanent.**

- `.claude/` changes what the next unattended run is allowed to do. A run
  cannot write there, so a run's PR that touches it means something has already
  gone wrong, and a person should be the one to see it.
- `.github/workflows/` decides which checks run, and whether the loop-alive
  alarm fires at all. A broken workflow looks like a quiet week.
- `migrations/` run against a live database, and ADR-031 does not support
  downgrading them.
- `docs/invariants.md` is the page other documents cite as the enforcement
  record. It was wrong on `main` on the day this was written.

**Section 3 exists because 057 already shows the failure in one direction.** A
number reserved and never written stays a hole for good. A number written twice produces two records with
one name, and every citation of it becomes ambiguous. Looking only at `main`
sees neither a record sitting in an open PR nor a reservation on an issue.

**ADR-052's argument is right, and part of it is kept.** Merging is not reading,
and a label that waits for a click produces a click. That is why the ledger
stays: it is the part of the review that survives into the report. What changes
is who presses the button on the kinds of work named above.

## What this does not do

- **It does not re-enable the routine.** The routine stays off until slice 16.1
  (#90) merges, so that it cannot pick up #90 while a session is building it.
- **It does not enforce section 2 mechanically.** Branch protection with
  required reviews on those paths would, but GitHub does not let a pull
  request's author approve their own, and the owner is the only person here, so
  it would block the owner as well as the loop. The rule is enforced by the
  protocol the loop reads, which is weaker, and this record says so.
- **It does not let a run edit `autonomy.md`.** The protocol is still changed by
  a person, through a pull request that section 2 makes `human-review`.
- **It does not change `blocked`**, or the two hard stops ADR-052 named.
- **It does not move the routine's prompt into the repository.** The prompt
  sentence was corrected on the routine itself on 2026-09-19 to point at the
  open `slice` issues rather than naming slice numbers. It is still one copy
  outside version control, and a later record could put it in the repository if
  it drifts again.

## Consequences

- `.claude/autonomy.md` changes in the same pull request as this record: step
  1 lists eligibility, step 2 carries the four paths, step 5 carries the CI
  gate list and the commit, step 7 loses the issue-label condition, and a new
  rule covers ADR numbers and state reads.
- `docs/decisions-to-defend.md` no longer says an agent may merge a
  `human-review` slice, and its closing section names this record beside
  ADR-052.
- **Slices the loop can finish on its own get narrower.** Any slice with a
  migration now ends at a `human-review` PR, and so will slice 16.1, which adds
  the `pm_task` table. ADR-052's cost comes back for those slices: work behind
  an unmerged PR waits for the owner. The backlog has to keep some slices that
  depend on nothing under review, or the loop idles.
- If the loop merges a PR touching any of the four paths, this rule has failed.
  Neither `git log` nor the merging account shows it: merges are squashed, and
  all 67 merged pull requests to date are recorded under the owner's account,
  whoever pressed the button. What shows it is a merged PR
  that touches one of the four paths and never carried `human-review`.

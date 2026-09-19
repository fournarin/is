# ADR-085: What the unattended loop may merge, and a check that can stop it

Revisits [ADR-052](0052-what-review-was-protecting-and-what-it-was-not.md)
**by the route ADR-052 itself laid down**: it named the evidence that would
mean its rule had failed, and that evidence is now in its ledger's history.
Written on 2026-09-19, before ADR-083 and ADR-084. Those numbers were reserved
that day, for slice 16.1 (#90) and for #105, and this record is the first to
follow the reservation rule in its own section 3.

## Context

### ADR-052's argument still holds

ADR-052 let an agent merge a `human-review` slice once every decision in it had
an entry in `docs/decisions-to-defend.md`. It kept two hard stops: a number
standing in for a measurement, and a safety-linked threshold. Its two reasons
have not been refuted, and this record does not try to refute them:

- **Merging is not reading.** A label that waits for a click produces a click,
  not an understanding.
- **The ledger outlasts a pull request.** It sits in the repository beside the
  records, and the report is written from the repository. A review comment
  lives in a web page nobody reopens in week 13.

### ADR-052's condition for revisiting it has been met

ADR-052's Consequences section says:

> If the ledger stops being written, the rule has failed and this record is
> what to revisit. The signal is a `human-review` slice merged with no entry -
> which is visible in one `git log` over that file.

That `git log`, on `main`, with the longer subjects shortened:

```text
$ git log --format='%ad %h %s' --date=short origin/main -- docs/decisions-to-defend.md
2026-09-19 4066a74 docs: two invariants were cited as enforced, ... (#106)
2026-09-19 43f3ae2 README, the invariants, and what a production read found (#104)
2026-08-23 f4450e1 feat(dispatch): a round proposes, and a person decides (#84)
2026-08-23 096f02d feat(sinks): a second destination, ... (#80)
2026-08-23 7049c48 feat(sinks): layer 4 gets the interface ADR-012 promised (#79)
2026-08-23 f3b9822 feat(work): what the finished jobs say ... (#71)
2026-08-22 e70bfe5 feat(web): the review screen that decides ... (#69)
2026-08-21 d317d51 docs: what review was protecting, and a ledger ... (#47)
```

Nothing was written between `f4450e1` on 23 August and `43f3ae2` on 19
September. In that time:

- nine records reached `main`, ADR-073 through ADR-081;
- four pull requests that needed review merged without an entry. #77 was one;
  issue #75 asked for review in its body. #87, #93 and #97 were labelled
  `human-review`. That is exactly the signal ADR-052 named.

Entries 19 to 30 arrived together in #104, a backfill written on 18 September
by a read of the whole repository.

**All four of those merges were pressed by a person.** `.claude/autonomy.md`
never took up ADR-052's permission, because the three edits ADR-052 listed
"to apply by hand" were never applied. The agent never merged `human-review`
work, and the ledger still went unwritten for four weeks. **The mechanism
failed, not the reasoning.** The ledger depended on somebody remembering a step
at merge time, nothing checked that they had, and nobody ran the `git log`
ADR-052 said to watch.

### What the ledger and the merge button both missed

On 2026-09-19 two defects came out that had passed every gate, and neither the
ledger nor the person who merged caught either:

- **Invariants 4 and 13 were cited as enforced, and are not**
  (`decisions-to-defend.md` entry 31). `docs/invariants.md` claimed each
  enforcement point had been checked against the code, and a person merged it
  in #104 with that claim in it.
- **Neither improvement loop has a runtime path** (entry 32). Loop 1 (#71) was
  merged **by a person, with ledger entries 11 and 12 written at merge time**,
  and nothing in the system calls it. Loop 2 (#77) was merged by a person with
  no entry. The result is the same either way.

**Both were found by someone reading the code again** at the line a document
pointed to, while every gate was green and, for Loop 1, the ledger was
written. That was the only check that worked that day.

### Smaller drifts found in the same read

- A batch was reported green on every gate from a branch that did not contain
  the file that failed `ruff format`.
- #104's state was read as `MERGED` before a push, and the push went ahead,
  because the read was printed rather than tested. It was the third merge to
  overtake a push, after #87 and #98.
- ADR numbers 083 and 084 were reserved in conversation. `autonomy.md` said to
  take "the next free number in `docs/adr/`", so an unattended run would have
  taken 083.
- `autonomy.md`'s gate list was missing three gates CI runs.
- The routine's prompt still said "The backlog runs 9.1 through 11.1". It lives
  on claude.ai, outside version control, so for six weeks there was no diff of
  it for anybody to see.

## Decision

1. **An issue labelled `human-review` is not eligible for the loop**, with or
   without `slice`. A person or an interactive session builds it or decides it.
   A slice the loop may build but a person must merge says so in its body, and
   the run labels its PR `human-review`.
2. **A run never merges a PR that changes anything under `.claude/`,
   `.github/workflows/` or `migrations/`, or changes `docs/invariants.md`.** It
   labels the PR `human-review` and leaves it.
3. **An ADR number is taken only after looking in four places.** A run does `git
   fetch`, then takes one above the highest number found in: `docs/adr/` on
   `main`; the branch of any open pull request; any open issue that says
   "Reserves ADR-NNN"; and the reserved numbers `docs/adr/README.md` lists.
   A reservation goes on the issue, and into the index with the next PR that
   touches it. The index copy is what puts the reservation into version
   control.
4. **A state read that can say stop is a condition, not a printout.** Before
   pushing to a PR's branch, the push runs only if the state is `OPEN`:
   `[ "$(gh pr view N --json state --jq .state)" = OPEN ] && git push ...`.
5. **Gates run on the commit being pushed, with a clean tree, and the PR body
   names that commit.** The gate list in `autonomy.md` is the list in
   `.github/workflows/ci.yml`.
6. **ADR-052's permission to merge `human-review` work lapses, on ADR-052's own
   condition.** The ledger stays, and a `human-review` PR has its entries before
   a person merges it. ADR-052's two hard stops also stay. Its three edits to
   `autonomy.md` are declined.
7. **The routine's prompt is mirrored in `.claude/routine-prompt.md`,** with the
   routine's identity and the steps for changing it. The mirror is a copy and
   says so.

## Reasons

**Why the permission lapses.** ADR-052 made the permission conditional on the
ledger being written, and said what would show that it was not. That has now
been shown, so the condition behind the permission is not met. The reason is
not that an agent is less trustworthy than a person; the four unrecorded merges
were a person's. A later record can restore the permission once the ledger is
written by a mechanism rather than by memory. [#112](https://github.com/fournarin/is/issues/112)
proposes that mechanism: a CI check that a pull request adding a record also
touches the ledger, or says why not.

**What handing the button back does not do, stated so nobody reads it in.** It
does not catch the class of defect found today. A person merged the invariants
page with its false claim, and a person merged Loop 1 with its ledger entries
written, and neither merge noticed anything. A person pressing merge is a
cheaper default while the ledger is not being kept. It is not a way of finding
defects, and this record does not claim it is.

**What does find them is an independent re-read of the code, and that
matters more than who holds the button.** Both findings of 2026-09-19 came from
reading the code again at the line a document cited, not from gates, the
ledger or review. Reading is labour, and a reader can be wrong: the first
check of `docs/invariants.md` was itself a reading, and it missed two rows.
[#108](https://github.com/fournarin/is/issues/108) turns that reading into
something repeatable, with one test per invariant that breaks it on purpose
and requires the mechanism to object. Once those tests exist, "the invariant is
enforced" is something a test run shows rather than something a reader
believes. That is where the effort this record implies should go.

**The four paths in section 2 are where a mistake is silent or permanent.**

- `.claude/` changes what the next unattended run may do. A run cannot write
  there, so a run's PR that touches it means something has already gone wrong.
- `.github/workflows/` decides which checks run, and whether the loop-alive
  alarm fires at all. A broken workflow looks like a quiet week.
- `migrations/` run against a live database, and ADR-031 supports no downgrade.
- `docs/invariants.md` is what other documents cite as the enforcement record.
  It was wrong on `main` on the day this was written.

**Section 3 exists because 057 already shows the failure in one direction.** A
number reserved and never written stays a hole for good. A number written twice
produces two records with one name, and every citation of it becomes ambiguous.
Looking only at `main` misses both a record in an open PR and a reservation
that lives only on an issue.

**Section 7 is the invariants page again.** The fifteen invariants were cited
more than 170 times and defined only in notes `.gitignore` excludes. The
prompt that governs every unattended run was the same kind of thing: it
governed everything and had no history. A mirror does not make the two agree,
but it gives every change a diff and puts the routine's identity somewhere a
cold reader can find it.

## What this does not do

- **It does not re-enable the routine.** The routine stays off until slice 16.1
  (#90) merges, so that it cannot pick up #90 while a session is building it.
- **It does not make the ledger get written.** ADR-052 named the signal of
  failure, and then nothing watched for it. A signal nobody watches is not a
  mechanism. #112 is the mechanism, and it is not built here.
- **It does not make the mirror authoritative, and nothing checks it.** CI has
  no credentials for claude.ai. A run could compare the prompt it was started
  with against the file, and #111 proposes that. Until then the mirror is a
  claim that was true on the day of its last commit.
- **It does not enforce section 2 mechanically.** Branch protection with
  required reviews on those paths would, but GitHub does not let a pull
  request's author approve their own, and the owner is the only person here. It
  would block the owner as well as the loop.
- **It does not let a run edit `autonomy.md`**, and it does not change `blocked`
  or the two hard stops.

## Consequences

- `.claude/autonomy.md` changes in the same pull request: eligibility, the four
  paths, the gate list and the commit, ADR numbers, and state reads.
- `.claude/routine-prompt.md` exists. Its history starts with the prompt as it
  stood before 2026-09-19, so the first diff in it is that day's edit.
- `docs/decisions-to-defend.md` no longer says an agent may merge
  `human-review` work, and its closing section names this record beside
  ADR-052.
- **The slices the loop can finish on its own become fewer.** Any slice with a
  migration ends at a `human-review` PR, and slice 16.1, which adds `pm_task`,
  is one. ADR-052's cost comes back for those slices: work behind an unmerged
  PR waits for the owner. The backlog has to keep slices that depend on nothing
  under review, or the loop idles.
- If the loop merges a PR touching any of the four paths, this rule has failed.
  Neither `git log` nor the merging account would show it: merges are squashed,
  and all 67 merged pull requests to date are recorded under the owner's
  account, whoever pressed the button. What would show it is a merged PR that
  touches one of the four paths and never carried `human-review`.

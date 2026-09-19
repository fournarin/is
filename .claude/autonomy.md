# The unattended loop

A scheduled cloud session opens this repository, does **one slice**, and stops.
Nobody is watching while it runs.

**The schedule is a property of the routine and is not written down here.** It
said "every four hours" for some weeks while the routine ran every two, which is
the kind of number that drifts the moment it is restated in a second place. If
you need to know the interval, read the routine.

Everything here is written for an agent that starts cold. It has this checkout,
a sandbox with the toolchain already installed, and the built-in GitHub tools -
and nothing else: `docs-md/` - the plan, `design.md`, the schedule, the
conversation log with the advisor - **is not in this checkout and never will
be**, because `.gitignore` excludes it on purpose. What survives that gap is
`CLAUDE.md`, `docs/adr/`, [`docs/invariants.md`](../docs/invariants.md), and the
issue being worked from. If a slice cannot be finished without something only
`docs-md/` could answer, that is a reason to stop and say so, not a reason to
guess.

**The invariant table is no longer one of those things.** It used to be in
`design.md` and is now `docs/invariants.md`, so a citation of "invariant 10" is
resolvable from inside this checkout.

Issues, pull requests, labels and merges go through the built-in GitHub tools,
which authenticate through a proxy. `gh` is not necessarily installed; `git`
always is.

## What one run does, in order

1. **Orient.** `git fetch --all --prune`. Read `CLAUDE.md` and this file. Then
   `gh pr list --state open` and `gh issue list --label slice --state open`.

2. **Finish before starting.** An open PR from an earlier run comes first:
   - CI green, no `human-review` label, and it changes nothing under the four
     paths below → squash-merge it, delete the branch.
   - CI red → fixing it *is* this run's slice. A red CI that nobody fixes is how
     a loop like this quietly stops being worth anything.
   - Labelled `human-review` → leave it alone. It is waiting for a person.
   - **It changes anything under `.claude/`, `.github/workflows/` or
     `migrations/`, or changes `docs/invariants.md`** → label it `human-review`
     and leave it, whatever else is true of it. These are where a mistake is
     silent or permanent (ADR-085 §2).

3. **Pick one slice.** The eligible issue with the lowest slice number, skipping
   any whose stated dependency is still open. One slice per run. Never two.

   **An issue labelled `human-review` or `blocked` is not eligible**, whether or
   not it also carries `slice`. `human-review` on an issue means a person or an
   interactive session builds it or decides it, not this loop (ADR-085 §1). If
   an issue wants the loop to build it and a person to merge it, it says so in
   its body, and step 7 labels the PR accordingly.

4. **Write the tests first**, particularly for the invariants the issue names.
   `CLAUDE.md` and the ADRs are the specification; a test that merely agrees with
   the code proves nothing.

5. **Build it**, commit, and then run every gate **on that commit, with a clean
   working tree**, before pushing. A green result from another branch, or from a
   tree with changes not yet committed, says nothing about what is pushed. On
   2026-09-19 a batch was reported green from a branch that did not contain the
   file that failed (ADR-085 §5). This is the list in
   `.github/workflows/ci.yml`; if the two ever differ, CI's list is right and
   this one is stale:

   ```
   git status --porcelain            # must print nothing
   uv run ruff format --check . && uv run ruff check .
   uv run mypy
   uv run lint-imports
   uv run python -m pdm.platform.config config
   uv run python scripts/check_no_wall_clock.py
   uv run python scripts/check_llm_isolation.py
   uv run python scripts/check_no_blob_deletion.py
   uv run python scripts/check_the_stylesheets_close_every_rule.py
   uv run python scripts/check_doc_links.py
   uv run python scripts/check_config_is_read.py
   uv run pytest -m "not db"
   ```

   Tests marked `db` need a real PostgreSQL, and ADR-031 forbids substituting
   SQLite: what most needs testing in the queue - `SKIP LOCKED`, partial indexes,
   CHECK constraints - is exactly what SQLite lacks, so a substitute would pass
   tests the real thing fails. **The sandbox ships PostgreSQL 16.** Start it and
   run them here rather than finding out from CI twenty minutes later:

   ```
   pg_ctlcluster 16 main start || service postgresql start     # not running by default
   su postgres -c "psql -c \"CREATE USER pdm PASSWORD 'ci' SUPERUSER\" \
                        -c 'CREATE DATABASE pdm_test OWNER pdm'"
   export DATABASE_URL=postgresql://pdm:ci@localhost:5432/pdm_test
   uv run alembic upgrade head
   uv run pytest -m db
   ```

   If PostgreSQL genuinely will not start, say so in the PR body and leave
   GitHub Actions as the authority - but never unmark a `db` test to make a run
   look green.

6. **Open the PR** on a `slice/<name>` branch off `main`. English, per
   `CLAUDE.md`: what changed, which ADRs it obeys, which gates were run here
   **and on which commit**, which were left to CI, and what a reviewer should
   look at hardest.

7. **Merge or hand over.** Squash-merge and close the issue only when all of
   these hold: CI is green, the issue's body does not ask for a person to merge,
   the slice needed no constant without a source, and the PR changes nothing
   under the four paths in step 2. Otherwise write its decisions into
   `docs/decisions-to-defend.md`, label the PR `human-review` and leave it open.
   A person merges it (ADR-085 §6).

8. **Leave a trail.** A comment on the issue, three or four lines, Thai, so it
   can be read on a phone: what was done, what is left, what needs a decision.
   Then append one line to `docs/loop-log.md`, on the same branch as the slice
   it describes - never in a pull request of its own.

## Rules that do not bend

- **One slice, one PR, one run.** A diff too large to read is a diff nobody
  reads, and nobody is reading these as they land.
- **Never invent scope.** When the backlog is empty, open one issue titled
  `backlog empty` proposing the next slices with reasons, and stop. Do not
  start work the issue does not describe.
- **Every constant needs a source**: a machine manual, a measurement made here,
  or a decision recorded in an ADR. A number that merely looks reasonable is the
  same defect as an unapproved playbook. If a slice needs a number that has none
  of the three, the PR is `human-review`.
- **Architectural decisions become new ADRs.** Never edit an existing one, and
  reference the record being revisited. **The next free number is not simply
  the next one in `docs/adr/` on `main`.** After `git fetch`, it is one above
  the highest number found in three places: `docs/adr/` on `main`, the branch
  of every open pull request, and every open issue that says "Reserves ADR-NNN"
  (ADR-085 §3). For example:

  ```
  gh pr list --state open --json headRefName --jq '.[].headRefName' \
    | xargs -I{} git ls-tree --name-only origin/{} docs/adr/
  gh issue list --state open --search '"Reserves ADR" in:body'
  ```

  A number written twice becomes two records with one name, and every citation
  of it becomes ambiguous.
- **A check that can say stop must be able to stop you.** Write it as a
  condition the next command depends on, never as output printed beside a
  command that runs anyway. Before pushing to a PR's branch:

  ```
  [ "$(gh pr view N --json state --jq .state)" = OPEN ] && git push ...
  ```

  On 2026-09-19 a session read `MERGED` for #104 and pushed regardless, because
  the read was printed rather than tested, and a correction missed `main` (ADR-085 §4).
  The same goes for a gate, a `git status`, or anything else whose answer can
  be "do not proceed".
- **Nothing under `.claude/` is written by a run.** Those paths are treated as
  sensitive and every write to one - `Edit`, `Write`, or a shell redirect
  alike - stops the run dead on a permission prompt that nobody is awake to
  answer. It has already thrown away finished work more than once. The trail goes
  in `docs/loop-log.md`; the protocol you are reading is changed by a person.
- **Never touch `main` directly**, never force-push, never rewrite history,
  never delete a file the issue did not ask you to delete.
- **The five principles in `CLAUDE.md` outrank the issue.** Runtime stays
  deterministic, every playbook stays traceable, every ticket carries its
  reason, nothing blocks on plant data, and thin evidence is stated rather than
  filled in.

## When the run cannot finish

Usage limits, a context that runs out, an unexpected blocker - all three are
normal and none is a reason to leave nothing behind:

- Push the branch anyway and open a **draft** PR whose body is a checklist of
  what remains, in the order it should be done.
- Comment on the issue with what is blocking, and label it `blocked` if a person
  has to answer something.
- The next run picks up from that PR under step 2. Resuming is the design, not
  the exception.

## Labels

| Label | Meaning |
|---|---|
| `slice` | A unit of work this loop may pick up |
| `human-review` | On an issue: not for this loop; a person or an interactive session builds or decides it. On a PR: a person merges it, and its decisions are in `docs/decisions-to-defend.md` first |
| `blocked` | Waiting on a decision or a dependency. Skip it |
| `loop` | Opened by the loop itself, not by a person |

`human-review` is not bureaucracy. It marks the code `docs-md/workflow.md`
identified as the kind an agent writes plausibly and wrongly at the same time:
the score formula, the load gate's boundaries, CP-SAT constraints, the prompts
that draft playbooks, and any constant standing in for a measurement. Those are
merged by a person who can defend them at the end of term, and when the issue is
labelled rather than the PR, they are built by one too.

ADR-052 would have let this loop merge `human-review` work once its decisions
were written down. The three edits it asked for were never applied here, and
ADR-085 declines them. The ledger ADR-052 created stays, and a `human-review`
PR has its entries in `docs/decisions-to-defend.md` before a person is asked to
merge it.

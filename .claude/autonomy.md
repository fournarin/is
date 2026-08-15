# The unattended loop

A scheduled cloud session opens this repository every four hours, does **one
slice**, and stops. Nobody is watching while it runs.

Everything here is written for an agent that starts cold. It has this checkout,
`gh`, and nothing else: `docs-md/` - the plan, `design.md`, the invariant table,
the conversation log with the advisor - **is not in this checkout and never will
be**, because `.gitignore` excludes it on purpose. What survives that gap is
`CLAUDE.md`, `docs/adr/`, and the issue being worked from. If a slice cannot be
finished without something only `docs-md/` could answer, that is a reason to stop
and say so, not a reason to guess.

## What one run does, in order

1. **Orient.** `git fetch --all --prune`. Read `CLAUDE.md` and this file. Then
   `gh pr list --state open` and `gh issue list --label slice --state open`.

2. **Finish before starting.** An open PR from an earlier run comes first:
   - CI green, no `human-review` label → squash-merge it, delete the branch.
   - CI red → fixing it *is* this run's slice. A red CI that nobody fixes is how
     a loop like this quietly stops being worth anything.
   - Labelled `human-review` → leave it alone. It is waiting for a person.

3. **Pick one slice.** The eligible issue with the lowest slice number, skipping
   any whose stated dependency is still open. One slice per run. Never two.

4. **Write the tests first**, particularly for the invariants the issue names.
   `CLAUDE.md` and the ADRs are the specification; a test that merely agrees with
   the code proves nothing.

5. **Build it**, then run every gate locally before pushing:

   ```
   uv run ruff format --check . && uv run ruff check .
   uv run mypy
   uv run lint-imports
   uv run python -m pdm.platform.config config
   uv run python scripts/check_no_wall_clock.py
   uv run python scripts/check_llm_isolation.py
   uv run python scripts/check_no_blob_deletion.py
   uv run pytest -m "not db"
   ```

   Tests marked `db` need a real PostgreSQL (ADR-031 forbids substituting
   SQLite). If the sandbox has none, say so in the PR body and let GitHub Actions
   be the authority - do not skip a `db` test by unmarking it.

6. **Open the PR** on a `slice/<name>` branch off `main`. English, per
   `CLAUDE.md`: what changed, which ADRs it obeys, which gates were run here and
   which were left to CI, and what a reviewer should look at hardest.

7. **Merge or hand over.** CI green and the issue is not labelled
   `human-review` → squash-merge and close the issue. Otherwise label the PR
   `human-review` and leave it open.

8. **Leave a trail.** A comment on the issue, three or four lines, Thai, so it
   can be read on a phone: what was done, what is left, what needs a decision.
   Then append one line to `.claude/loop-log.md`.

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
- **Architectural decisions become new ADRs.** Never edit an existing one.
  Next free number in `docs/adr/`, and reference the record being revisited.
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
| `human-review` | Merging needs a person. Build it, test it, open the PR, stop |
| `blocked` | Waiting on a decision or a dependency. Skip it |
| `loop` | Opened by the loop itself, not by a person |

`human-review` is not bureaucracy. It marks the code `docs-md/workflow.md`
identified as the kind an agent writes plausibly and wrongly at the same time:
the score formula, the load gate's boundaries, CP-SAT constraints, the prompts
that draft playbooks, and any constant standing in for a measurement. Those get
built here and merged by a person who can defend them at the end of term.

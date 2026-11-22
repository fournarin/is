# How an agent works in this repository

Replaces the unattended-loop protocol of ADR-085 (ADR-090). There is no
scheduled loop any more: an interactive session owns the work and finishes it.

## The rules

1. **Decide and build.** The owner does not approve plans. State the plan in a
   sentence or two in the reply and start. Questions only the advisor can
   answer do not pause work: take the reading that costs least to reverse and
   write the assumption into the ADR.

2. **Priority is what a user or the report sees.** In order: a technician
   getting correct steps; a shift lead releasing work; real data loadable
   without code changes; measured results the report can quote. Documents about
   the repository's own process come last and are usually not worth writing.

3. **Your own worktree, one change, one PR.** Several sessions may be open on
   this repository at once and share one main checkout. Never switch
   branches there. Work in `git worktree add ../is-<topic> -b <branch>
   origin/main`, named `feat/…`, `fix/…`, `docs/…` or `chore/…`, with
   conventional-commit titles.

4. **Tests first for behaviour.** A test that merely agrees with the code proves
   nothing. `CLAUDE.md`, `docs/contracts.md`, `docs/invariants.md` and the ADRs
   are the specification.

5. **Gates on the commit being pushed.** Run the list in `CLAUDE.md` with a
   clean tree, and name the commit hash in the PR body and in the reply. A green
   result from another branch says nothing.

6. **Merge when CI is green.** `gh pr merge <n> --squash --delete-branch`. If
   the permission layer refuses it, leave the PR open, say so in the reply, and
   carry on with work that does not depend on it.

7. **ADRs are for decisions about the system**: behaviour, contracts, data,
   dependencies, and what is in or out of scope. Not for process, labels or
   bookkeeping. The next number is one above the highest in `docs/adr/` on
   `origin/main` and on every open PR branch. Add its row to
   `docs/adr/README.md` in the same commit. Never edit an existing ADR.

8. **Every constant has a source**: a manual page, a measurement in this repo,
   or an ADR. Say which in a comment beside it. A safety-relevant constant
   (torque, lockout, a threshold on a safety-linked rule) with no source is not
   merged. It goes to the owner as a question.

9. **Keep the claims true.** When behaviour changes, update the affected lines
   of `README.md` ("What this cannot do yet"), `docs/demo.md` and
   `docs/invariants.md` in the same PR. A measured figure that moved is
   re-measured by its `scripts/measure_*.py`, never edited by hand.

10. **Never** commit to `main` directly, force-push, rewrite history, or delete
    a file nothing asked you to delete.

## Local environment

- PostgreSQL 16 (homebrew) on `localhost:5432`: `pdm_test` for `pytest -m db`,
  `pdm_web_check` for the screen checks.
- A compose stack may already hold ports 8000 and 3000. For hand-run screen
  checks use `API_PORT=8001` and `PORT=3001`, pass `PDM_API_URL`/`PDM_WEB_URL`,
  and run them in `scripts/rehearse.py::CHECKS` order, sign-in first.

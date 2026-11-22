# The whole system, checked at the last commit of the build

Run on 2026-11-18 on branch `feat/frontend-v2` at **`04321e4`**, with a clean
tree. No Python file changed between `8931cbb` and `04321e4`, and no web file
between `a6c0c95` and `04321e4` (only `docs/` did), so a check that ran on one
of those commits holds for this one; the commit each ran on is named.

The one commit after it, the one that adds this file, adds only result files under `docs/results/`;
the link check and the key tests were re-run on it and pass.

macOS on Apple silicon, Python 3.12.13, Node 24.14.1, PostgreSQL 16 (Homebrew),
Chrome for the browser checks.

## Static gates - all pass (04321e4)

| Gate | Result |
|---|---|
| `ruff format --check .` | 474 files already formatted |
| `ruff check .` | all checks passed |
| `mypy` | no issues in 260 source files |
| `lint-imports` | 14 contracts kept, 0 broken |
| `python -m pdm.platform.config config` | ok: 1 line, 4 stations, 4 machines, 5 rules, 4 skills, 3 shifts |
| `check_no_wall_clock`, `check_llm_isolation`, `check_no_blob_deletion`, `check_the_stylesheets_close_every_rule` | pass |
| `check_doc_links` | 430 relative links, all resolving |
| `check_config_is_read` | 85 configuration fields, all read (1 allowed exception) |

## Tests

| Suite | Commit | Result |
|---|---|---|
| `pytest -m "not db"` | 04321e4 | **1,067 passed**, 17 skipped |
| `pytest -m db`, on a freshly created and migrated database, dropped after | 04321e4 | **696 passed** |
| web: `npm run lint`, `tsc --noEmit` | 04321e4 | pass |
| web: `npm test` (unit) | 04321e4 | **60 of 60** |
| web: `npm run build` | a6c0c95 (same web files) | built |
| web: `npx playwright test` (end-to-end + axe) | a6c0c95 | **7 of 7**, axe 0 violations on 11 screens ([e2e.md](e2e.md)) |

Python tests in all: **1,763 passed** (the report's last figure was 1,701 at
`f1499b8`, 4 October).

The 17 skipped in the `not db` run are database tests not marked `db` that
skip themselves when `DATABASE_URL` is unset, as that run leaves it.

## The screens, driven like a phone (04321e4)

The six `web/check-*.py` screen checks, in `scripts/rehearse.py`'s order, on a
demo-only seed (`alembic upgrade head` + `scripts/seed_demo.py
--demo-passwords`), against the built web server and the API on ports
3001/8001:

| Check | Result |
|---|---|
| `check-sign-in.py` | 44 of 44 |
| `check-the-technicians-screen.py` | 60 of 60 |
| `check-the-review-screen.py` | 45 of 45 |
| `check-the-overview-screen.py` | 33 of 33 |
| `check-reporting-a-fault.py` | 23 of 23 |
| `check-when-the-api-is-down.py` | 12 of 12 |

`check-the-content-path.py` was not run: it needs Qdrant and the authoring
worker drafting from the embedding model, the part of the system this round
did not touch.

## The whole stack, end to end

`scripts/rehearse.py --fresh` was **not** run: it builds and replaces the
Docker stack on this machine, and the live trial stack of 12 November still
holds ports 3000/8000. Its equivalent here:

- the usability-test stack (ports 3002/8002, its own database) was installed
  from `04321e4`, reset to tester 1's starting world, and signed into through
  the real form: `tech-t1` lands on the job at MC-012 at step 2 of 9, `sup-t1`
  on the board with 6 decisions waiting;
- the end-to-end flows above run the same build from report to closed job.

## What this does not show

That a person can use it. The last trial with a real technician was on the
first frontend (17 November); none was run on this one.

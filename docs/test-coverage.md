# What the tests reach

**Measured 18 September 2026** on a clean checkout of `main` at `9fa0a07`, over
the whole suite - 730 tests that need nothing and 530 that need PostgreSQL -
with branch coverage on.

```
uv pip install coverage          # not a project dependency; see the last section
DATABASE_URL=postgresql://... uv run python -m coverage run \
    --source=src/pdm --branch -m pytest
uv run python -m coverage report --sort=cover
```

## The figure

| | |
|---|---|
| statements | 6,433, of which **365 never run** |
| branches | 1,100, of which 95 are taken one way only |
| **covered** | **93.4%** |
| files at 100% | **50 of 105** |
| covered, setting aside the four container entry points | **96.5%** |

## Where the 365 are

Three groups, and none of them is a surprise, which is the useful part: the
uncovered lines are where the system talks to something that has to be running.

**The four container entry points, 143 statements, none of them run.** That is
39% of everything missing, in `api/__main__.py`,
`workers/runtime/__main__.py`, `workers/authoring/__main__.py` and
`platform/config/__main__.py`. They wire a process together and then loop; what
they call is covered and the wiring is not. The rehearsal runs all four, and
[ADR-067](adr/0067-the-rehearsal-runs-inside-the-stack-it-rehearses.md) is the
record of why no CI tier can: each needs a database, a built web app and a
running API at the same time.

**The production half of two ports.** `retrieval/vectors.py` is at 56% and its
docstring says why - "Qdrant in production, an in-memory store for tests, both
behind one port" - so the covered half is the store the tests use and the
uncovered half is the adapter that talks to Qdrant. `retrieval/embedding.py` at
79% is the same shape: the missing lines are model loading. This is the pattern
[ADR-002](adr/0002-signalsource-interface-with-three-implementations.md) chose
for signals, showing up in the numbers: an interface with a real implementation
and a test one means the real one is exercised by the rehearsal and not by
pytest.

**`platform/db.py` at 52%**, which is connection setup and teardown, reached in
tests through a fixture that takes a different path.

Everything else is at 84% or above, and 50 files are at 100% including
`dispatch/domain.py`, `authoring/domain.py`, `health/domain.py` and
`triggers/domain.py` - the pure modules
[invariant 10](invariants.md) exists to keep pure, which is also what makes them
cheap to cover.

## What this number does not say

**Coverage counts lines that ran, not assertions that would fail.** Three things
found in this repository in one week were all in code at or near 100%:

- a `form_with` helper in a screen check that picked whichever form rendered
  first, so an assertion about a specific row passed whatever the row contained;
- an assertion matching a word present in the navigation of every signed-in
  page, so it passed on any page at all;
- `safety_min_score`, a configuration field that is validated, loaded, and read
  by nothing.

A line that runs proves the line is reachable. It says nothing about whether the
test would notice if the line were wrong. **This figure is a floor under the
question, not an answer to it**, and the honest use of it in a report is as
evidence that the suite reaches the system rather than that the system is
correct.

## Coverage is not a project dependency

`coverage` is not in `pyproject.toml` and CI does not run it. That is why the
command at the top installs it first, and why this page carries a date like the
other measurements rather than a badge.

Adding it would need a record under `CLAUDE.md`'s rule about dependencies. The
argument for is that this figure is worth watching rather than sampling; the
argument against is the one the other baselines make in their own words - a
figure that changes silently on every commit is a figure nobody trusts, and a
percentage that CI enforces becomes a number people write tests to move rather
than a measurement of anything.

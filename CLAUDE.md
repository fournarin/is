# Predictive maintenance with automatic work-order dispatch

An Individual Study project: one student, one term. The problem comes from a
vehicle assembly plant moving towards full automation. The advisor's brief, in
full: *monitor and predict maintenance, say where a technician should repair and
how, issue tickets automatically, and rank them against the technicians' load -
important work first when the shift is busy, lower-priority work released when
it is quiet.* The plant runs its own work-order system (CMMS); the advisor asked
for integration with it "or at least somewhere the ticket is displayed".

## The goal everything is measured against

> By the end of term there must be a system a technician can open and actually
> work from, **even if sensor data from the plant never arrives.**

Plant data is confirmed not coming this term (ADR-082). So "usable" means: a
technician gets tickets with real steps and page citations, a shift lead
releases them, and **the day real data exists it can be loaded without code
changes** - signals from a file, technicians and shifts from a file.

Dates: on 2026-09-28 the owner moved the close to **30 September 2026**: the
system, its verification and the bound report (in Thai) all finish by then. The
original freeze (22 October) and report weeks (30 Oct - 12 Nov) still bound
anything after that. The written report is what gets graded. A real technician trying the system
(ADR-014, `docs/trial-protocol.md`) is the one piece of evidence that cannot be
generated.

## How an agent works here

The owner has handed this project to the agent to run (2026-09-27, ADR-090).
Usage is scarce. Read [`.claude/autonomy.md`](.claude/autonomy.md) - it is
short - and follow it. In one line: **decide, build, test, merge; spend effort
on what a technician or the report will see, not on documents about process.**

## Four layers

```
Three sources of work
 ├── machine signals (SignalSource) → layer 1 · Trigger    [synthetic today]
 │      detect:  rules and thresholds     → Finding (detected)
 │      predict: trend → time to threshold → Finding (predicted + ETA)
 ├── the PM schedule → lower-priority work (origin = scheduled)
 └── a technician or supervisor reporting it (origin = manual)
                    ▼
layer 2 · Content - ticket with steps from an approved playbook
        │   playbook store ← drafted from manuals with RAG at build time, approved by a person
        ▼
layer 3 · Dispatch - rank against the shift's load; a round proposes,
        │   the shift lead confirms (ADR-071)
        ▼
layer 4 · Destination - our screens (the floor), a CMMS adapter, a file
        ▼
     technician - accept, close, propose corrections → back into the store
```

Layers 2 and 3 never block on layer 1. Dispatch never reads a Finding: a work
order carries everything the scheduler needs (ADR-030, ADR-041).

## Principles that are not negotiable

1. **Runtime is deterministic.** No LLM writes repair instructions while a
   technician waits. The LLM drafts at build time for a person to approve
   (ADR-003). Enforced by `lint-imports` and a network boundary.
2. **Every playbook is traceable.** Source document and page per step, revision,
   approver, approval time. A closed work order proves what it instructed via
   `playbook_snapshot`.
3. **Every ticket explains itself** - why this job, why now, why ranked here
   (ADR-005).
4. **Nothing blocks on plant data.** Everything is testable on synthetic data.
5. **When the evidence is thin, say so.** "Not found - see manual page X or ask
   an engineer" beats a guess. A plausible wrong procedure is the worst output
   this system can produce.

The fifteen invariants that make these concrete are
[`docs/invariants.md`](docs/invariants.md). The data contracts (`Signal`,
`Finding`, `Playbook`, `WorkOrder`, and the four resource contracts) are in
[`docs/contracts.md`](docs/contracts.md). Read the contract before changing a
table, an API shape or `dispatch/`.

## Where things are

| Path | What |
|---|---|
| `src/pdm/contracts/` | the data contracts as types; imports nothing else in `pdm` |
| `src/pdm/signals/`, `triggers/` | layer 1: sources, rules, trend prediction, Findings |
| `src/pdm/retrieval/`, `authoring/`, `llm/` | build-time RAG and drafting (only `authoring/` may import `llm/`) |
| `src/pdm/playbooks/`, `work/` | layer 2: approved playbooks, work orders, closing, improvement loops |
| `src/pdm/dispatch/` | layer 3: load gate, score, CP-SAT, proposals and confirmation |
| `src/pdm/sinks/` | layer 4 adapters |
| `src/pdm/health/` | machine health reader (read-only, not a source of work) |
| `src/pdm/sim/`, `baselines/` | discrete-event simulator and policy comparison |
| `src/pdm/api/`, `workers/` | FastAPI app; `worker-runtime` and `worker-authoring` |
| `web/` | Next.js screens (technician, shift lead, reviewer, overview) |
| `config/` | `plant.yaml`, `policy.yaml`, `rules.yaml` - every field is read by something |
| `fixtures/corpus/` | synthetic manuals with their own answer key (ADR-033) |
| `scripts/` | CI checks (`check_*`), measurements (`measure_*`), demo and rehearsal |
| `docs/adr/` | decision records, append-only |

`docs-md/` is the owner's Thai working notes, outside git. Citations like
`design.md 6.2` are provenance; the load-bearing parts are in
[`docs/from-the-working-notes.md`](docs/from-the-working-notes.md).

## Commands

```bash
uv sync
# the gates CI runs - run all of them on the commit you push, with a clean tree
uv run ruff format --check . && uv run ruff check .
uv run mypy                                    # file list comes from pyproject
uv run lint-imports
uv run python -m pdm.platform.config config
for s in check_no_wall_clock check_llm_isolation check_no_blob_deletion \
         check_the_stylesheets_close_every_rule check_doc_links check_config_is_read; do
  uv run python scripts/$s.py || break; done
uv run pytest -m "not db"
DATABASE_URL=postgresql://narinthon@localhost:5432/pdm_test uv run pytest -m db
(cd web && npm run lint && npm test && npm run build)          # when web/ changed

uv run python scripts/rehearse.py --fresh      # whole stack in Docker, seeded, screen-checked
```

`db` tests need real PostgreSQL; never substitute SQLite (ADR-031).

## Technology

Python, FastAPI, PostgreSQL via psycopg 3 and plain SQL (no ORM; Alembic for
migrations only). Qdrant + PostgreSQL full-text, fused by rank. The job queue is
a PostgreSQL table (`SKIP LOCKED`). OR-Tools CP-SAT. Next.js. Docker, on-premise
only - plant documents are under NDA. **No new dependency without an ADR**
(ADR-008).

## Working language

- **Reply to the owner in Thai**, technical terms in English.
- **Code, comments, commits, PRs and ADRs in English.** The repository is the
  handed-over artefact.
- ADRs are append-only: a changed mind is a new record that references the old.

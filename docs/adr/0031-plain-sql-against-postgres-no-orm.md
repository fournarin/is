# ADR-031: Reach PostgreSQL with plain SQL, not an ORM

## Context

The stack names PostgreSQL and forbids new dependencies without an ADR, but no
document says **what talks to it**. That has to be settled before the job queue,
and it shapes every repository file in the system.

What makes the options unequal is that **the load-bearing parts of this schema
are things an ORM handles badly or not at all**, and each of them is required by
an earlier decision:

| Requirement | From | How much an ORM helps |
|---|---|---|
| `FOR UPDATE SKIP LOCKED` with heartbeat and reaper | ADR-017 | works, through a translation layer |
| Playbook snapshots immutable at database level | invariant 2 | a trigger has to be written by hand |
| PostgreSQL full-text search (tsvector, GIN, trigger) | ADR-008 | autogenerate cannot see it |
| BRIN index on the signal timestamp | storage design | autogenerate cannot see it |
| CHECK constraints on statuses and enums | invariants | partially |

## Decision

1. **psycopg 3 with plain SQL** for all database access, confined to `repo.py`
   files. Rows come back as dictionaries and are converted into contract objects
   immediately - **nothing bound to a connection leaves `repo.py`.**
2. **Alembic does one job: version the migrations.** Their contents are raw SQL
   through `op.execute()`. No models are declared and autogenerate is never used.
3. **Nothing under `src/` may import SQLAlchemy or Alembic.** Both live only in
   the migrations directory, enforced by the import linter.
4. **Everything is synchronous.** FastAPI endpoints are declared as ordinary
   functions and the framework runs them in a thread pool.
5. **Tests always run against a real PostgreSQL. SQLite is never substituted.**
6. Functions in `repo.py` **receive a connection as an argument** and never open
   one.

## Reasons

1. **Point 1 is the previous ADR's boundary made real.** That ADR drew the line
   that `domain.py` must not perform I/O. If `repo.py` returned ORM objects, what
   flows into `domain.py` would be objects with a live session attached, and lazy
   loading would issue queries the moment a field is read - **a violation of
   invariant 10 that the import linter cannot see, because every line is correct
   in import terms.** Returning dictionaries and converting immediately makes that
   mistake structurally impossible.
2. **Point 2 because a half-correct autogenerate is more dangerous than none.**
   Four of the five load-bearing items above are invisible to it, so it produces a
   migration that looks complete and is missing exactly what matters, which then
   has to be corrected by hand every time - worse than writing it by hand, because
   it invites trust.
3. **Point 3 fixes the problem point 2 creates.** Alembic brings SQLAlchemy with
   it. Unguarded, somebody will eventually notice it is installed and start using
   it in `repo.py` one file at a time. The import rule makes reversing this
   decision a deliberate, visible act rather than a slow leak - the same reasoning
   as the network boundary in ADR-029.
4. **Point 4 because async buys nothing at this scale.** The load is a few dozen
   technicians and a dispatch tick every five minutes, while async comes with a
   connection pool bound to an event loop, harder testing, and deadlocks that are
   difficult to find. The genuinely heavy work is GPU-bound, where async does not
   help.
5. **Point 5 because what most needs testing is exactly what SQLite lacks.** Skip
   locked claims, BRIN, tsvector, triggers. Tests on SQLite would produce false
   confidence from runs that never touched the riskiest lines.
6. **Point 6 is a precondition of ADR-017**, which requires enqueue and complete
   to commit with the real data in one transaction. If `repo.py` opened its own
   connections, each call would sit in its own transaction and the whole class of
   bug that ADR set out to remove would return while we still believed it was
   gone.
7. **The cost of plain SQL falls exactly where there is most help available.**
   Schema, migrations, CRUD and adapters are the work AI assists with best -
   repetitive, with visible mistakes. What must not be delegated is the scoring
   formula and the drafting prompts, neither of which is affected here. Choosing
   the option whose cost lands where we have leverage beats choosing one that
   saves effort there and spends it elsewhere.

## Consequences

- New dependencies: psycopg with its binary and pool extras, and Alembic, which
  brings SQLAlchemy transitively.
- **An eighth dependency rule**: `src/` must not import SQLAlchemy or Alembic,
  which requires the linter to inspect external packages.
- CI needs a PostgreSQL service from its first database-backed test rather than
  later, and tests are slower than they would be on SQLite. Accepted: fast and
  wrong is not useful.
- Row-to-contract conversion is written by hand for every table. This is
  repetitive work traded for a clear boundary. **It must never be automated by
  reflecting the schema**, which would reintroduce an ORM under another name.
- No downgrade migrations. Forward only, consistent with the earlier decision
  that rollback is worth little in a system with a human approval step.
- **Revisit if** the schema grows past roughly 25 tables and hand-written
  conversion costs more than an ORM would. But the line that **nothing bound to a
  connection enters `domain.py`** does not move under any circumstances.

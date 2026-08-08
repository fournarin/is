# ADR-030: Package layout, the I/O boundary, and the facts a work order holds itself

## Context

The design declares four dependency rules and says an import linter will enforce
them, but those rules cannot be written as a configuration file until it is known
which package the data contracts live in. Invariant 10 - dispatch does not touch
the database - had nothing enforcing it beyond discipline, because no structural
line said which code may perform I/O.

**And drawing the real import graph revealed that two documents contradict each
other.**

The rules forbid dispatch from importing the trigger layer. But the scoring
formula includes a term for urgency derived from a predicted Finding's ETA, and
another ADR requires the priority reason to read differently depending on whether
the Finding was detected or predicted. On top of that, the station-level downtime
term must resolve a station from a machine id - **and the work order contract had
none of `machine_id`, `severity`, `kind` or `eta`. It had only a reference to the
Finding.**

As written, dispatch could not compute a score without violating its own import
rule. This is not an implementation detail; it is a conflict between two
documents that would have surfaced in week 7.

## Decision

### 1. `contracts/` is a leaf package

```
src/pdm/
  contracts/    the eight contracts and their enums - must import nothing else
  platform/     Clock, config loader, job queue, auth, audit, object store
  signals/  triggers/  playbooks/  retrieval/  llm/  authoring/
  work/     dispatch/  sinks/      sim/
  api/          FastAPI routers                    (entrypoint)
  workers/      runtime / authoring                (entrypoints)
```

### 2. Every domain module splits three ways

| File | May perform I/O | May be imported by |
|---|---|---|
| `domain.py` | **no** - pure logic | anyone, including the simulator and tests |
| `repo.py` | yes - queries and writes only, no business logic | its own module's `service.py` |
| `service.py` | yes - composes the two above | `api/` and `workers/` only |

New rule for the linter: **no module's `domain.py` may import any `repo.py`, or
the platform's database layer.** The simulator's existing rule narrows to
contracts, the two domain modules it needs, and the clock.

### 3. A work order holds the facts the scheduler needs

Add `machine_id`, `severity`, and optionally `finding_kind`, `eta` and
`eta_confidence`. The work module copies these onto the order **when it is
created**, and dispatch never reads a Finding at all. The Finding reference
remains as a trail for tracing back, not as the route the scheduler takes to its
data.

## Reasons

1. **Point 3 reuses the pattern from the playbook snapshot.** That problem was
   solved by *copying what is needed to where it is needed* rather than making
   the consumer follow a reference back. This problem has the same shape, with a
   different motive - that one was for traceability, this one is for layer
   independence. The side benefit is that a work order can be read on its own
   without a join.
2. **Point 3 also stops scheduled and manual work being second-class.** With
   severity on the Finding, those two kinds of work have no severity at all, and
   the load gate that admits "high severity only" cannot judge them. Moved onto
   the order, all three origins are assessed by the same rule.
3. **Point 1 is a technical precondition for every other rule.** With contracts
   distributed among their owning modules, every module would import across to
   fetch a type and the graph would become a mesh no rule could describe. With
   contracts as a leaf, what remains is genuinely layered.
4. **Point 2 turns invariant 10 from a promise into a structural constraint** -
   the same reasoning that makes the LLM import rule the most valuable one in the
   design. "Dispatch must not query the database" as an agreement gets violated
   the night somebody needs one more field. If `domain.py` cannot import the
   database layer at all, it cannot happen. It is also a precondition of the
   scheduler-weights loop.
5. **A simulator limited to `domain` is what makes hundreds of scenarios per CI
   run affordable.**

## Consequences

- **The work order contract in the brief must change**: five new fields, and a
  note that the Finding reference exists for tracing rather than for the
  scheduler.
- Dependency rules go from four to seven.
- "No business logic in `repo.py`" is a rule no machine can enforce and has to be
  caught in review - the one item of the three with nothing automatic behind it,
  and worth knowing will leak.
- Values copied onto the order are a snapshot at creation time. If the Finding is
  updated afterwards - its occurrence count rising - the order will not know.
  **This is deliberate**: letting the queue reorder itself from repeat firings
  contradicts the decision that queue stability is worth more than a slightly
  better answer. The technician's screen showing "seen N times" reads the Finding
  through the reference instead.

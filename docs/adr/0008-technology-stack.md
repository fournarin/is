# ADR-008: Technology stack, and the boundary around Redis

## Context

The project brief listed a full stack with no ADR behind it, which contradicts
the project's own rule that architectural decisions must record their reasoning.
Redis appeared in that list with no work anywhere in the plan that needed it.

## Decision

- Python, FastAPI, PostgreSQL, Qdrant - the same set the author has already
  taken to production once
- OR-Tools (CP-SAT) for constraint optimisation, SimPy for simulation
- Next.js for the approval screens and the technician's ticket view
- Docker, on-premise only
- **Redis is scoped to the authoring pipeline alone**, as the broker for the
  workers that ingest PDFs and draft playbooks. Serving tickets at runtime does
  not depend on it.

## Reasons

One term leaves no time to learn new tools. Something already taken to production
carries less risk than something better on paper. Redis was judged necessary
because ingesting a manual takes minutes per file and cannot be handled inside an
HTTP request - but letting it spread into runtime caching would add a dependency
to maintain on the plant's machine for no reason.

## Consequences

No new dependency without an ADR. If runtime turns out to need a cache, write a
new ADR referencing this one rather than widening its use quietly.

*The Redis portion was replaced by ADR-017.*

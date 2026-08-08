# ADR-026: Split the worker into two roles, runtime and authoring

## Context

The design had a single worker, while ADR-017 requires worker concurrency of 1
because embedding and LLM work is GPU-bound. Meanwhile runtime needs three things
running continuously that are neither HTTP requests nor authoring jobs: the
trigger loop consuming signals, the dispatch tick every five minutes, and the
queue reaper.

With all of them in the same worker as authoring jobs that take five to twenty
minutes each, **ingesting one manual stops ticket dispatch for the whole system
for twenty minutes.** No Finding is raised, no work is assigned, and no error is
produced. The moment it happens is the moment somebody uploads a manual - which
is to say, during a demonstration.

## Decision

One image, one codebase, three entrypoints.

| Process | Responsible for | Concurrency |
|---|---|---|
| `api` | All HTTP, plus runtime retrieval | normal |
| `worker-runtime` | Trigger loop, dispatch tick, reaper, runtime job class | may exceed 1; no GPU |
| `worker-authoring` | The authoring job class only | **1**, per ADR-017 |

The job table gains a `job_class` column, and each worker claims only its own.

## Reasons

1. **The right dividing line is not "short work versus long work" but "is
   anybody waiting for it".** A technician stands in front of a machine waiting
   on runtime work; an engineer looks at an authoring result some time this
   afternoon. Those tolerate latency three orders of magnitude apart and cannot
   share a worker whatever the concurrency setting.
2. **It does not break the modular monolith.** One image, one codebase, one set
   of import rules, no network calls between them - they still communicate
   through the job table. What is added is a process role, not a service with its
   own API.
3. **The real operational cost is lower than the container count suggests.** What
   the person maintaining the machine carries is not the number of containers but
   **the number of things that can fail in different ways**. Two workers from one
   image, one configuration and one log format are one thing running twice -
   unlike adding a whole new technology, which ADR-017 declined.
4. **Separation delivers ADR-001 at process level.** Previously "build time must
   not block anything else" was enforced only through import rules; now
   `worker-authoring` can die or hang without affecting ticket dispatch at all.

## Consequences

- `job_class` must exist in the first migration; adding it later means migrating
  jobs already in flight.
- **The heartbeat and reaper need two sets of thresholds.** A twenty-minute
  authoring job and a five-second runtime job cannot share a definition of "silent
  long enough to be dead". One value would either kill live ingest work or leave
  the runtime queue stalled for ten minutes before anything noticed.
- **A dispatch tick arriving while the previous one is still running must be
  skipped, not queued**, or under heavy load the system chases itself.
- Running more than one `worker-runtime` requires the dispatch tick to hold a
  lock, or two copies will assign the same work twice.
- New invariant: **`worker-runtime` must never be able to claim an authoring
  job**, tested by enqueueing one and confirming the runtime consumer does not
  touch it.

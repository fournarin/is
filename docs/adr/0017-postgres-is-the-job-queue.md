# ADR-017: PostgreSQL is the job queue; no Redis

## Context

ADR-008 named Redis as the broker for the authoring pipeline. At the time there
was a possibility of carrying a Celery and Redis pipeline over from the author's
earlier system, which would have brought Redis with it. That reuse was later
ruled out for both contractual and engineering reasons, and the reason for having
Redis went with it.

## Decision

A job table in PostgreSQL using `FOR UPDATE SKIP LOCKED`, with a heartbeat and a
reaper for workers that die mid-job. No Redis anywhere in the system.

## Reasons

1. **The main reason is traceability, not removing a dependency.** An authoring
   job produces a playbook row in `draft` with full provenance. With job state in
   Redis and the result in Postgres there are two sources of truth, and dying
   between the two writes leaves either a page nobody queued or a job reporting
   success with nothing to show. In one database, enqueue and complete commit
   with the real data in a single transaction and the entire class of bug
   disappears.
2. The volume is a handful of manuals and a few dozen jobs a term.
3. Jobs run five to twenty minutes, so polling latency measured in seconds is
   meaningless.
4. On-premise: every container that can be removed is one thing the person at the
   plant does not have to look after.
5. Redis is not durable by default; AOF has to be enabled deliberately or work is
   lost on a power cut.

## Consequences

A heartbeat every ~30 seconds is required, plus a reaper that returns jobs whose
heartbeat has gone silent to `queued`. Without it the queue dies quietly once
jobs run for minutes. Worker concurrency is 1, because embedding and LLM work is
GPU-bound and running it in parallel is not faster.

*Replaces the Redis portion of ADR-008.*

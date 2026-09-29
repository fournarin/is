# ADR-109: Scheduled work stays under its ceiling

Written on 2026-09-29. Amends ADR-011 and ADR-045 on how a quiet shift tops up
with scheduled maintenance. Decided by the agent on the owner's delegation, from
the finding recorded in ADR-107.

## Context

On a light shift, scheduled (PM) jobs are released in score order until the load
reaches `load.light_below`. The check ran **before** a job was added, so the job
that crossed the ceiling was released: a 90-minute PM on a technician with 100
minutes left moved the shift from 0% to 90%, from the light band to the heavy
one, in a single round. The quiet-shift behaviour the advisor asked for -
release lower-priority work when the shift is quiet - should not be able to make
the shift busy.

## Decision

A scheduled job is released only if the load **with it** stays at or below the
ceiling. A job that would cross is held, and its reason says the load it would
cause ("ถ้าปล่อยงานนี้ ภาระของกะจะเป็น 90% เกินเพดาน..."). The loop goes on, so a
smaller job further down the ranking may still fit. Hand-released work (ADR-059)
is unchanged.

## Consequences

- A quiet shift can no longer be pushed into the heavy band by its own top-up.
- A long PM job may wait for a quieter round even when the shift is light, while
  shorter ones behind it are released. That is the intended trade.
- The policy comparison (`compare_policies.py`) has no scheduled work, so its
  figures do not change. `docs/results/gate-trace.md` is regenerated: still no
  PM job placed outside a light round and no condition job held inside one, over
  40 runs.

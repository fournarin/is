# ADR-001: Three layers that can be built in parallel

## Context

The advisor has not yet received real-time data from the plant, and there is no
firm date for it. A system built as one piece that only works once data arrives
would stand still waiting for it.

## Decision

Split the system into Trigger, Content and Dispatch. Layers 2 and 3 must have no
code dependency on layer 1.

## Reasons

Layer 2 needs only the manuals. Layer 3 needs only technician and workload data.
Neither has to wait for a sensor. Once separated, the project's largest risk is
handled by the design rather than by waiting.

## Consequences

`Finding` has to be defined precisely from the start, because it is the contract
between layer 1 and layer 2, and a synthetic generator must be able to emit
plausible Findings so that the lower layers can be tested without layer 1
existing.

*Extended later by ADR-012, which adds a fourth layer for the destination
system, and by ADR-010, which establishes that a Finding is not the only way
work enters the system.*

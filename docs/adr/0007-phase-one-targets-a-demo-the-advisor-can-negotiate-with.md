# ADR-007: Phase 1 aims at a demo the advisor can negotiate with

## Context

The advisor said the real-time values exist "but I do not have them yet", which
means negotiation with the plant is still in progress.

## Decision

Spend the first four weeks on a prototype that produces a real ticket with real
repair steps. Use public industrial robot manuals (Fanuc, ABB) until the Ford
manuals arrive.

## Reasons

Something tangible carries more weight in a negotiation than slides, and gives
the plant a reason to release data. In effect it lets us work on the project's
own bottleneck.

## Consequences

Phase 1 favours "visible" over "complete", but must not violate ADR-003. Even a
demo needs the approval step: showing a system that generates live, and having
the plant spot a wrong value, would cost trust immediately.

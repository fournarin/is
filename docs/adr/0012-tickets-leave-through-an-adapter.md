# ADR-012: Tickets leave through an adapter interface while the CMMS question is open

## Context

We do not know whether the plant already has a CMMS. If it does, tickets have to
land there rather than in a new system nobody opens. The answer changes the whole
outbound layer, and waiting for it would block a term of work.

## Decision

Define layer 4 as an interface with swappable adapters: `OwnSystemSink` first,
then `CMMSSink` and `ChatSink`. The scheduler never learns what the destination
is.

## Reasons

This is the same shape of risk as `SignalSource` - an unknown at the boundary -
so it gets the same defence. Building the interface now costs far less than
rebuilding the outbound layer in week 10.

## Consequences

ADR-001's three layers should be read as four. Layer 4 is not developed in
parallel like layers 2 and 3; it is designed to be cheap to change. Writing to a
real CMMS happens only if access is granted and is not treated as work that must
be finished.

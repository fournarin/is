# ADR-005: Every ticket must carry a `priority_reason`

## Context

Technicians in a plant have more experience than the system. If the system gives
an order that runs against their instinct and cannot explain itself, they stop
believing it and go back to their old way of working.

## Decision

`WorkOrder` always carries a `priority_reason`, the interface shows it alongside
the ordering, and there is a way for a technician to disagree.

## Reasons

A system nobody uses has failed, however good the algorithm. User acceptance is a
functional requirement here, not a nicety.

## Consequences

If CP-SAT is used for assignment, explanations have to be derived from the
solver's result - a counterfactual such as "deferring this job adds 12 minutes of
total downtime", or naming the constraint that forced the outcome. This is also
one of the more publishable parts of the work.

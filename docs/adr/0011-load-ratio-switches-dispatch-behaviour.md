# ADR-011: Dispatch switches behaviour on `load_ratio`, not on score alone

## Context

The part of the brief the advisor described most concretely was load: when it is
heavy, choose the important work first; when it is light, release the secondary
work. The scoring formula had terms for severity, downtime cost, skill match and
waiting time - and no term for load at all.

## Decision

Two separate mechanisms. The score decides the ordering; `load_ratio` decides how
deep into the queue the system reaches. `load_ratio` is pending work in the shift
divided by the shift's capacity, with boundaries at 0.5 and 0.8.

## Reasons

Folding load in as another term produces a weight nobody can interpret, and no
way to explain to a technician why a job that waited yesterday is being done
today. As a gate it collapses to one sentence - "this shift is at 92%, four
non-urgent jobs are being held" - which serves ADR-005 directly.

## Consequences

Shift capacity must be known, which requires technician data, which is a further
reason to ask for it before sensor data. Test scenarios in phase 2 must cover
both heavy and light load rather than a single point. The 0.5 and 0.8 values live
in configuration.

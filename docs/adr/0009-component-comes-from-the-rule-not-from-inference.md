# ADR-009: `component` comes from the rule's own definition, never from inference

## Context

The advisor requires the system to say **which part** a technician should repair.
But a threshold rule on a PLC signal gives information at machine level, not part
level, and `Finding.component` had been defined without saying who fills it in.

## Decision

Each rule declares in its own definition which component it watches (one signal
tag maps to one component). A rule that cannot say uses `unknown`, and layer 2
then serves a **fault-finding** playbook instead of a repair one.

## Reasons

Inferring the component from a signal is guesswork that can be wrong and cannot
be explained, which violates two of the project's principles. Having the rule's
author declare it means the answer to "which part" always has somebody behind it,
and when it cannot be determined the system says so - which is what a technician
does in reality anyway.

## Consequences

A second kind of playbook is needed for diagnosis, and phase 1 must include at
least one `unknown` case to prove that path works. When asking the plant for
data, ask for **the map of which tag sits on which part**, not only for the
signal values.

# ADR-002: `SignalSource` is an interface with three implementations

## Context

Data could arrive in any shape - historical CSV, OPC UA, MQTT - or not at all.

## Decision

Define `Signal` as `(timestamp, machine_id, metric_name, value, unit)` and build
three implementations: `SyntheticSource`, `ReplaySource`, `LiveSource`.

## Reasons

The rest of the code talks to this contract alone and neither knows nor cares
what sits behind it. When real data arrives, the source is swapped and nothing
else changes.

## Consequences

`SyntheticSource` must model believable situations - a motor heating gradually
until it fails - rather than emitting random numbers, because it is what proves
the detector works.

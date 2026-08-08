# ADR-010: `WorkOrder` has an `origin` - work does not only come from a Finding

## Context

The advisor asked that when load is light, the system "release the lower-priority
work". But `WorkOrder` required a `finding_ref`, which meant every job had to
originate from a signal crossing a threshold. On a quiet shift the system would
have had nothing at all to hand out.

## Decision

Add `origin` with values condition / scheduled / manual, make `finding_ref`
optional, and add `pm_task_ref`.

## Reasons

Lower-priority work in a real plant is scheduled maintenance and jobs reported by
a supervisor or a technician. Neither has a Finding attached. Without recognising
other sources of work, the advisor's fifth requirement is structurally impossible
rather than merely unimplemented.

## Consequences

Layer 2 must be able to find a playbook for PM work as well, not only for symptom
codes, and connecting to the plant's existing PM schedule becomes another data
request - consistent with the choice already made to build on that schedule.

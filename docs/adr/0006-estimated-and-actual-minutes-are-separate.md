# ADR-006: `estimated_minutes` and `actual_minutes` are separate fields

## Context

The scheduler needs an estimate of repair duration to build a queue, but
estimates taken from manuals routinely differ from reality.

## Decision

Keep `estimated_minutes` on `Playbook` and `actual_minutes` on `WorkOrder`,
separately.

## Reasons

Once real data accumulates, the estimate can be corrected. This is a feedback
loop that improves the system with no machine learning at all.

## Consequences

Technicians have to record completion times, which is extra burden. It must be as
close to a single tap as possible, or derived automatically from status changes.

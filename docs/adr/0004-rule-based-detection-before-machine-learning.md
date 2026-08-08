# ADR-004: Start with rules, not machine learning, for detection

## Context

Direct experience from the author's earlier project: a prediction feature was cut
because the only inputs were machine specifications, repair history and shift
reports - no live sensors, no failure labels. Accuracy never reached what a
production line would accept.

## Decision

Layer 1 begins with threshold rules and condition-based monitoring built on the
existing PM schedule. No supervised model yet.

## Reasons

The threshold values are already in the machine manuals. No labels are needed, no
dataset is needed, a technician can read the rule and see immediately why it
fired, and a wrong threshold is fixed by editing a number rather than retraining.

## Consequences

Label quality must be confirmed with the plant before option 1D is considered:
how many years of history, how precisely the times are recorded, whether the
component is identified, and whether genuine breakdowns can be separated from
scheduled maintenance.

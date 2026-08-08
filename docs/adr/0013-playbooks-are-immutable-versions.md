# ADR-013: A playbook version cannot be edited in place

## Context

ADR-003 requires a person to approve every playbook. Content changes for two
reasons - the manual gets a new edition, or a technician reports that the
procedure does not work. Editing in place would leave an approved playbook whose
current content nobody approved.

## Decision

Every edit creates a new `draft` pointing at the one it supersedes. Runtime keeps
serving the previous version while the draft waits, and a draft is never served
at runtime under any circumstances, including when there is nothing else to give
the technician.

## Reasons

Traceability collapses the moment content can change while `approved_by` and
`approved_at` still point at the previous approval. And letting a draft escape
when there is nothing else to serve opens exactly the gap ADR-003 exists to
close: text reaching a technician that nobody has read.

## Consequences

Version history and diff screens are needed, and the review queue becomes
something that must be maintained rather than a decorative feature - a queue
nobody clears leaves the system permanently on the old version.

*The mechanism here was replaced by ADR-018.*

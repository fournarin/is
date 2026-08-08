# ADR-018: Drop the playbook version chain; move history onto the work order

## Context

ADR-013 made playbooks immutable, with every edit creating a successor and a
hash-based diff to detect whether the source pages had changed. That machinery is
expensive to build and takes real interface space (a history screen, a diff
screen) in a project with twelve weeks of technical work and one person.

## Decision

- The playbook table holds only the current version, one row per
  (`symptom_code`, `machine_model`). Approval overwrites and increments
  `revision`.
- Remove `supersedes`, the version chain, hash diffing, the version history
  screen and the `stale` status. Statuses are draft / approved / needs_review.
- **Add `WorkOrder.playbook_snapshot`** - a frozen copy of the steps, their
  per-step provenance and the approval, taken when the order was issued and never
  editable for the life of the order.
- The operator manages manuals directly: replacing an edition moves every
  playbook derived from it to `needs_review` automatically.
- Old PDFs are removed from the retrieval index but kept on disk.

## Reasons

1. **The only problem versioning actually solved was the traceability of closed
   work orders** - not rollback, and not browsing history. Overwriting without a
   snapshot would make last month's work order point at steps that are not what
   the technician did, so an incident could not be reconstructed.
2. A snapshot solves that more directly and more cheaply, by keeping the history
   where it is actually needed. Once moved, the playbook table has no reason to
   keep history at all.
3. **An operator replacing a manual is a clearer and less fragile signal than
   hashing pages.** A diff guesses whether a referenced page changed; replacing
   the edition states outright that the basis has changed.
4. The rollback capability lost is worth little, since approval already has a
   person in it, and reverting to steps from a manual that is no longer in the
   system is not something anyone should do.
5. Removing the diff engine and history screen returns time to layer 3, which is
   where this work is graded.

## Consequences

- `playbook_snapshot` must be unmodifiable, enforced at schema and code level,
  because it is now the only remaining evidence.
- A technician's objection becomes a pending edit on the current row; approval
  overwrites, with no version chain.
- The ability to answer "what did this playbook look like three months ago" is
  lost when no work order was issued in that period. Acceptable: the question
  people actually ask is "what did this work order instruct", not "what did the
  playbook used to say".

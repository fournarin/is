# ADR-038: The review queue is its own table, and the served table holds no drafts

## Context

Slice 3.5 produces drafts and has nowhere to put them. ADR-018 settled what the
playbook table looks like - one row per (`symptom_code`, `machine_model`),
approval overwrites and increments `revision`, no version chain - and left one
sentence for everything that happens before approval: *"a technician's objection
becomes a pending edit on the current row."*

That sentence does not survive contact with the two things that will actually
arrive:

1. **A pair can already be approved.** Re-drafting after a manual is replaced
   produces new steps for a row a technician is being sent to work from today. If
   the draft lands on that row, unreviewed text is in front of a technician,
   which is the whole of what ADR-003 exists to prevent.
2. **Two pending edits can exist at once** - an engineer's re-draft and a
   technician's objection from the floor. One row holds one pending edit, so the
   second silently replaces the first, and the one that loses is whichever
   arrived first, which is usually the person who was standing at the machine.

`design.md` section 4 also requires the two to arrive in **one** review queue,
because one engineer reviews both and nobody opens two boxes.

## Decision

### 1. Two tables, split by whether the content is served

| Table | Holds | Read by |
|---|---|---|
| `playbook` | what a technician can be given, one row per pair | runtime |
| `playbook_proposal` | everything waiting for a person | the review screen |

### 2. The served table has no `draft` rows

Statuses there are `approved` and `needs_review`. A draft is a proposal and lives
in the other table.

This turns invariant 3 - "a draft is never served at runtime, not even when there
is nothing else to give the technician" - from a rule the serving code has to
remember into a state the database cannot hold. There is no draft row to serve by
mistake.

### 3. One queue, two origins, and the whole drafting outcome

A proposal carries `origin` (`drafted` or `technician`), the steps with their
per-step provenance, and - for a drafted one - the outcome, the steps the gate
rejected and the reason (ADR-037). A withheld draft is a row in this queue with
no steps and a reason, because "the drafter produced nothing usable, here is
what it tried" is information the reviewer needs and a silence is not.

### 4. Several proposals may be pending for one pair, and approving one does not
dismiss the others

Dismissal is explicit, recorded, and carries a note. A re-draft that quietly
closed a technician's objection would lose the one report in this system that
came from somebody standing at the machine.

### 5. Approval applies a proposal onto the served row

Overwrite, `revision + 1`, and record who approved it, when, and **the role they
held at that moment** (ADR-024). Only an engineer may do it, checked at the
endpoint rather than by hiding a button (invariant 6) and again in the service,
because the service is what the worker and the seed script call.

### 6. Nothing is deleted - neither dismissed proposals nor rejected ones

They are the record that a suggestion was considered, and in aggregate they are
the only signal that a backend has started fabricating.

### 7. Replacing a manual moves every playbook citing it to `needs_review`

Still served, with a warning (ADR-018, `design.md` 5). Which playbooks cite a
document is answered by a `cited_documents` array maintained when the row is
written, not by reading the steps at cascade time: the cascade is a safety
mechanism and should not depend on the shape of a JSON document that changes
whenever a step gains a field.

## Reasons

**The split is not about tidiness; it is about what can be served.** Every other
arrangement leaves a row that is one mistaken `WHERE` clause away from putting
unapproved text on a technician's screen. With drafts in a different table, the
serving query cannot reach them even if it is wrong.

**Proposals are not a version chain.** ADR-018 removed history from this side of
the system and that stands: a proposal is work waiting to be done, not a record
of what the playbook used to say. It stops existing as content the moment it is
applied or dismissed, and the history that matters still lives in
`WorkOrder.playbook_snapshot`.

**Keeping dismissals is cheap and answers a question nobody can otherwise
answer:** why does this symptom still have no playbook, when the queue shows
somebody looked at it three times.

## Consequences

- **The review screen has one list**, mixing LLM drafts and technician
  objections, ordered by age. That is `design.md` 4's requirement, and it is now
  a query rather than a merge of two sources.
- **`Playbook` objects with `status = draft` can be built and never stored.**
  `PlaybookDraft.into_playbook` produces one, and the repository refuses it. The
  contract keeps the status because the in-memory object is what the review
  screen renders before anybody approves anything.
- **A pair with no approved row and a pending proposal serves nothing at
  runtime**, which is the extractive fallback's case (ADR-003) and not this
  table's problem.
- **The cascade can flag a playbook whose citing step was later edited away**,
  because the array is maintained on write. Over-flagging is the safe direction:
  a `needs_review` playbook is still served, with a warning, and the cost is one
  engineer's glance.
- Two more tables to migrate, and `authoring/` gains a dependency on
  `playbooks/` - allowed by the import rules, which forbid only the reverse.

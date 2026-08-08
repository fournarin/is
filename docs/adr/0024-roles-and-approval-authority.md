# ADR-024: Roles and approval authority

## Context

ADR-003 rests on the sentence "no page reaches a technician without somebody
approving it", but no document said **who that somebody can be**. If anybody with
a login can approve, the whole gate is ceremony and the most expensive principle
in the system has no effect.

## Decision

Define roles and bind safety-relevant actions to them.

| Action | Who may |
|---|---|
| Approve a playbook | **engineer only** |
| Propose a playbook edit | technician / engineer |
| Upload or replace a manual | operator / engineer |
| Release work the load gate is holding | supervisor / engineer |
| Accept and close work | technician |
| Change configuration (thresholds, weights) | engineer, with the editor recorded |

`Playbook.approver_role` records the role held **at the moment of approval**, not
the person's current role.

## Reasons

1. The same reasoning as the playbook snapshot: people change position, but the
   evidence that "at the time of approval, this person had the authority" must
   not move with them. Storing only a user id leaves the record unreadable later.
2. Separate roles mean **a technician cannot approve their own proposal**, which
   is the most dangerous case in the objection loop. Field knowledge is valuable
   and still has to pass the person accountable for the content.
3. An engineer may edit a draft and approve it, because the drafter is an LLM
   rather than a person. Requiring a second human in a project with one engineer
   would make the system unusable.

## Consequences

- **There is no mode that disables authentication, not even for a demo.** This
  comes from the author's earlier system, which had a demonstration mode that let
  unauthenticated requests run with elevated rights and required a warning in the
  handover documentation. Demos use sample accounts with real roles.
- The approval endpoint must be tested to reject non-engineers, rather than
  merely hiding the button.

*Note: this ADR states "five roles" while its table names four. The
implementation defines exactly the four with stated authority; a fifth would need
its own ADR before appearing in code.*

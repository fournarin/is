# ADR-130: Tools in Thai, and a skill picked by name

Written on 2026-10-04. Extends ADR-095 from a playbook's steps to its tools, and
changes how the approver gives the skill. Decided by the agent on the owner's
delegation (ADR-090), from the fourth trial (`docs/results/owner-trial.md`).

## Context

ADR-095 let the approver render each step in Thai under a figure check. The
tools were left as the manual wrote them, so a technician read "torque wrench
5-60 Nm · belt tension gauge · 10 mm socket" on a card that was otherwise Thai
(fourth trial, finding 10). On the same form the skill was a text box holding
"robot_mechanical", with the plant's Thai names in `plant.yaml` and nowhere on
the screen (finding 17).

## Decision

1. `Playbook.tools_th` holds the approver's Thai for each tool, position for
   position; "" keeps a tool as the manual wrote it, and an empty tuple means
   none were rendered (migration 0018). Approval takes `thai_tools`, and every
   rendering passes the same check as a step's: the same figures and every unit
   the original states (ADR-095, ADR-108). A wrench of 5-50 Nm is refused.
2. The technician's card and the printed ticket show each tool in Thai where
   there is one, else as the manual wrote it.
3. The proposal detail carries the skill vocabulary with its Thai names, and the
   approval form offers it as a choice. Invariant 13 already refused any other
   value; the form no longer invites one.

## Consequences

- Playbooks approved before this have no Thai tools until they are approved
  again; the card shows the manual's words for them, as before.
- Tests: `tests/playbooks/test_steps_in_thai.py` (the rule),
  `tests/api/test_review_queue.py` (stored on approval, the skill choices).

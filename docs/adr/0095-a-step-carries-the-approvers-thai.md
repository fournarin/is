# ADR-095: A step carries the approver's Thai, with the manual's figures checked

Written on 2026-09-27, after the rebuilt screens (ADR-093) showed the one part
of the technician's screen still in English: the repair steps themselves.

## Context

The manuals are English (FANUC's are, and so are the synthetic ones built to
stand in for them, ADR-033). The drafter quotes them (ADR-037 §9). So every step
a Thai technician reads is English, on the screen that ADR-093 otherwise made
Thai.

Translating at runtime is out, for the reason ADR-003 exists: no model writes
what a technician does while they wait. Translating on the screen is out for
the same reason. What reaches a technician must be what a person approved.

## Decision

1. **`PlaybookStep` gains an optional `text_th`.** `text` stays the manual's
   words, which the page citation proves. `text_th` is what the approving
   engineer wrote or checked.
2. **It is supplied at approval**, position for position (`thai_steps` on
   `POST /playbooks/queue/{id}/approve`), from a field per step on the review
   screen. A blank entry leaves that step without Thai. If a model is ever wired
   into `llm-server`, it may pre-fill these fields at build time, and an engineer
   still approves them. The model never writes to a step.
3. **Every figure in the Thai must equal the figures in the step it renders**,
   in both directions, or the approval is refused and the step is named. This
   is checked even though an edit of the English is not (ADR-064). A rendering
   has an exact answer about its numbers, and translation is where 42 becomes 24
   without anyone reading it twice.
4. **The technician reads the Thai first, and the manual's words beneath it**,
   on the step screen, the checklist and the printed ticket. A step with no
   Thai shows the English alone.
5. It travels in `playbook_snapshot` like every other field of a step, so a
   closed work order proves the Thai it showed as well as the English.

## Consequences

- An engineer approving a playbook spends a few minutes more on it, once. This
  is the cost of the steps being in the technician's language, and it is paid
  by the one person who can vouch for the words.
- Playbooks approved before this change have no Thai. Adding it needs a new
  proposal and a re-approval, which is the path ADR-018 already gives any
  change to a served playbook.
- `figures()` moves to `pdm/contracts/wording.py`, since both the drafting gate
  and this check use it and `contracts/` is the one module both may import.

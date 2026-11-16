# ADR-135: Isolation is confirmed point by point, and locks are registered

Written on 2026-11-16. Extends ADR-018 (the snapshot is what was instructed),
ADR-025 (handover needs a note) and ADR-134. Decided by the agent on the
owner's delegation (ADR-090), carrying out the owner's decision Q9 (2026-11-15):
engineer-marked isolation steps, lock ownership, restore and handover are in
scope now, backend included.

## Context

The trials and the EHS review (design/REQUIREMENTS.md REQ-H-02 to REQ-H-07) found
the same gap from three sides. A lockout step was one tap like any other. A job
could be closed or handed over without anybody saying whether a lock was still
on the breaker. And the earlier attempt to highlight safety steps by keyword
missed the hot-surface wait and highlighted the unlock step exactly like the
lock step. A plausible wrong procedure is the worst output this system can
produce (principle 5), and an unclear lock state is how one hurts somebody.

## Decision

1. **The engineer marks the step; the screen never guesses.** `PlaybookStep`
   gains `kind` (`normal | isolation | verify | restore | hazard`), `hazards`
   (ISO 7010 codes), `isolation_points` (one object per breaker or valve: id,
   label, energy) and `wait_minutes`. The marks travel in `playbook_snapshot`
   like the text. An isolation, verify or restore step must name its points.
   Nothing is inferred from the words of a step (REQ-H-02).
2. **Each point is confirmed in OSHA 1910.147 order**, with who and when, in
   `step_confirmation`:
   - isolation: switched off, then a personal lock with its number;
   - verify: zero energy;
   - restore: the lock taken off by its owner.

   A hazard with a wait starts its clock when the step is reached. `POST
   /work-orders/{ref}/steps/{n}/confirm` takes one confirmation at a time and
   refuses one out of order. `progress` refuses to move past an unfinished
   step, so the order holds without the button and without JavaScript
   (REQ-H-04).
3. **Locks are a register.** `lock_record` holds point, lock number, owner, the
   step it went on, and when; it stays open until the owner takes it off. A
   lock number can be on one point at a time, which a partial unique index
   enforces. Every screen of the job shows a strip saying who has which lock on.
4. **Closing and handing over say what is still locked**: released, still
   locked (with the reason), or not isolated. The API checks the answer against
   the register and refuses one that contradicts it - "my locks are off" while
   one of yours is on, or "not isolated" while any lock is on the job. As REQ-H-06
   asks for Phase A, the answer is written as the first line of the note.
   A caller that does not answer is accepted only when none of its locks are on
   the job, so clients that predate the question still work where it cannot
   matter.
5. **An isolation step with no verify step after it** is shown with a stop bar
   (REQ-H-05). The playbook is still served; the technician is told to go to the
   shift lead before starting.

## Consequences

- One migration (0021), with two tables. The step marks need none, because the
  snapshot is JSON and older snapshots read as normal steps.
- Not yet built:
  - **Lock transfer between people at handover** (REQ-H-07, Phase B). A lock
    left on stays its owner's, the strip and the handover screen say so, and the
    screen says there is no transfer button yet.
  - **The engineer review screen that sets the marks** (set 5). Until then the
    marks come from the seed and the API contract.
  - **A `lock_state` field on the order** (REQ-H-06, Phase B), which would
    replace the note line.
- The personal lock numbers offered for one tap are the ones the person has
  used before, read from the register. There is no list of issued padlocks yet.

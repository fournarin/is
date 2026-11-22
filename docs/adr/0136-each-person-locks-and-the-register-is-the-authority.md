# ADR-136: Each person locks, and the register is the authority on every answer

Written on 2026-11-16. Amends ADR-135 after the EHS review of set 2
(ui-redesign-work/design/review/s2-safety.md), which found the screens right and
the server rules behind them open in six places. Decided by the agent on the
owner's delegation (ADR-090).

## Context

ADR-135 checked the order of confirmations inside a step and checked the lock
answer against the caller's own locks. The review showed what that let through:

- **Red line 3.** Whoever took over a job could close it with no lock answer
  while the first technician's lock was still on.
- **B1.** A confirmation could be made on a step the job had not reached:
  released at step 2, verified before the lock, a wait started early. A
  "locked" statement counted even after the lock came off.
- **B2.** "Released, back to production" was accepted while another person's
  lock, or another job's lock, was on the same machine.
- **B3.** After a handover or a "still locked" close the owner could never record
  the lock coming off.
- **B4.** The register had no person in its key, so a second technician or the
  receiver of a handover could not hang their own lock (1910.147(f)(3)).
- **B5.** Restore was only "unlock", and a combined refit, unlock and test-run step
  went unflagged.

## Decision

1. **Per person.** A confirmation is keyed by who made it (migration 0022).
   An isolation step needs every point switched off once, by anybody. It needs
   **your own lock on that point now**, not a past statement of it. Verify is
   yours too. Whoever works past an isolation step has their own lock on, so
   group lockout and the receiver of a handover fall out of the same rule.
   Past a restore step for a point, its lock is no longer asked for.
2. **Nothing ahead.** A confirmation is accepted only on a step the job has
   reached, with every step before it finished for that person. A lock taken
   off early reopens the isolation step for everyone who works past it.
3. **The register answers.**
   - No answer is refused while anybody's lock is on the job.
   - "Released" is refused while any lock is on the machine, or from somebody
     who never locked here.
   - "Not isolated" is refused where anybody locked anything.
4. **The owner takes their own lock off, from anywhere**, with a reason
   (`POST /locks/{id}/release`, a "my locks" section on the job page), and only
   their own. This is how the register ends empty after a handover or a "still
   locked" close.
5. **The plant's restore checks** (R-H5: tools removed, guards back, people
   clear, operator told) are EHS's list in `policy.yaml` `safety`, the same on
   every machine. Each is confirmed before any lock on a restore step comes off.
6. **At approval**, energy marks are refused when:
   - an isolated point is not verified after it;
   - an isolated point is not restored after it;
   - a restore step also runs or tests the machine.

   The last check reads the step's words. This is allowed for a warning to the
   approving engineer, and is never done on a technician's screen (REQ-H-02).
7. **A close kept offline and refused by the register when it arrives** is kept
   on the device with the API's sentence and shown. It is never retried.

## Consequences

- Two technicians on one job each hang a lock, and the job cannot close as
  "back to production" until both are off.
- The step page's "next" can be disabled by an earlier step: the person's own
  lock came off, or they joined after the isolation. The page says which step.
- Still open:
  - An abandoned-lock record for the supervisor and EHS (a lock whose owner is
    gone), and the board's "machines locked now" list. Both are set 3.
  - A list of issued padlocks per person: lock numbers are still typed or picked
    from the person's own history.
  - Recording the verify reading as a value (0 V) rather than a tap.

# ADR-137: A lock comes off in the restore step, or witnessed once the job is gone

Written on 2026-11-16. Amends ADR-136 after the second EHS review of set 2
(ui-redesign-work/design/review/s2r2-safety.md). That review closed red line 3,
B1, B2 and B4, and found five new holes. Decided by the agent on the owner's
delegation (ADR-090). Each hole below has a test, and each test fails on
889d040, the ADR-136 commit: seven tests fail there and pass here.

## Decision

1. **N1. A job you hold is restored in its restore step.** The owner's own
   release (`POST /locks/{id}/release`) is refused while they still hold the
   job, because the restore step is where the plant's checks are confirmed.
   "Released" in either form is also refused on any job where a lock went on
   but the restore checks were never confirmed.
2. **B3. A release outside the restore step is witnessed.** The owner gives a
   reason, and a shift lead signs with their own user and password on the
   phone. Their account must be a supervisor's. Migration 0023 stores the
   witness beside the reason.
3. **N2. Lock-on before lock-off.** While the job is still open, the sender of
   a handover cannot take their lock off a point until somebody else's lock is
   on that point. The machine is never without a lock between two people.
4. **N3. "Mine are off, the machine is still locked by another job"**
   (`released_machine_locked`) is a fourth answer. It is accepted when this job
   has no lock left, you locked here, and another job's lock is on the machine.
   "Back to production" stays refused while any lock is on the machine. Before
   this, the first technician on a shared machine could give no true answer.
   No answer at all is now refused wherever anybody locked on the job.
5. **N4. Inside a restore step its own points are being restored.** The
   isolation step behind it stops asking for their locks, so a step with two
   points can take off both.
6. **N5. Migration 0022 fills the reason before it requires one**
   ('restore step (before ADR-136)'). A test migrates a database holding a
   released lock from 0021 to head.
7. **B5. Every approved playbook is linted where it is saved**
   (`repo.save_approved`): approval, seeds, and anything set through the
   contract. This is tested through the approval API as well as the function.
8. **Serialised per machine.** Every read-then-write of a machine's locks
   takes a transaction-scoped advisory lock for that machine, so a lock hung
   in between cannot slip past "back to production".

## Consequences

- One migration (0023) and one new answer in `LockState`. The close and
  handover forms show the fourth answer only when another job's lock is on the
  machine.
- Still not built:
  - **The abandoned-lock record** (a lock whose owner has gone), signed by the
    supervisor and EHS, and the board's "locked now" list. Both are set 3.
  - **An issued-padlock list.**
  - **The verify reading as a value.**
  - **Telling the shift lead** when a close kept offline is refused.
- Who grades a hazard code as DANGER or CAUTION is still written in code (only
  W012 is DANGER). The review asks for this to be EHS's table in config. It is
  left for the owner and EHS to decide.

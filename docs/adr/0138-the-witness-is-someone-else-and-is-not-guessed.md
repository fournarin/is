# ADR-138: The witness is someone else and is not guessed; one writer per machine

Written on 2026-11-16. Carries out the set 2 final review's carry-over C1-C5
(ui-redesign-work/design/review/set2-final.md), which passed set 2 for a
supervised real-machine trial with conditions. Decided by the agent on the
owner's delegation (ADR-090). Amends ADR-137.

## Decision

1. **C1. Nobody witnesses their own release.** The service refuses a witness
   who is the lock's owner, whatever their role.
2. **C2. A witness password is not guessed and not kept.**
   - Every attempt is written to the access log
     (`witness_lock_release`, with the witness's user as the subject).
   - After five refused attempts in fifteen minutes the witness is held: the
     API answers 429, even to the right password, until the window passes.
   - The phone's field asks the browser and password managers not to save it,
     and the server never keeps it.
   - A short per-lead PIN, which the review suggests, would need a place to
     issue and store it. That waits for the board set.
3. **C3. A release after the job has closed makes the restore checks.** The
   restore step went with the job, so the plant's checks (`policy.yaml`
   `safety`) are confirmed on the release itself and stored beside it
   (migration 0024, `release_checks`). "My locks" shows them only for a closed
   job.
4. **C4. Between a handover and the lead's re-assignment** the sender's lock is
   the only lock on the point, so it stays on, and nobody holds the job to
   close it. This is now tested.
5. **C5. One transaction, one writer per machine.**
   - The API's connection is not autocommit; a test checks this.
   - The per-machine advisory lock is held until commit. A two-connection test
     shows a second transaction waits for it, and that another machine does
     not.
   - Moving to the next step takes the same lock.

## Consequences

The trial conditions stand as the review wrote them: one line or cell, one or
two technicians per job, handovers only with the shift lead present, the
plant's paper LOTO procedure as the authority, a safety officer present, and
the database migrated with the 0022 test passing.

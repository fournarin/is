# Set 2, round 3: EHS re-review (889d040..f4c97c8, ADR-137)

## Items from round 2

| Item | Status | Evidence (file:line in set2c.diff) and the test that reproduces it |
|---|---|---|
| **N1** release outside the restore step on a job you still hold | **Closed** | `service.py` `release_own_lock` refuses while you hold a live job (diff 471–475). Both "released" answers need the restore checks (`locks.py` `restore_checked`, diff 299–300). Test `test_your_own_lock_on_a_job_you_hold_comes_off_only_in_the_restore_step` (refused even with a witness, then close refused). |
| **N2** handover gap | **Closed for an assigned job; one window unverified** | Lock-on before lock-off while the job is `STILL_LIVE` (diff 471–487). The test checks only *after* the lead re-assigned the job. The time between the handover and the re-assignment is untested. If `STILL_LIVE` does not include the post-handover queue status, the sender can release with no other lock on. **Add that test.** Any other job's lock on the same point also counts; acceptable, because the machine is never without a lock. |
| **N3** two work orders on one machine | **Closed** | New answer `RELEASED_MACHINE_LOCKED` (`enums.py`; `locks.py` diff 291–309). The test now walks every answer: still_locked, not_isolated and no answer are refused, and the new answer is accepted. No answer is refused wherever anybody locked. Small issue: the note line shows the owner's user ID (`_owned`), not their name. |
| **N4** restore step with two points | **Closed** | `restoring` (diff 245–254, 482–491). API test `TestARestoreStepWithTwoPoints` locks, verifies, checks and releases two points, then closes as "released". |
| **N5** migration 0022 on existing data | **Closed** | Backfill runs before the CHECK constraint (diff 81–86). Under 0021 the restore step was the only way to release a lock, so the backfill text is true. `test_0022_upgrades_a_database_with_released_locks` migrates a populated 0021 database to head. |
| **B3** witness recorded | **Closed, with gaps** | Supervisor password checked by the API (diff 165–178), `release_witness` column (0023). Tested: no witness → 422; wrong password → 403; technician as witness → 403; the row stores `sup-1`. |
| **B5** lint every approved playbook | **Closed** | Runs in `repo.save_approved` (diff 216–221). Tested through the approval API (`test_review_queue`). |

**W017 hot surface:** shown correctly in `tech-step-hot-done` (W017, "ข้อควรระวัง", "ครบเวลารอแล้ว · ตรวจก่อนแตะ").

## New holes and checks

1. **Witness spoofing.**
   - A technician cannot witness (role check).
   - A supervisor **can witness their own release**: there is no `witness != owner` check. This matters if supervisors can hold locks; add the check.
   - No lockout or audit is visible for failed witness passwords on this endpoint. Rate-limit and log it like a sign-in.
   - The lead's password is typed on the technician's phone. A password seen once can be reused for later releases. A short-lived PIN, or approval from the lead's own session, would be better (set 3).
2. **A witnessed release after a "still locked" close skips the restore checks.** The machine can come back with no guard or people check. Show the policy restore checks in the "my locks" form, confirmed in front of the witness.
3. **Advisory lock.**
   - Scope is per machine, transaction-scoped, and always taken before row writes, so I see no ordering deadlock.
   - It protects nothing if the API connection runs in autocommit. That is not verified, and there is no two-connection test.
   - `reach_step` (progress) does not take it. Low risk, because it reads only the caller's own locks.
   - Add one concurrency test: apply a lock on another job versus a "released" close.
4. **Backfill is correct.** 0022 was edited after release. Any database that already passed 0022 cannot have had released rows (the upgrade would have failed), so nothing is lost.
5. **Still open, set 3:**
   - abandoned-lock record (supervisor + EHS);
   - the board's "locked now" list;
   - issued-padlock list;
   - verify recorded as a value;
   - telling the lead when a queued close is refused;
   - an EHS-owned table for DANGER/CAUTION grading.

## Verdict

**Supervised real-machine trial: YES, with conditions.**
- Before the trial: add the N2 queue-window test and the `witness != owner` check. Confirm the API transaction is not autocommit.
- One line or cell. One or two technicians per job (group lockout now works).
- Handovers only with the shift lead present until the N2 window is tested.
- The plant's paper LOTO/ECP is the authority; the app is the second record.
- จป. present.
- The trial database is migrated with the 0022 test passing.

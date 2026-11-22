# Refresh: EHS check of C1–C5 (f4c97c8..b2eb3f2, ADR-138)

All references are line numbers in `refresh/c15.diff`.

| Item | Status | Evidence | Test |
|---|---|---|---|
| C1: owner cannot be their own witness | **Closed** | `service.py` refuses `witness == user` (diff 314–316) | `test_nobody_witnesses_their_own_release` would fail without the check |
| C2: witness password limits and audit | **Closed** | Every attempt is written to the access log; after 5 failures in 15 min the API answers 429, even to the right password (diff 196–216, `auth/repo.py` 244–253) | `test_a_witness_password_is_not_guessed`: 5×403, then 429, 5 rows in the audit, released after 16 min |
| C3: late release needs restore checks | **Closed** | For a job that is no longer live, all `policy.yaml` checks are required and stored in `release_checks` (migration 0024) (diff 323–327, 343) | `test_a_late_release_makes_the_restore_checks`: a partial list is refused, the full list is stored |
| C4: handover-to-reassignment window | **Closed** | No code change: a queued job is still live, so the sender's lock stays on | `test_between_handover_and_reassignment_the_lock_stays_on` (status `queued` → 409). This is a regression guard; it passes on the old code too, because the hole never existed. |
| C5: one writer per machine | **Closed** | `reach_step` now takes `hold_machine` as well (diff 297–298) | Pool is not autocommit; a two-connection test shows the second waits and another machine does not. Neither test calls an endpoint, so only the primitive is covered, not that each endpoint takes it. |

## New, minor

- Anyone can lock a lead out of witnessing for 15 minutes with 5 wrong tries, because the count is per witness. The 429 message already says "ให้หัวหน้ากะมาใส่เอง". Acceptable for the trial.
- `autoComplete="off"` does not stop most password managers from offering to save. Use `autocomplete="new-password"`.
- The handover screen's step 2 should say *where* to release: "กุญแจของฉัน" with the lead present.

## Visual refresh

Checked on the SSR pages and PNGs. Nothing safety-related is hidden or softened:
- The lock strip shows owner, point, lock number, time and step.
- Signal words are graded correctly: W012 "อันตราย", W017 "ข้อควรระวัง".
- Every ISO sign is 48 px tall.
- The lock question is #2 on close; refused options stay disabled and give the register's reason.
- Restore checks come before unlock.

**The trial verdict and conditions are unchanged.**

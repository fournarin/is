# Set 2 review: EHS / safety officer (จป.)

I reviewed the 7 SSR pages and their PNGs against `system/screens`, and `set2.diff` line by line. I re-measured the signs with Playwright at 360 px. File:line references are to the new files, worked out from the diff hunks.

**Verdict:** This is a big step up. Steps are confirmed point by point and the server enforces the order inside each step. The register checks the lock answer, and nothing is guessed from keywords. It is **not yet safe for a real machine**. One red line is hit at the API, and the register cannot represent three real situations: an early release, a handover, and a close while still locked. Fix B1–B5 and add the missing tests before any plant trial.

## Scores (1–5)

| Criterion | Score | Why |
|---|---|---|
| OSHA order, per point | 3 | Inside a step, the order is correct (off → lock → verify, wait from when the step is reached) and `progress` refuses to skip. Across steps it is not enforced (B1). There is no notify item and no try-out; the spec had the try-out. |
| Lock register integrity | 2 | Locks are orphaned after close or handover, an early release is invisible to `progress`, there is no group lockout, and `lock_no` is not tied to an issued padlock |
| Close / handover lock answer | 3 | The UI is excellent: options are disabled with the register's reason. The API is looser (B2, B3). |
| Hot / stored-energy wait | 3 | Server clock, cannot be skipped by `progress`; it can be pre-started (B1), and the wording is wrong (W2) |
| Restore | 2 | The only item is "unlock". No pre-energise check, no signal word, and step 7 combines refit + unlock + 20-min run with no warning |
| Signs and signal words | 3 | M021 + W012 correct and ≥48 wide. W012 is **42 px tall** (R-H2 needs ≥48). The signal word follows the step kind, not the hazard (W1). |
| Honesty / no guessing | 4 | Unapproved checklists were removed. The marks carry "วิศวกรกำหนด · ฉบับที่ 1". |
| Tests | 2 | 23 tests, but the safety-critical edge cases are untested. One test passes *because of* B1. |

## Red lines

- **RL3 HIT (API):** a job with somebody's lock still on it can be closed or handed over with no lock answer. In `locks.py:139` an answer of `None` is refused only if *the caller's own* locks are on (`mine`). A receiver who never locked, closing while A's lock is on, gets through. The UI requires the answer; the API does not.
- RL1 (one-tap isolation): not hit by design. B1 lets the register stop matching the work.
- RL2 (keyword guessing): not hit. RL4 (auto-moving a locked job): not hit; the handover goes to the lead's queue. But the board does not show the lock yet, so the lead assigns blind. RL5 and RL6: not seen. RL7 (non-standard signs): not hit, but see W1.

## Blocking holes

- **B1 – `confirm()` never checks that the step was reached** (`service.py:450–507`). It does not call `first_unfinished` or compare with `step_reached`, which allows three things:
  - The restore step's `released` can be confirmed at step 2. `test_only_the_owner_takes_a_lock_off` (`test_isolation_point_by_point.py:311`) does exactly that.
  - A verify can be recorded before the lock.
  - A hazard `wait_started` can be posted early (`service.py:474`), so a 30-min cooling wait runs before the motor is even stopped.

  It is worse because `still_needed` (`locks.py:78`) only asks whether the "locked" *statement* exists, not whether the lock is **still open**. After an early release, `progress` lets the technician work steps 3–6 with no lock in the register. Fix: refuse a confirm for a step after the first unfinished one or beyond `step_reached + 0`. Treat isolation as unmet once its lock is released before the restore step is reached.
- **B2 – "Released" is checked against the caller's locks only** (`locks.py:133`). "ปลดกุญแจของฉันแล้ว **เครื่องคืนสู่การผลิต**" is accepted while another person's lock is on the job, or on the machine through another work order (two technicians, two WOs). Fix: refuse "released" while *any* open lock is on the machine, and require that the caller locked during the job. Refuse "not_isolated" if the job has any "locked" confirmation.
- **B3 – Orphaned locks.** `release_lock` (`locks.py:251`) is reached only through `confirm()`, which needs `holds_it` (`service.py:469`). After a handover the sender is removed as assignee (`service.py:569`). After a close with "still_locked", the order is no longer live. In both cases the owner can **never** record removing their own lock, and the strip shows it forever. The handover screen tells the sender to remove the lock in front of the lead (`handover-form.tsx:96`), but the register cannot record that. Fix: the owner can release their own lock at any time from a "my locks" screen (owner only, with a reason). Add a separate abandoned-lock record for supervisor + EHS, with a reason; it is not a technician button.
- **B4 – The receiver cannot register a lock, and there is no group lockout.** The primary key is `(work_order_ref, step, point_id, item)` with no person (migration `0021:32`). Once A has confirmed "locked" at CP-3, B's lock on the same step is "already confirmed" (`service.py:486`). Two technicians on one job cannot each hang a lock (1910.147(f)(3)). Fix: put `confirmed_by` in the key, require "off/locked" per person for everyone who works on the job, and add a "put on my lock" action for a receiver.
- **B5 – Restore is unlock only.** R-H5 (tools removed, guards back, people clear, station operator told, then owner unlocks) is a plant EHS rule, not step content, so it should come from EHS-approved config rather than being dropped as "unapproved". The demo playbook's step 7, "ประกอบฝาครอบกลับ ปลดกุญแจ … เดินแกน 20 นาที", is exactly the combined step R-H5 says to reject. There is no approval lint for it.

## Warnings

- **W1:** `energy.tsx:46` sets "ข้อควรระวัง" for every `hazard` step. The captured DC-bus discharge (W012, stored electrical energy) is therefore labelled CAUTION, beside the title "ขั้นอันตรายจากไฟฟ้า". Grade the signal word from the hazard code. The restore step shows no sign and no word at all.
- **W2:** `energy.tsx:225` says "เหลือก่อนแตะได้ / ครบเวลาแล้ว", which promises that the surface is safe once time is up. Say "ครบเวลารอแล้ว · ตรวจก่อนแตะ" instead, and restore the spec's line "ระหว่างรอ ห้ามแตะฝาครอบ".
- **W3:** `missing_verify` (`locks.py:107`) only checks that some verify step comes later. The verify step tests TP-1/TP-2 while the isolation is at CP-3, with no check that they cover each other. Add an approval lint that every isolated point (and every restore point) is covered. Record the measured value (for example, 0 V) rather than a tap that says "พลังงานเป็นศูนย์".
- **W4:** `lock_no` is free text, trimmed only (migration `0021:41`). Anyone can claim any number, and "ก03" and "ก-03" are different locks. Add a list of issued padlocks per person.
- **W5, offline:** confirmations are server actions with no offline state, which is correct because confirmations must never be queued with device time. But the screen does not tell the technician "ยังไม่ได้บันทึก · ทำตามใบพิมพ์ แจ้งหัวหน้ากะ". A close queued offline and later refused by the register is not tested.
- **W6:** The lock strip was shortened and dropped the owner name and step the spec showed. Keep the name when the lock is not yours. Add the board list "เครื่องที่ล็อกอยู่ตอนนี้" and locks still on at shift end.

## Missing tests

Non-owner release (`OTHER` is created but never used); confirm on an unreached step; release then `progress`; receiver locks after a handover; receiver says "released" or gives no answer while A's lock is on; two work orders on one machine; pre-started wait; "not isolated" after a release; release after a "still locked" close; queued offline close refused; combined restore step at approval.

## Fix order

B1 → B2 → B3 → B4 → B5, then W1/W2 and the 42 px W012. Most of the work is in the API and the register; the UI already does most of it.

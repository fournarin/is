# Phase 3 set 2, round 2 - core rules closed, new blockers (Cowork, 2026-11-16 22:55)

s2r2-safety.md (EHS, read 320db0d..889d040): R3, B1, B2, B4 closed with tests that hit the holes (10 of 11
missing tests added). Verdict for a supervised real-machine trial: NO until N1 + N5 (+ N4 if the machine
has more than one isolation point). s2r2-check.md: conditional pass, regression sweep clean.

## [M] Blockers (backend, each with a test that reproduces it first)
N1. service.py:553 - the owner can release their lock via "my locks" on a job they still hold, then close as
    "ปลดกุญแจแล้ว เครื่องคืนสู่การผลิต" without the restore checks (tools out, guards back, people clear, operator
    told). Release on an active job must go through the restore step; the "my locks" release is only for jobs
    the person no longer holds (after handover / closed still-locked), with a reason and a witness (B3).
N5. migration 0022:31 adds CHECK (released_at IS NULL OR release_reason IS NOT NULL) without backfilling the
    reason - any database with already-released locks fails to upgrade. Backfill (e.g. 'released before
    ADR-136') before adding the constraint; add a migration test on a DB with released rows.
N4. locks.py:124-159 - a restore step with two points cannot finish: after the first release the second is
    refused "ขั้นที่ 2 ยังยืนยันไม่ครบ". Restore validation must count the step's own points, not re-require
    the isolation step. Test with 2+ points.
N2. Handover can leave the machine unlocked: refuse the sender's release until the receiver's lock is
    registered on every point (lock-on before lock-off).
N3. Two work orders on one machine: all three lock answers are refused, so the first technician cannot close
    or hand over - define the rule (locks on the machine from another WO are listed, do not block this WO's
    own answers, but block "เครื่องคืนสู่การผลิต") and test it.
B3. Witness: "ปลดต่อหน้าหัวหน้ากะ" is only text - record the witnessing shift lead (sign-in or PIN by a
    supervisor) on owner releases outside the restore step.
B5. Lint seeded / contract-set step marks too (not only edits at approval); combined-restore approval check
    tested at API level.
## Screen fixes
S8. tech-step-offline: the "Wi-Fi หลุด" chip clips the station name at 360/390 ("ติดตั้งห") - and teach
    MEASURE to catch text clipped by overflow:hidden (scrollWidth > clientWidth on text containers).
S9. tech-noplaybook first action row spans 601-667 at 360x640 - fully above 640.
S10. Offline note on the isolation step below the fold at 360 - move up or into the lock strip.
S11. Add a hot-surface step to the design world so W017 and the "ครบเวลารอแล้ว · ตรวจก่อนแตะ" state are
    captured; wait-reason tiles in the standard tile style; handover sticky primary.
## For the EHS / owner (not code)
- Signal-word grading table (which ISO sign / hazard -> "อันตราย" vs "ข้อควรระวัง") should be owned by EHS
  config, not code; today only W012 is graded DANGER.
- Trial conditions if ever used on a real machine: one machine, one technician, no handovers until N2, the
  plant's paper LOTO procedure stays the authority, safety officer present.

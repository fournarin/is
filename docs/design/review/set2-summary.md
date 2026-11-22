# Phase 3 set 2 review - NOT PASSED: safety logic holes (Cowork, 2026-11-16 22:05)

s2-aesthetics.md (Opus): 4/5 PASS - calm and unmistakable. s2-check.md (Sonnet): conditional pass - phone
rules hold on 42 renders. s2-safety.md (EHS, read the backend diff): NOT safe for a real machine yet -
register integrity 2/5, restore 2/5, tests 2/5; red line 3 hit at the API. The screens are right; the
server rules behind them have holes. Fix order: safety first, then screens.

## [M] Safety red lines / blockers (backend, with tests for each)
R3. locks.py:139 - a missing lock answer is refused only when the CALLER's lock is on: whoever took over
   can close / hand over with no answer while the first technician's lock is still on. The API must
   require the lock answer whenever ANY lock is registered on the job (or the machine).
B1. service.py:450-507 confirm() never checks the step was reached: lock released at step 2, zero-energy
   check before the lock, hot wait started early. still_needed (locks.py:78) checks "locked was confirmed
   once", not "lock is still on" -> after an early release work continues with no lock. Enforce step order
   server-side and "lock currently on" for every step after isolation. Fix test_only_the_owner_takes_a_lock_off
   (it passes only because of this hole).
B2. locks.py:133 "ปลดกุญแจแล้ว เครื่องคืนสู่การผลิต" is checked only against the caller's locks - refuse it
   while ANY lock (other person, or another work order on the same machine) is on.
B3. Orphaned locks: after a handover or a "still locked" close the owner can never record removing their
   lock (service.py:469, 569). Allow the lock owner to record removal (witnessed by the shift lead) after
   handover/close; the register must end empty or show who still holds a lock.
B4. Confirmation key has no person (migration 0021:32): the receiver cannot register their own lock and two
   technicians cannot each lock the same job. Key by (work order, step, point, person); group lockout.
B5. Restore step is only "unlock": add the restore checks (tools removed, guards back, people clear,
   operator told) before unlock; flag at approval a step that combines refit + unlock + test run.
Missing tests to add: non-owner release (use the 2nd technician account), confirm on an unreached step,
release then move on, receiver locks after handover, two WOs on one machine, pre-started wait, queued
offline close refused by the register, combined restore step at approval.

## [M] Screen fixes
S1. Signal words by hazard: electrical DC-bus discharge = "อันตราย", not "ข้อควรระวัง" (energy.tsx:46);
   restore step shows its sign/word. Hot step uses W017 (hot surface), not W012; every sign >= 48 px (W012
   is 42 px tall).
S2. Wait wording: "เหลือก่อนแตะได้ / ครบเวลาแล้ว" implies safe to touch - say "ครบเวลารอแล้ว · ตรวจอุณหภูมิ
   ก่อนแตะ" (energy.tsx:225).
S3. Lock strip shows owner name, point, lock no., time and step (spec); offline state on the isolation step.
S4. tech-close-locked: lock-state question #2 and above the fold (spec), not #3 below it.
S5. tech-close-confirm: primary goes back to undone steps; "ปิดงานเลย" secondary; offline note (spec).
S6. tech-noplaybook actions at y=790 at 360x640 - bring the primary above 640 (set-1 carry-over, still open).
S7. Offline strip keeps "ไม่ใช่สัญญาณจริง" in the synthetic banner; "ซ่อมชั่วคราว" wording restored (or
   declared); missing-verify check covers all locked points (locks.py:107).
## Polish (aesthetics)
P1. One option-tile style on close forms; fieldset legend inside the card; manual-excerpt label on its own
   line (set-1 regression); hot timer "5 นาที" unbroken; sticky primary on close-confirm and handover.
## Later (board, set 3)
- "เครื่องที่ล็อกอยู่ตอนนี้" list on the board; issued-padlock list instead of free-text lock numbers.

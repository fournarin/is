# Set 2, round 2: EHS re-review (fix commit 889d040, ADR-136)

What I checked:
- `set2b.diff` and the full `locks.py`.
- The new SSR pages, measured at 360 px.
- The multi-point restore rule, run against the real `locks.py` with stubbed contracts.

File:line references are to the new files.

## Red line 3 and B1–B5

| Item | Status | Evidence |
|---|---|---|
| **R3** close or hand over with no lock answer while anyone's lock is on | **Closed** | `locks.py:182` refuses `None` when any lock is on the job. Test `test_whoever_took_over_must_answer…` covers close, "released" and handover by a second person. |
| **B1** confirming ahead of the job | **Closed** | `service.py:494` blocks a step that has not been reached. `service.py:498` requires every earlier step to be finished for that person. `locks.py:110` asks for *your lock on now*. Tests cover: step not reached, release at step 2, early wait, and a lock taken off early that reopens isolation. The old test that relied on the hole is gone. |
| **B2** "released" while another lock is on the machine | **Closed, with a new side effect (N3)** | `locks.py:184–190` checks the whole machine (`service.py:589`). "Not isolated" is refused once anybody locked. Both are tested. |
| **B3** orphaned locks | **Mostly closed** | `POST /locks/{id}/release` (`work_orders.py:464`) only matches the owner's locks in SQL (`locks.py:339`), and a reason is required (`service.py:565`). Tested after a still-locked close, after a handover, and for a non-owner. **Not done:** a shift-lead witness. "ปลดต่อหน้าหัวหน้ากะ" is placeholder text only (`my-locks.tsx:29`). It also opened N1 and N2. |
| **B4** per-person locks | **Closed** | The primary key now includes `confirmed_by` (migration `0022:22`). Tests cover a second technician and a handover receiver each hanging their own lock. |
| **B5** restore checks and the combined-step lint | **Partly closed** | `policy.yaml` `safety.restore_checks` must be confirmed before a release inside the restore step (tested). `energy_problems` (`domain.py:268`) catches an unverified or unrestored point, and a restore step that also runs the machine. Two gaps: the checks are bypassed by N1, and the lint runs only in `PlaybookStore` approval (`service.py:191`). Seeded or contract-set marks go through `repo.save_approved` and are never linted, and there is no engineer screen yet. |

## Missing tests from my last list

10 of 11 now exist, and each one exercises the hole, not just the happy path. The combined-restore approval check is tested only at function level, not through approval.

These are still untested, and each is a real hole:
- A restore step with two points.
- `release_own` while you still hold the job, followed by a "released" close.
- The sender releasing before the receiver has locked.
- What the first technician can answer when another work order's lock is on the machine.
- Migrating 0022 over existing released rows.

## Warnings

| Item | Status | Evidence |
|---|---|---|
| Signal word graded by hazard | Closed | `energy.tsx:28` gives W012 "อันตราย". Restore now shows W012 and "อันตราย". But `DANGER` contains only W012, so any other code defaults to CAUTION. EHS should own the grading table, not the code. |
| Wait wording | Closed | `energy.tsx:309` now says "ระหว่างรอ ห้ามแตะฝาครอบ / ครบเวลารอแล้ว · ตรวจก่อนแตะ". |
| W017 on the hot step | Not demonstrable | The world has no hot-surface step (ROUNDS). It needs one fixture capture. |
| Signs ≥ 48 px | Closed | Measured 56×48 on all four step pages. |
| Lock strip shows the owner | Closed | Shows point, lock number, owner name, time and step. |
| Verify points cover locked points | Closed | `uncovered` (`domain.py:241`) shows a stop bar naming the uncovered point. |
| Offline on the isolation step | Closed | "Wi-Fi หลุด" in the top bar, plus "ยังไม่ได้บันทึก · ทำตามใบพิมพ์" (`energy.tsx:131`). At 360 the note is below the fold. Confirmations are never queued. |

## New holes

- **N1: the restore checks can be bypassed (blocker).** "กุญแจของคุณที่ยังล็อกอยู่" on `/work` lets the owner release a lock **on a job they still hold** (`service.py:553`). That release asks for no restore checks and no restore step. The close is then accepted as "ปลดกุญแจแล้ว **เครื่องคืนสู่การผลิต**": the job is empty, the machine is empty, and "you locked here" is true (`locks.py:184`). Tools, guards, people and operator are never confirmed. Fix:
  - Refuse `release_own` while the caller holds the job (they use the restore step).
  - Refuse "released" on a job with isolation unless its restore checks are confirmed.
- **N2: the handover can leave a gap (blocker for handover).** `release_own` does not check whether the job is still open with nobody else's lock on the point. The sender can remove their lock before the receiver locks, so the machine sits unlocked between shifts. The test only follows the correct order. Fix: while the job is open, refuse the sender's release on a point with no other lock on it, unless the shift lead records it.
- **N3: two work orders on one machine (deadlock).** Technician A has finished and released, while B's lock is on via another work order. In the close and handover forms (`close-form.tsx:291`, `handover-form.tsx:33`):
  - "released" is refused because of B's lock on the machine;
  - "still locked" is refused because nothing is locked on A's job;
  - "not isolated" is refused because A locked.

  A cannot close or hand over at all. The API accepts `None` in this case, which is a workaround nobody should use. An orphaned lock from an old job, with no abandoned-lock process until set 3, blocks every later job on that machine the same way. Fix: add an answer "ปลดกุญแจของฉันแล้ว · เครื่องยังล็อกโดย <owner> ที่ <point>".
- **N4: a restore step with two points cannot finish (deadlock).** Inside the restore step, `restored_points(before=step)` leaves out that same step. After the first point is released, the isolation step asks for "your lock on" that point again, so the second release is refused with "ขั้นที่ 2 ยังยืนยันไม่ครบ". I reproduced this against `locks.py:124–159`. The only way out is N1. Fix: count the current restore step's points as restored when confirming inside it.
- **N5: the migration fails on real data.** `0022:31` adds `CHECK (released_at IS NULL OR release_reason IS NOT NULL)` without filling `release_reason` first. Any database holding locks released under 0021, such as trial data, fails to upgrade. Fix: backfill `release_reason = 'restore step (pre-0022)'` first, and add a test that migrates a populated database.
- **Minor:**
  - A refused offline close is shown only on that device; the shift lead is not told.
  - The checks in `_lock_answer` are read-then-write under READ COMMITTED. A lock applied concurrently on the same machine can slip past "released"; lock the machine's register rows.
  - The restore step's English original is now a fragment, "remove locks,".

## Verdict

**Safe enough for a supervised trial on a real machine: NO, not today.** Fix N1 and N5 first (each less than a day). If the trial machine has more than one isolation point, fix N4 too. After that, **yes**, under these conditions:
- one machine (MC-012, single point CP-3) and one technician per job;
- no handovers during the trial, or N2 fixed;
- the plant's paper LOTO/ECP stays the authority and the app is the second record;
- จป. present.

The core rules (R3, B1, B2, B4) are now right, and tested properly.

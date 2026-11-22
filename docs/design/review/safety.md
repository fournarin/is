# Review 3: EHS / safety officer (จป.), Round 0

Scope: all screens of A, B and C, including `tech-step-isolation-phaseB.html`. I read the PNGs and checked them myself with Playwright at 360x640 and 390x844 (fixed/sticky overlap while scrolling, text contrast, ISO symbol size, tap targets, emoji scan). No rationale.md existed at the time of review.

Measured, all concepts: 0 emoji. 0 fixed/sticky elements overlapping text at 360 or 390 (A scrolls an inner `<main>`, so its bars cannot overlap, but at 360x640 only 372 px of the A isolation screen scrolls). Every text node on the step, isolation, close and job screens is ≥ 7:1. M021/W012 are 52–56 px in all three. No tech screen shows "คัน".

## Red lines

| # | A | B | C |
|---|---|---|---|
| 1 One-tap isolation | All three, owner-mandated (Q2): Phase A `tech-step.html` passes step 2 (CP-3 lockout) with "ทำขั้นนี้แล้ว". **Not for real machines.** Each Phase B file fixes this, so the point does not separate the concepts. | same | same |
| 2 Keyword guessing | no | no | no |
| 3 Close/handover without lock state | no. Handover reuses the same form, but "ยังล็อกอยู่" is free text in the note | Close: no. Handover: **unverified**, no screen | Close: no. Handover: **unverified**, no screen |
| 4 System moves a locked job | no | no | no |
| 5 Safety text obscured | no | **HIT**: in `tech-close-sign` at 360 and 390, step 6 (the unlock/restore step) prints "10 N·m" over "แล้วปลดล็อก…". The cause is the `.nw` span becoming a grid item in `.undone li` | no |
| 6 Unapproved safety text | borderline: the verify checkbox in the isolation screen says "ตรวจแล้ว เครื่องไม่มีพลังงานค้าง". That is a designer-written claim about energy state, which the engineer's text does not make | no | no |
| 7 Non-standard safety symbol/colour | **HIT**: a safety-yellow triangle with black border marks severity "▼ สูง" (tech-job) and "▼ คาดว่าจะเกิน" (board legend, station 2 and 3). This breaks REQ-H-13 (no warning triangle for equipment status) | no | warning: amber/white diagonal "hazard tape" marks the forecast state on the board (stations 2 and 3). It is not ISO, but it reads as a hazard marking |

**Verdict per red lines: A FAIL, B FAIL, C pass** (C still carries the shared red line 1 caveat). The A and B hits each take under an hour to fix.

## Scores (1–5)

| Criterion | A | B | C |
|---|---|---|---|
| 1 Isolation step, Phase B (H-03/04/05) | 3 | 4 | 4 |
| 2 Honesty in Phase A: TH+EN together, no guessing, no reassurance (H-01/02) | 4 | 4 | 4 |
| 3 Close/handover lock state (H-06, T-10) | 3 | 3 | 4 |
| 4 Lock ownership visible (R-H8, H-07) | 1 | 1 | 1 |
| 5 Pre-start disclosure / no production pressure (R-H1, H-12) | 3 | 2 | 2 |
| 6 Symbols, colour, nothing covering text (H-13, G-05, G-09) | 2 | 2 | 3 |
| 7 Operator report: "not an emergency channel" | 3 | 3 | 4 |

### Evidence for scores below 4

**A**
- 1 = 3 (isolation, 390): (a) the verify label overclaims. It should state what was observed: "ลองสั่งเดินแกนที่ teach pendant แล้ว เครื่องไม่ตอบสนอง". (b) "Breaker off" and "lock applied" are one checkbox. (c) There is no lock-number field. (d) Verify can be ticked before the lock. (e) Once ticked, a row does not show who or when, although the footer claims "บันทึกชื่อและเวลา". Fix: split the rows, gate verify behind the lock, and show "พิมพ์ชนก · 10:12" on each ticked row.
- 3 = 3 (`tech-close__review`, 390): the summary says "กุญแจ: ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต", yet step 2 (apply lock) and step 6 (unlock) are both listed as not done, and no challenge appears. The blocked state (no answer, so the button is off) is never shown. For handover, "ระบุจุดและเหตุในโน้ต" is free text. Fix: cross-check the answer against the steps, name step 6 in a stop box, and give handover structured points.
- 4 = 1: shown on no screen.
- 5 = 3 (`tech-job`): the Start button comes after the prep list, which includes "กุญแจล็อกและป้ายส่วนตัว" (good). It still never says "ต้องหยุดสถานี 3 · ตัดพลังงาน 1 จุด". That can be derived from `NEW_kind` / `NEW_isolation_points`.
- 6 = 2: red line 7 above.
- 7 = 3 (`report`, 360): the sentence is at the top, but it does not say what to do instead.

**B**
- 3 = 3 (`tech-close-sign`, 360 and 390): this shows the worst case. The record reads "แก้แล้ว" plus "ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต", while steps 3–6, including refit and unlock, are undone, and it can be signed with no challenge. Step 6 is garbled (red line 5). The close page says "ทำถึงขั้น 2" but the sign page counts step 2 as done, so it is unclear whether the lock was ever applied. There is no handover screen. Fix: the cross-check stop box, the CSS fix, and a handover screen.
- 4 = 1: shown on no screen.
- 5 = 2 (`tech-job`, 360x640): "เริ่มงาน" sits at about y=570. The tools list, which includes the lock and tag, starts below the fold, and there is no isolation line. Fix: put "ต้องหยุดสถานี 3 · ตัดพลังงาน 1 จุด (CP-3, ไฟฟ้า)" above Start.
- 6 = 2: red line 5.
- 7 = 3 (`report`): same as A.

**C**
- 4 = 1: shown on no screen.
- 5 = 2 (`tech-job`, 360/390): Start comes before the prep and lock information. The bold ETA "ราว 14:20" directly above Start adds time pressure, and there is no isolation line. Fix: same as B.
- 6 = 3: (a) the board's amber stripes. (b) The M021 pictogram in the isolation screen draws plug–slash/check–socket, which can read as "connected"; B's arrow-out reads correctly. (c) Verify is not gated behind the lock tick. (d) The next button uses only `aria-disabled`; it must really be disabled and enforced on the server.

### Not shown by any concept (the gaps I care about most)
- Lock ownership after the tick: no "กุญแจของพิมพ์ชนก อยู่ที่ CP-3 ตั้งแต่ 10:12" on steps 3–6, the close/handover review, or the board. No board list of "เครื่องที่ล็อกอยู่ตอนนี้". The board shows "ส่งต่อ รอคนรับ MC-005" with no lock state, and "เสร็จแล้ว" rows do not show the lock answer the technician gave.
- Only step 2 is marked. Step 3 (hot surface, W017, plus the wait-start time from R-H15), step 1 (E-stop) and step 6 (a combined refit + unlock + test run, i.e. a restore step) are all unmarked. **Marking one critical step and missing others is worse than marking none.** The fixture itself only marks step 2, so the fixture needs fixing too.
- No restore-step design: tools removed, guards refitted, people clear, operator told, only the lock owner unlocks.
- No plant ECP document or revision. The step text says "ตามขั้นตอนล็อกเอาต์หน้า 2", but the only button opens manual p.143.
- No `playbook_warning`, no-playbook state, print sheet, or manual-failed-to-load state. These were not required this round but are still open.
- The station is left E-stopped (step 1) when C closes "ไม่พบอาการ / ไม่ได้ตัดพลังงาน". The close summary should ask "แจ้งผู้ควบคุมสถานี 3 แล้วว่าเดินเครื่องได้".

## Best idea to steal / worst idea

| | Best | Worst |
|---|---|---|
| A | Handover is a mode of the same close form, so the mandatory lock question covers handover too | A safety-yellow/black triangle used as the "high" severity and forecast glyph |
| B | Isolation sequence: breaker off, then my lock, then lock number, then verify unlocks only after every point, with a "ยังเหลือ: …" list and the honest verify wording "ลองแล้ว เครื่องไม่ทำงาน" | The sign page signs off "แก้แล้ว + ปลดกุญแจแล้ว เครื่องคืนสู่การผลิต" with refit/unlock undone, and the unlock line is overprinted |
| C | The confirm page makes "กลับไปทำขั้น 2" the primary action and "ปิดงานเลย ทั้งที่ยังไม่ครบ" the secondary; the isolation marking says "วิศวกรกำหนดตอนอนุมัติ ฉบับที่ 3" | Start placed above the prep/lock information, with a bold ETA as the last thing read before tapping |

## Ranking and verdict

**C > B > A.** Build on **C**: it has no red line, the safest close friction, and the clearest emergency wording ("ใช้ andon หรือวิทยุ"). Move that line above the form. From B, take its isolation interaction and its signed name/time. None of the three is ready for a real machine. The Phase A step flow is acceptable only for the IS demo, and the report must state "ยังไม่ใช้กับเครื่องจริง". The owner lifted backend limits at 12:55, so the Phase B isolation flow should become the main build target rather than an optional extra file.

## Top 5 fixes (in priority order)

1. **Make the Phase B flow the main step design and cover every critical kind**, not just step 2. Use B's sequence, gate verify after the lock, and show who and when on each ticked row. Add a restore checklist (owner-only unlock) and a hot-surface W017 step with its wait-start time. Lint the combined step 6 at approval. Fixture: `NEW_kind` on steps 3 and 6.
2. **Show lock ownership everywhere.** Use a `NEW_locks[]` field (owner, point, lock number, time). Show a persistent chip on steps 3–6, close, handover and the sign page. On the board, add a "เครื่องที่ล็อกอยู่ตอนนี้" list, a lock line on the active and handover rows, and the lock answer on "เสร็จแล้ว".
3. **Cross-check close and handover.** If a lock was applied and the restore step was not done, show a stop box naming step 6, and do not accept "ปลดกุญแจแล้ว เครื่องคืนสู่การผลิต" without the restore checklist. Design the handover screen (B, C) with structured locked points and "the receiver applies their own lock before the sender removes theirs".
4. **Add a pre-start line above Start** on `tech-job`: "ต้องหยุดสถานี 3 · ตัดพลังงาน 1 จุด (CP-3 ไฟฟ้า) · ใช้กุญแจและป้ายของคุณ", with hazard symbols. Link the plant ECP number and revision (`NEW_ecp`) in the isolation step, not only manual p.143. In B and C, move Start below this line.
5. **Clear the hits and warnings today:**
   - A: drop the yellow/black triangle and use a neutral shape.
   - B: wrap the `.undone li` text in one element, and add an automated overlap test for text that overflows its grid column.
   - A: change the verify label to the observed fact.
   - C: replace the amber hazard stripes.
   - All: use the official ISO 7010 artwork with a symbol inventory, because C's M021 is ambiguous.

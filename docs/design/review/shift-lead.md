# Review: shift lead (หัวหน้ากะ) – Round 0 board screens, A / B / C

Reviewer: role 2, shift lead (interview `interviews/shift-lead.md` and REQ-S). I looked at `png/board.*` for each concept and opened `board.html` in Playwright at 1280x800 and 1920x1080. I did not read any rationale; none existed yet.
For measurements I cloned the proposal rows to 15 (the REQ-S-01 acceptance case) and checked font sizes, button heights and truncation.

## Scores (1-5; 3 = pass with fixes, 4 = pass)

| Criterion | A | B | C |
|---|---|---|---|
| 1. Shift overview in ≤10 s without scrolling (R-S1, REQ-S-01) | 3 | 3 | 3 |
| 2. Decision table (R-S3, REQ-S-02/03) | 3 | 3 | 4 |
| 3. Acting in clicks: confirm, give to someone else, set aside (R-S4/5/6) | 3 | 3 | 3 |
| 4. Per-person load, who is free (R-S2, REQ-S-07/08) | 3 | 3 | 4 |
| 5. Trust: live/stale, consistency, nothing lost (R-S7/8, REQ-S-12) | 3 | 3 | 2 |
| 6. Appeal: would I want it on my 24" and the room TV | 4 | 3 | 4 |
| **Total** | **19** | **18** | **20** |

**Red lines.** No concept has a clean hit, so none fails. Two items come close:
- **C, red line 2 (statuses that contradict each other):** station 4 has a red **"สายหยุด"** banner. The design derives it from `NEW_line_stopped`, but the row for the same machine says "เกินเกณฑ์แล้ว · เครื่องหยุด", and priority_reason says the buffer after station 4 still holds 12 cars. REQ-S-01 requires the station wording "เกินเกณฑ์" because the system cannot know whether the line has actually stopped, and real line-stop status from Andon is out of scope (REQUIREMENTS §6 item 6). If the radio says the line is running while the board says "สายหยุด", I stop trusting the board. **If this ships, it counts as a fail.**
- **All three, red line 4 (stale data the system does not report):** I could not test it. No concept draws the stale or offline banner state.
- **All three, red line 3 (jobs that vanish):** no concept has a place for expired proposals. B and C say "หมดเวลา 11:10" but never show where an expired job goes.

## Per-concept findings (anything below 4 is cited)

### A: dark header bar, line strip, technician strip, dense table
- **Overview (3).** At 1920 everything I need is on one screen: the line strip with buffers, "รอคุณยืนยัน 6 ใบ · นานสุด 2 นาที", the load band with 2,976/4,800, the next round at 10:45 and the people strip. **With 15 rows only 12 fit at 1920 and 7 at 1280**, which fails the ≥8 rule. The four summary tiles plus the people strip take 300 px.
  - **Fix:** merge the tiles into one 56 px header row.
- **Table (3).** This is the best grid of the three: separate คันที่เสีย column, ETA with date and ±, skill, waiting minutes per row, and sort buttons where "ลำดับระบบ" is the way back to system order. Two problems:
  - priority_reason is cut ("…มีช่างที่มีทักษะ…") and the full text is only a `title` tooltip, which is hover-only and useless on a tablet. REQ-S-02 requires the reason to be expandable.
  - 164 text nodes are at 14 px; desk body text must be ≥15 px (REQ-G-06).
- **Acting (3).** The "ให้คนอื่น" popover is good: sorted by free minutes, showing the current job and skill, two clicks. But "พักไว้" links to `#aside-WO-…`, which does not exist, so there is no reason picker (REQ-S-06, an M). There is also no confirmed or undo state; only the subtitle says "ยกเลิกได้ภายใน 5 วินาที".
- **People (3).** The strip is sorted by free minutes, which answers "who is most free" in under 5 s. But:
  - At 1280 it shows only "กำลังทำ", without machine or symptom.
  - Elapsed time against the standard time is shown nowhere. The active list on the right says "ประมาณ 45 นาที" but not how long has passed.
- **Trust (3).** The update time is a small grey label on the black bar. MC-004's ETA is shown as **21:00**, while the API fields `NEW_eta_local` and `state_th` say **21:10**. That kind of mismatch is how two screens end up disagreeing.
- **Appeal (4).** A looks like Excel done properly: restrained, serious, with mono codes and shape-coded priority (■ ◇ ○ survives grayscale).
- **Best idea:** the people strip, sorted by free minutes and always visible, including at 1280.
- **Worst:** reasons I cannot open, and the dead "พักไว้" and row links.

### B: "ใบคุมงานประจำกะ", a paper form
- **Overview (3).** At 1920 it is fine. **At 1280 the board is only the queue**: no people and no active work (scroll height 1885 px). With 15 rows, 12 fit at 1920 and 8 at 1280. The title block "ใบคุมงานประจำกะ" uses 440 px of width to say little.
  - **Fix:** turn the title cell into the update and next-round cell, and give 1280 a 280 px people rail.
- **Table (3).**
  - The "สภาพตอนนี้" column wraps to **3 lines (76 px)** on MC-004 and MC-028, which breaks the ≤2-line rule.
  - There is no per-row "เสนอมาแล้วกี่นาที".
  - The reason is truncated and cannot be expanded.
  - The 4-bar priority glyph is tiny and reads like a barcode.
  - The navy outline "ยืนยัน" has the same weight as the other two buttons, so a mis-click is easy.
- **Acting (3).** **The inline "ให้คนอื่น" panel is the best of the three.** It is sorted by free minutes, has a named button ("ให้สุนทร"), and warns "ระบบเสนอ WO-000113 ไว้แล้ว", which prevents double-booking. But it pushes the rows below it down while I am aiming at them. As in A and C, there is no set-aside reason picker and no undo state.
- **People (3).**
  - The right panel gives used and free minutes with a bar, plus "ผ่านไป 132 จากประมาณ 90 นาที", which is the only text-based time against standard in any concept. But that text is truncated off-screen.
  - At 1920 "ส่งต่อ รอคนรับ MC-005" **overlaps the load bar** in กิตติพงษ์'s row.
  - "ระบบเสนอ WO-000115" uses a work-order number where I need the machine and symptom, and it truncates to "WO-00011…" for วิชัย, which hides his second proposal.
- **Trust (3).** The ETA of 21:10 matches the API. But "ระบบกันไว้ก่อน … ปล่อยเมื่อภาระกะลดลง" does not say whom the job is released to. It must say the job comes back to *me* (red line 1).
- **Appeal (3).** It is calm and printable, which suits a handover sheet. On a 24" screen it reads like a form, not a live board, and the barcode glyphs add noise.
- **Best idea:** the "ให้คนอื่น" panel with the "already proposed for" warning.
- **Worst:** at 1280 it shows nothing about people.

### C: line schematic, table, and a per-person shift timeline
- **Overview (3).** At 1920 this is the best whole picture: an 8-station schematic with buffers in cars and minutes, "คอขวด", the queue, the load band, a large 10:42 clock with "อ่านใหม่ทุก 30 วินาที", and people. With 15 rows, 13 fit at 1920 and 8 at 1280. **At 1280 the schematic takes about 190 px and people and active work disappear.**
  - **Fix:** at ≤1440 px, collapse the schematic to a single 48 px strip.
- **Table (4).** Type words match R-S3 (เสียแล้ว / คาดการณ์ / แจ้งซ่อม / PM ตามแผน). Each row shows "2 นาที · เสนอ 10:40". **The reason expands in place** (`<details>`), the only concept that meets REQ-S-02. Three smaller problems:
  - The machine code sits on line 2 in small mono, so I cannot scan by machine.
  - MC-028's row wraps to 3 lines (68 px).
- **Acting (3).**
  - The others popover has named buttons, but it says นันทนา has "ไม่มีงานที่กำลังทำ" without saying the system has already proposed MC-028 for her, so double-booking is possible.
  - There is no set-aside reason picker and no undo or confirmed state.
- **People (4).** **The per-person timeline is the magnetic whiteboard reborn.** One row per person shows status, current machine and symptom, start time, standard time, a bar from start to now against the standard, free minutes, the full handover note, and "ระบบเสนอ MC-018 · MC-001 รอคุณยืนยัน". That last item shows วิชัย is being given 120 minutes. Gaps:
  - The rows use a fixed order, not sorted by free minutes.
  - Overrun is shown only in the bar. กิตติพงษ์ is at 152 of 60 minutes and has no "เกินมาตรฐาน" text, which R-S2 asks for (shape or text, not colour alone).
- **Trust (2).**
  - The "สายหยุด" near-hit described above.
  - The ETA shows 21:00 while the API says 21:10.
- **Appeal (4).** This is the one I would be proudest to put on the room TV.
- **Best idea:** the per-technician shift timeline with "ระบบเสนอ … รอคุณยืนยัน".
- **Worst:** "สายหยุด", a claim the system cannot make.

## Ranking and verdict

**C > A > B.** C can be built on if the "สายหยุด" wording is removed and the 1280 layout is fixed. A is close behind and has the stronger table and 1280 behaviour. B should not be redone from scratch, but its strengths belong in C or A rather than as a separate direction.

What to steal:
- From A: the table grid with ETA, skill and waiting minutes as separate columns, the shape-coded priority, and the people strip that survives at 1280.
- From B: the "ให้คนอื่น" panel that warns when someone is already proposed, the "ผ่านไป X จากประมาณ Y นาที" text, and the paper-form look for the A4 ส่งกะ handover sheet.

## Top 5 fixes (for today's finishing pass)

1. **Draw the missing decision states. These are M requirements and no concept has them.**
   - "พักไว้" with the 4 preset reasons plus a text field, with the confirm button disabled until a reason is chosen (REQ-S-06).
   - After "ยืนยัน", the row moves to "ส่งถึงช่างแล้ว" with a 5-second "ยกเลิก" bar naming the machine and the person (REQ-S-04, G-10).
   - The full-width stale or offline banner "ข้อมูลเมื่อ hh:mm · …" (REQ-I-04).
   - A home for expired proposals (REQ-S-12).
   - A's `#aside-` and `#WO-` links currently point nowhere.
2. **Fit 15 rows at 1920 and ≥8 at 1280, with people still visible.** Measured: A 12/7, B 12/8, C 13/8.
   - Shrink the top area: A's tiles into one row, C's schematic into a 48 px strip at ≤1440 px, B's title cell repurposed.
   - Keep rows ≤2 lines (B's state column, C's MC-028 row).
   - At 1280, keep a people rail or strip.
3. **One source of truth for every status.**
   - Use one ETA field: A and C show 21:00, B and the API show 21:10.
   - C: replace "สายหยุด" with "เกินเกณฑ์ · เครื่องหยุด" until real Andon data exists.
   - B: change "ปล่อยเมื่อภาระกะลดลง" to "กลับมารอคุณยืนยันเมื่อภาระกะต่ำกว่า …".
4. **Make per-person load answer two questions in 5 s: who is free, and who is overrunning.**
   - Sort by free minutes, or mark the most free.
   - Show elapsed against standard as text, and flag overruns above 50% with shape and text (e.g. กิตติพงษ์, WO-000105, 152/60 minutes).
   - Name what each person has been proposed for by machine and symptom, not WO number.
   - Carry this into "ให้คนอื่น" (C's นันทนา case).
5. **Make every row decidable in place.**
   - An expandable full priority_reason. C has it; A has only a hover tooltip; B has none.
   - Row click opens a read-only ticket drawer in ≤2 s (REQ-S-09).
   - A "this machine already has an open job" chip, for example:
     - MC-019 is proposed while อำนาจ is already working on MC-019.
     - MC-001 has a PM due while WO-000098 says "ควรเปลี่ยนสายแกน 1 รอบหน้า".
     - MC-005 is set aside while it also has a handover waiting.
   - On the whiteboard I would combine these jobs. The board should let me.

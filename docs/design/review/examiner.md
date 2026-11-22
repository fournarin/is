# Review: role 5, IS examiner (Round 0 snapshot, 16:41)

Lens: R-A / R-Q items in `interviews/examiners.md` and REQ-G/H/T/S/P/A in REQUIREMENTS.md. I looked at every png/ render. I also opened the HTML myself with Playwright to measure font sizes, tap targets, horizontal scroll, contrast at 360×640, and the board at 1024/1280/1920. I checked every value on screen against `data/fixture.json`.
Note for the report: this panel is a **stakeholder simulation** (REQ-A-06). Do not cite it as a real examiner's opinion. The three concepts were made by AI agents, so the report must disclose that (REQ-A-10 / R-A8).

## Scores (1-5; 3 = pass with fixes, 4 = pass)

| Criterion | A | B | C |
|---|---|---|---|
| Traceability to REQ (implicit coverage of applicable M; no orphans) | 3 | 3 | 2 |
| Honesty (synthetic label, no invented data or claims) | 3 | 3 | 3 |
| Professional finish | 4 | 3 | 3 |
| Would NOT look AI-made to a committee | 4 | 3 | 3 |
| **Red line hit** | none | none | **pending, see C-1** |

All three render the synthetic banner on every file. None has emoji, external requests or text below 14 px. All have `lang="th"` and no horizontal scroll at 360. My approximate contrast check found every text node at ≥ 7:1. **No concept has rationale.md.** As a result, R-A2 (element → REQ → test) and REQ-A-03 cannot be checked for any of them. That is the main reason no concept scores 4 on traceability.

## A

- **T-01 met only here.** At 360×640, `tech-job` shows the job, station, status, reason, ETA with date, the bar "ถัดไปอีก 1 งาน" and "เริ่มงาน", all without scrolling.
- The board has a "เรียงตาม ลำดับระบบ / คันที่เสีย / คาดการณ์" toggle with a way back to system order (S-02) and the line "ยกเลิกได้ภายใน 5 วินาที" (S-04). Load is shown as "จองแล้ว 2,976 / ความจุ 4,800 นาที-คน" (L-04). Station 4 is labelled "เกินเกณฑ์", the wording S-01 requires.
- Score < 4, **S-10 (M), `board.html` @1024×768:** the page scrolls horizontally and the "ยืนยัน" buttons and the header's right side are cut off. Fix: at < 1200 px, drop the technician strip to two rows and move the decision buttons into the row.
- Score < 4, **R-Q5, `board` @1280, column "รอ นาที":** the cells show a bare "2". Fix: "2 นาที".
- Score < 4, honesty, **`report.html` "เห็นอะไร":** the options are rewritten ("เสียงดังผิดปกติ", "รั่วหรือหยด (น้ำมัน ลม น้ำ)") and two are added ("ชิ้นงานเสียจากเครื่องนี้", "อื่น ๆ"). The fixture's `NEW_observation_choices` has four options. Use them verbatim, or add new ones to the fixture as NEW_ with a source.
- Score < 4, honesty, **`tech-step-isolation-phaseB`:** it shows "ISO 7010 M021, W012", but `NEW_hazards` contains only W012. It also says "1 จาก 2 รายการ" while the fixture has one isolation point plus one verify. State the derivation, or drop M021.
- Score < 4, demo coherence, **`tech-close` @390:** the demo answer is "ปลดกุญแจของฉันแล้ว", yet the lockout step (2) is not done. A committee member reading closely will see a story that contradicts itself. Use C's case ("งานนี้ไม่ได้ตัดพลังงาน"), or mark step 2 done.
- Best idea to steal: the first screen with a pinned "next N + เริ่มงาน", and the review screen that lists each undone step in full.
- Worst: the board breaks at tablet width.

## B

- The banner wording is the most explanatory: "สัญญาณเครื่องจักรในหน้านี้สร้างขึ้นเพื่อทดสอบ ไม่ได้มาจากเครื่องจริง". The step header shows provenance (T-15). The board is the only one that works at 1024×768 (S-10).
- Score < 4, **R-Q3 consistency plus safety, `tech-close-sign` @390:** the screen says "ยังไม่ได้ทำ 4 ขั้น จาก 6" and lists steps 3-6, with the button "กลับไปทำขั้น 3". `tech-step` and `tech-close` say the job is at step 2 ("ทำถึงขั้น 2 จาก 6"). The summary therefore **omits the lockout step**. A gets this right ("ยังไม่ได้ทำ 5 ขั้น", steps 2-6). Fix: compute the list from the step state.
- Score < 4, **finish / G-06, same screen, step 6:** the text "10 N·m" is printed on top of "แล้ว", so the torque value cannot be read. Fix the number-column layout, then run a text-overlap check on every screen.
- Score < 4, **T-01, `tech-job` @360×640:** "เริ่มงาน" is half below the fold, and there is no "ถัดไป N งาน" on the first screen.
- Score < 4, **S-02, `board`:** there is no per-row "เสนอมาแล้วกี่นาที" (it appears only in the header) and no "กลับไปลำดับระบบ".
- Score < 4, honesty:
  - The report options ("รั่วระบบไฮดรอลิก", "ขนาดชิ้นงานคลาดเคลื่อน") are not in the fixture.
  - The "เลขกุญแจ" field in Phase B has no NEW_ field behind it.
  - "ลงชื่อปิดงาน" implies an electronic signature. The system only records the user and the time, so call it "ยืนยันปิดงาน" unless an e-signature is designed and justified.
- Score < 4, finish, `board` @1920: the heading "ช่างในกะ 10 / คน" wraps. The "ให้คนอื่น" panel is open in the default render, which pushes the lower sections down.
- Best idea to steal: the banner text, and the "ตรวจทานแล้วลงชื่อ" button that stays disabled with "ยังไม่ได้ตอบ: ข้อ 3 สถานะกุญแจ".
- Worst: a confirmation summary that miscounts unfinished steps and hides the LOTO step.

## C

- C uses the fixture most faithfully: the report options match `NEW_observation_choices` exactly, and Phase B matches `NEW_isolation_points` and `NEW_verify_th`.
- The banner covers people's names too: "สัญญาณ ชื่อเครื่อง และชื่อคนในหน้านี้ไม่ใช่ข้อมูลจากโรงงานจริง". This is the best answer to examiner question 5 (how users tell real data from simulated data).
- The board is the strongest information design. Each station carries "ใบงานเปิด N" (L-02) and the buffers read "N คัน · M นาที" (L-01). There is also a per-technician time line (S-07).
- **C-1, red line 3 pending, S-01 (M), `board` @1280/1920, station 4 "สายหยุด" and the legend "สายหยุด":** REQ-S-01 says to use "เกินเกณฑ์" *because the system does not know whether the line actually stopped*. The fixture station state is `over_threshold`, and the proposal says "เครื่องหยุด" (machine, not line). `NEW_line_stopped` has no source in the system, and REQUIREMENTS §6 puts "สถานะสายหยุดจริงจาก Andon" out of scope. As it stands this is a claim the backend cannot make. Fix: "เกินเกณฑ์ · เครื่องหยุด" in the colour C already defines for "เกินเกณฑ์", or name the field and its source in rationale as a proposal. If it is left unfixed into the report, it becomes a red line.
- Score < 4, **S-10 (M), `board` @1024×768:** the symptom column collapses to about 45 px, Thai wraps one word per line, only one row is visible, and the buffer labels collide ("15 คัน · 15 น 0 คัน"). Fix with a breakpoint layout, and commit a 1024 PNG.
- Score < 4, **G-05, `board`, "คาดว่าจะเกิน":** it uses diagonal hazard-tape striping. That reads as an ISO hazard marking, and the striped pattern is reserved for hazards. Use a hatched outline or the amber token instead.
- Score < 4, honesty, `board`:
  - The technician lane labels `est_min` as "มาตรฐาน 60 นาที" / "เวลามาตรฐานของงาน". It is an estimate, not a standard time. Use "ประมาณ 60 นาที".
  - "เลขกุญแจของฉัน" in Phase B has no NEW_ field behind it.
  - The phrase "ใช้ andon หรือวิทยุ" in `report` is a plant-specific assumption. Make it configurable (P-08).
- Score < 4, T-01, `tech-job` @360×640: "ถัดไป 1 งาน" sits at the bottom of a long page.
- Score < 4, G-15 (S): "2 นาที / เสนอ 10:40" is repeated in all six rows.
- Score < 4, AI-look: the rounded segmented-pill navigation and the numbered black square badges "1 2 3" are common in generated dashboards. A square tab bar like A's would avoid that.
- Best idea to steal: the line schematic with buffers and open-ticket counts, the station-first report flow, and the coherent close scenario.
- Worst: "สายหยุด".

## Would it look AI-made?

- **A** looks closest to a deliberate HMI: monochrome, mono numerals, a real table, colour only for exceptions. The risk is that every box looks the same.
- **B**'s paper-form idea is intentional. But the light-blue selected fill, the navy accent and the decorative hatched corner are generic, and the overprinted text is the classic sign that nobody checked the output.
- **C** has the most designed board, but the pill navigation and hazard-tape stripes are recognisable tropes.

## Ranking and verdict

**A > C > B.** All three are buildable; none needs a full redo.

- Build on **A**'s structure, which has the fewest M failures.
- From **C**, take the line schematic, the technician time line, the report flow and the banner wording about names.
- From **B**, take the 1024 layout approach and the disabled-until-answered close button.

## Top 5 fixes for today

1. **All:** write rationale.md now. Include a decision → REQ table, an element → REQ list per screen (no orphans), every NEW_ field used with its source, and the unmet-M list. Without it, traceability cannot pass.
2. **C:** replace "สายหยุด" with "เกินเกณฑ์" wording (S-01), relabel "มาตรฐาน" as "ประมาณ", and drop the hazard-tape striping for predictions (G-05).
3. **A and C:** fix the board at 1024×768 (S-10, M). No horizontal scroll, and pending plus active work visible. Commit the PNG.
4. **B:** derive the "ยังไม่ได้ทำ" list from the step state (steps 2-6, including LOTO), and fix the "10 N·m" overprint. **A and B:** make the demo lock answer consistent with the step state.
5. **A and B:** show fixture data only. Use `NEW_observation_choices` verbatim, remove or justify M021 and "เลขกุญแจ" (in C as well), and put "ถัดไป N งาน" on the first screen in B and C (T-01).

## Fixture issues for the owner (not the designers' fault)

- `finished[].outcome_th` "ไม่พบปัญหา" does not match REQ-T-09 "ไม่พบอาการ". B shows the fixture term and A shows the REQ term, which breaks R-Q3.
- `NEW_line_stopped` has no data source in the system.
- The step text is invented, but it is attached to a real-looking manual ("R-2000iC Maintenance Manual (B-83284EN/09)", pp. 142-147). Verify it against the real manual, or label the page numbers as illustrative, before any screenshot goes into the report.
- `my_job.status` is `in_progress`, but the brief asks `tech-job` to show `assigned`.

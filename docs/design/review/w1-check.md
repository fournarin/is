# w1 check - refresh round 3 + set 3 (independent)

BLOCKERS: none

(Checked all listed PNGs plus all four measure.json files: every record has hscroll=false, minFont 18 on phones, minTap 56 phone / 48 desk. No clipped or overlapping text seen. Desk minFontReal 15 is outside the phone rule.)

## Item A - app /board vs board_calm.py
- A: met. set3/board.390x844.png, board.1280x800.png: line strip, "รอคุณตัดสินใจ 5 เรื่อง", focal card with "ยืนยันให้ สมชาย", one-line rows "name · N คัน" + ยืนยัน, tab row (desk: segmented; phone: stacked list below the rows, board.390.full.png). Drawers (board-drawer.390/1920, board-focal-drawer.1280) contain "ได้งานนี้เพราะ". Wall 1920: type clearly bigger, width 1696 of 1920; content ends at y 877 of 1080, so about 200 px blank below (fills width, not full height).

## Items B1-B7
- B1 line overview (spec): met. spec/line-overview.1920x1080, 1280x800, 390x844, -tip, -drawer: one 8-number strip; plan is the focus (hairline footprints, one lamp bar, light dots, no codes); codes appear only in the tap tooltip ("MC-018 · MC-019"); "สถานีที่ต้องดู 3" is one line per station; drawer opens on tap. Machine list is a "เครื่องที่มีงานเปิด 12 จาก 12" row, not a visible tab (partly, see note 3).
- B2 tech phone: met. round3/set1/tech-job.390x844.png: forecast "ถึงเกณฑ์ราว 17 พ.ย. 21:41 น. ±2 ชม." appears once; status "◆ สูง · ขั้น 2/9". set2/tech-close-locked.390x844.png: one line "กุญแจ ก-11 ยังล็อก CP-3" + "ทำไม" button.
- B3 phone text >= 18 px: met. set3/measure.json all phone records minFont 18 and minFontReal 18; spec board-15@360/390 minFont 18; set1/set2 all 18.
- B4 sticky next at 360x640: met. set2/tech-step.360x640.png: "ต่อไป: ใส่กุญแจของคุณ" bar at the bottom of the first screen; same pattern in -verify and -restore. Lock banner (safety) is visible on those screens.
- B5 wall scale: partly. board.1920x1080.png and board-drawer.1920x1080.png are visibly scaled up and wide; board-15@1920 spec measures minFont 18. Bottom about 20% of the screen is empty. Spec line-overview.1920 is NOT scaled (text about 15-18 px, plan ends at y 708; bottom 350 px empty).
- B6 board polish: met. "พิมพ์ชนก · 135 คัน" (name first); severity word beside the icon on one line; "ยืนยันให้ สมชาย" single space; segmented tab row at 1280 (board.1280x800.png). 1024 shows the chips as separate boxes, 8 px apart, with the last row cut by the fold only (scrollable, not clipped).
- B7 dark-mode rule removed: cannot verify from PNGs. Only ROUNDS.md claims it; nothing in the shots contradicts it (all light).

## Non-blocking notes (worst first)
1. board.360x640.png: the focal card's "ยืนยันให้ สมชาย" button is below the fold (measure primaryBottom 773 at 360x640; the title and "ถ้ารอ" are visible, the confirm is not). At 390x844 it is visible (button ends at 710). Not a blocker per the stated rules, but it is the main decision on the smallest phone. Smallest fix: at <= 640 px height, drop the line-strip sentence (or compact the header to one row) so the button lands above y 640.
2. Phone header on 360 (board.360x640.png): the clock and "ออก"/user wrap onto three rows before the tabs, spending about 140 px before the strip; the cause of note 1.
3. Line overview (spec only, not in the app): machine list is a count row, not the tab the summary asked for; the strip sentence and the right-hand list repeat the station names. Wall 1920 version is not scaled like the board.
4. tech-step-verify.360x640.png: step 4 is "ขั้นตรวจพลังงานเป็นศูนย์" and the sticky link also reads "ต่อไป: ตรวจพลังงานเป็นศูนย์" (same name; presumably the points below the step). Could confuse; consider "ต่อไป: จุดวัด TP-1 / TP-2".
5. The sticky bar covers the last text line of the step card on first view (tech-step.360x640.png, English source excerpt cut); it scrolls away, so cosmetic.

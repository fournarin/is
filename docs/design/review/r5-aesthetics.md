# R5 aesthetics - final GATE 2 re-score (role 6)

Method: I re-ran the Playwright measurements (google-chrome) on all 36 screens: at 360 and 390 for every page, and at 1280/1920 for board, line and eng. For each I checked h-scroll, input clipping, type sizes and weights, amber use, stripes, glyphs, sticky elements and page height. I looked at the fresh PNGs (10:06-10:07) for board-15, line-overview and eng-review at 1920, and took my own 1280 render of eng-review-kind scrolled to the isolation editor. Scores are not rounded up.

## Scores

| Audience | R4 | R5 | Note |
|---|---|---|---|
| Technician phone | 4 | **4** | Unchanged: 18/24/36, weights 400/600, no h-scroll or clipping at 360/390. |
| Operator report | 4 | **4** | Unchanged and clean at 360/390. |
| Board | 3.5 | **3.5 (blocked)** | Desk/wall now reaches 4 (see below). The phone board still pans sideways. |
| Line overview | 3.5 | **4** | Starred fixes verified. |
| Engineer | 3.5 | **3.5 (blocked)** | eng-review now reaches 4. The new isolation editor clips Thai. |

## Fixes verified

- **board-15, 1920:** the page is exactly 1080 tall. The second row line is now about 18 px. Only the top row's "ยืนยัน" is solid; the rest are quiet text buttons with an icon-only ellipsis. The empty bottom cards are folded into the queue header. At 1920 it now reads as a calm ledger.
- **line-overview, 1920:** the page is 1080 tall. Chevrons sit in the gaps, not through the outlines. Markers are lighter (dot in ring). Door arcs make it read as a hall. The machine list is single-line with status chips and all 12 rows fit. The legend swatch now has an outline.
- **eng-review, 1920:** the ↑/↓ hints are inline key caps on one line. The page thumbnail is larger and watermarked "ภาพหน้าคู่มือ (จำลอง)". The gate strip is sticky (stays at 142-214 when scrolled). A hot-surface kind was added.
- **System-wide:** still no amber misuse, left stripes or Unicode arrows; weights are 400/600 only.

## Remaining fixes (ranked)

1. **BLOCKS GATE: board-15, 360/390, queue card chip** "กิตติพงษ์ ส่งต่อ รอคนรับ เครื่องนี้อยู่". This is R4 item 1 and it is not fixed. scrollWidth is 425 at 360 and 447 at 390, and the window scrolls 57-65 px sideways. `white-space` is now normal, but the chip (left edge at 137 px) still does not shrink. Fix: `.chip{display:inline; max-width:100%}`, or put the chip on its own line in the card with `overflow-wrap:anywhere`. Then re-test every page for `scrollWidth == viewport`.
2. **BLOCKS GATE: eng-review-kind, 1280 (and 360), isolation point description input.** It shows "เบรกเกอร์ CP-3 ที่ตู้จ่ายไฟข", cut mid-word (scrollWidth 255 > 205). This is the same "Thai clipped in an edit field" red line as R3. Fix: put the description on its own full-width row (id · description, then energy-type chips on the next line), or use an auto-height textarea.
3. **Non-blocking: eng-review-kind, 1280.** "+ เพิ่มจุดตัด" uses a text "+"; use the Lucide `plus` icon. The kind picker wraps to two rows of six chips, which is acceptable but would look calmer as one segmented row at ≥1440.
4. **Non-blocking: line-overview, 1920, station 4 in the plan.** The ringed markers on the amber tint look washed out. Give the ring a 1 px ink outline.
5. **Non-blocking: board, 1920, people panel.** Its meta text is still 15 px. That is acceptable for secondary information, but consider 17 px on the wall.

## Verdict

**FAIL as delivered, by two small, mechanical defects.** Both are red-line defects (off-screen and clipped Thai), and each sits on an audience that otherwise now scores 4. With fixes 1 and 2 applied and verified (the h-scroll check and the input `scrollWidth <= clientWidth` check on all screens at 360/390/1280), I would score all five audiences 4/5 and **pass GATE 2**. No further design change is needed for the gate.

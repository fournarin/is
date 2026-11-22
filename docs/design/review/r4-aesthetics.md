# R4 aesthetics re-judge - Phase 2 design system, 36 screens (role 6)

Method: I re-measured live HTML with Playwright (google-chrome) on all 36 screens at 390, at 1280 for desk pages, and at 1920 for board, line and eng-review. For each I recorded computed font sizes and weights, every element painted in amber, left-stripe borders (also on `::before` and inset shadow), Unicode arrows and shapes, input clipping, nowrap truncation, and page width and height. I checked the PNGs against the HTML (both 23:43-23:44) and looked at: line-overview 1280/1920, eng-review 1920, an eng desk contact sheet (health, audit-closed, review-kind, queue, gaps, loops), board and board-15 1920, a 390 sheet (report ×3, sign-in, tech-job, tech-step, unreachable, line, board), and my own render of board-15 at 390. Gate rule: every audience must score ≥ 4. Scores are not rounded up.

## Per-audience scores

| Audience | R3 | R4 | Why |
|---|---|---|---|
| Technician phone | 4 | **4** | Unchanged and still the best part of the set: 18/24/36, weights 400/600, Lucide icons, ISO signs only on the isolate step. |
| Operator report | 4 | **4** | report, report-manual and report-states at 390 are calm and tappable with clear required/optional labels. Small wraps remain: "ผู้แจ้ง / มาลี" in the header and "เปลี่ยน / เครื่อง" in the station button. |
| Board (desk/wall) | 3 | **3.5** | Cleaner, but it does not yet meet its own README intent ("read from 3 m on the wall"). Details below. |
| Line overview | 3 | **3.5** | The station strip is now excellent: buffers sit on an axis below it, and each card is MC id + status. The floor plan is now real geometry but still looks like a slide diagram. |
| Engineer | 2.5 | **3.5** | Big leap. eng-review is now near Linear quality: blocker bar with the approve action at the top, page tabs, "หน้าต่างใหม่", textarea, step-kind control. One visible layout bug on the flagship page keeps it below 4. |

## What improved (verified by measurement)

- **Type scale:** mobile uses only 18/24/36, desk adds 15 and 30. Weights are 400/600 only; 900, 700, 17 and 20 are gone.
- **Amber:** amber now marks only over-threshold (solid or tint) and forecast (outline): board `.s.over`, `.sw.over`, line `.lamp`, and the ISO warning sign. The test chip, stale strip, reassurance box and mismatch are all re-treated. Item 15 is done.
- **Callouts:** no left-stripe callouts were detected on any screen. They are now one style (surface + Lucide icon + bold label). Item 17 is done.
- **Unicode:** no ↑↓→▾ characters remain in text (only "≥" in the components spec). The board-15 handover white block is gone, components swatches wrap normally, and the eng tabs no longer wrap to two rows at 390.
- **No input clipping** on any screen. The eng-review step-6 Thai is in an auto-height textarea, so the R3 red line is cleared.
- **sign-in:** the station-squares wordmark (8 squares, #4 lit) is a real brand device tied to the strip. It now looks designed.
- **Engineer desk tables** (health, loops, audit-closed, queue) have consistent columns, right-aligned figures and a quiet hierarchy.

## Remaining issues, ranked (minimum set to reach 4/5 per audience marked ★)

1. ★ **board-15, 390, queue cards.** The chip "กิตติพงษ์ ส่งต่อ รอคนรับ เครื่องนี้อยู่" is nowrap and makes the page 447 px wide, so the whole phone board pans sideways and the cards are cut on the left. Fix: let the chip wrap or ellipsize, and set `max-width:100%`. This is a "Thai cramped / off-screen" red line on the phone board.
2. ★ **board and board-15, 1920, the second row line** (machine · station · reason, 620+ text nodes at 15 px). It is unreadable at 3 m and contradicts README line 34. Fix: 17 px minimum at ≥ 1600, or drop that line on the wall and keep it on hover or in the drawer.
3. ★ **board and board-15, 1280/1920, decision column.** Up to 15 identical grey "ยืนยัน" buttons plus "··· อื่น ๆ" form a wall of buttons, and it is the heaviest element on the screen. Fix: keep only the focused or top row solid, render the rest as quiet text buttons, and make "อื่น ๆ" an icon-only ellipsis with an aria-label.
4. ★ **board-15, 1920.** The page is 1288 px tall on a 1080 wall, so the 15th row and the bottom panels are cut. Fix: cap the visible rows and add "+N ใบ" (or a dense row height) so the wall never scrolls.
5. **board, 1920, bottom band.** The three cards have unequal content ("หมดเวลา 0 ใบ" is mostly empty next to the full lock card). Fix: fold the empty states into one line in the queue header.
6. ★ **line-overview, 1280/1920, floor plan.** The conveyor chevrons are drawn through the station outlines (x≈250/400/548 at 1280). The 12 px black dots outweigh the labels, labels sit jammed in the box corners, and the aisle band is dead space. Fix: put chevrons only in the gaps, use 8 px markers with labels on one baseline, shorten the aisle band, and add hairline doors or machine footprints so it reads as a hall rather than a flowchart.
7. ★ **line-overview, 1920.** The page is 1302 px tall, so the machine list continues below the fold on a wall. Fix: single-line list rows (machine · station · job · status) at about 40 px, so all 12 fit beside the plan. At 1280 the plan starts at y≈570; consider plan and list side by side from 1280.
8. **line-overview, 1920, legend.** The "ไม่มีสัญญาณเกินเกณฑ์" swatch is lamp-off on andon and nearly invisible. Fix: add a 1 px on-andon-2 outline.
9. ★ **eng-review / eng-review-kind, 1280/1920, side panel footer.** The ↑ and ↓ Lucide icons stack on two lines with the text on a third. Fix: inline `kbd`-style key caps on one line ("↑ ↓ เปลี่ยนขั้น"). Also hide the textarea resize grip on step 6, since it auto-grows.
10. **eng-review, 1920, page thumbnail "ภาพหน้าจริง".** It is too small to read and looks like a placeholder. Fix: make it 160 px wide, or drop it until real page images exist (README known gap).
11. **Minor:** a 3 px radius remains on board 390/1280; unify to 4 px.

## Verdict for GATE 2

**FAIL under the owner's gate rule.** Board, line overview and engineer are at 3.5. Technician phone and operator report pass at 4.

The minimum changes to reach 4/5 for every audience are the ★ items:
- **Board:** 1-4 (overflow at 390, 17 px wall text, quiet decision column, no wall scroll).
- **Line overview:** 6-7 (a cleaner plan drawing, and plan + list fitting one wall screen).
- **Engineer:** 9 (fix the stacked key hint).

These are focused CSS and layout changes, not a redesign. The system itself (tokens, amber discipline, callouts, icons, type) now holds together, and I would expect a pass on a re-check once the ★ items are in.

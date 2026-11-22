# Round 5 (GATE 2 final re-check) - 2 blockers left (Cowork, 2026-11-16 10:40)

r5-aesthetics.md: technician 4, operator report 4, line overview 4 (up), board 3.5, engineer 3.5 -
both blocked only by the two items below; with them fixed all five audiences = 4 (judge).
r5-check.md: 9 PASS / 1 PARTIAL / 1 FAIL; regression sweep over 36 screens clean.

## [M] Blockers
1. board-15 at 360/390 still scrolls sideways (scrollWidth 425 / 448): the chip
   "กิตติพงษ์ ส่งต่อ รอคนรับ เครื่องนี้อยู่" in td.rs is nowrap. Let it wrap (display:inline;
   max-width:100%; white-space:normal) or put it on its own line. The round-4 claim "no h-scroll"
   was wrong - measure scrollWidth on board-15 itself at 360 and 390.
2. eng-review-kind (1280 and 360): the isolation-point description input clips Thai
   ("…ตู้จ่ายไฟข", scrollWidth 255 > clientWidth 205). Full-width row or auto-height textarea.
Then add an automated check to render.py: every page x viewport fails if
documentElement.scrollWidth > innerWidth, or any input/textarea has scrollWidth > clientWidth.

## Non-blocking (Phase 3)
- board-15 with a mouse: 5 px between buttons (desk rule); hybrid touch laptops report
  pointer: fine - consider any-pointer: coarse.
- pdfpage.swift is macOS-only; Lucide plus icon; marker ring on amber; 15 px in the people panel.
- eng-audit-closed snapshot steps + A4 (round 4 item 10).

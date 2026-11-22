# GATE 2 blockers - direct verification (Cowork, 2026-11-16 10:25)
Measured in the cloud with Chrome + Playwright, file:// from design/system/screens, twice per
viewport: with the woff2 web fonts loaded (document.fonts.ready; Plex Looped 400/600 loaded) and
with all .woff2 requests blocked (fallback font).
| check | 360 | 390 | 1280 |
|---|---|---|---|
| board-15 page scrollWidth (webfont / fallback) | 360 / 360 | 390 / 390 | - |
| eng-review-kind page scrollWidth (webfont / fallback) | 360 / 360 | 390 / 390 | 1280 / 1280 |
| clipped inputs/textareas (any page above) | 0 | 0 | 0 |
Both blockers FIXED. The only elements past the viewport on eng-review-kind at 360/390 are the
engineer tabs inside the nav's own horizontal scroller (overflow-x:auto) - intended.
New, non-blocking (engineer screens are desk-first): at 360 the "อนุมัติไม่ได้ · 4 ข้อ" gate strip in
eng-review-kind squeezes its blocker list into a narrow column (one Thai word per line). Fix in Phase 3:
stack the gate strip vertically below 600 px. Screenshot: G2-eng-kind-360.png (sent to the owner).

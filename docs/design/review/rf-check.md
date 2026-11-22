# Visual refresh check (Q13) - app re-captures + spec dark wall theme

Method: Playwright on the 14 SSR snapshots in `refresh/set1|set2/pages/` (360x640, 390x844, 1280x800 = 42 renders), closed state, then each sheet opened on its own; PNGs and measure.json for the spec screens. The first sweep with every `<details>` open at once gave ~40-90 false "overlaps" per page (open sheets are fixed overlays), so I discarded it.

## Phone rules, closed state: PASS (one note)
Text min 18 px, taps min 56 px high, 0 gaps under 8 px, 0 h-scroll, 0 split Thai words, 0 clipped text, 0 external requests, 0 emoji, contrast min 7.05 (set1: amber chip with dark text) / 7.90 (set2). Primary above 640 at 360x640: tech-job 575, tech-job-two 567, tech-step-normal 628, tech-handover 632 (sticky); tech-noplaybook first action 570-636 (4 px margin, was 790); tech-manual primary 1297 (back button on top); tech-step-hot-done 888 (declared, unchanged).
Note: tech-handover's sticky bar covers 9 px of the last visible form line at rest (overlap 1-2 lines at 390). Not a failure, but add bottom padding or a fade.

## Sheets (detail behind a tap)
| Item | Verdict | Evidence |
|---|---|---|
| Opens as bottom sheet (phone) / right drawer (1280) | PASS | Panel 360x370 at bottom at 360x640, 480 px wide at right at 1280; no h-scroll when open |
| Visible close button | PASS, width short | "ปิด" is 50 x 56 px (width under 56) |
| Tap outside closes | PASS | Summary is the fixed full-screen backdrop; clicking it closes all 11 sheets tested, with no JS needed |
| Focus moves into the sheet and back | **NOT VERIFIABLE / FAIL as captured** | Snapshots have 0 `<script>`. After opening, focus stays on the (children-hidden) summary; nothing moves into the panel. |
| Escape closes (desk) | **NOT VERIFIABLE / FAIL as captured** | Escape does nothing at 1280 in the snapshots |
| "ปิด" button closes | **NOT VERIFIABLE / FAIL as captured** | `<button type="button">` has no effect without hydration; the sheet stays open |
| Reduced motion | PASS | `prefers-reduced-motion: reduce` emulated: panel and backdrop animation 0s / none (normal: 0.18 s) |
| Safety-critical detail not behind a tap | PASS | Sheets hold only history, the ranking reason + disagree form, and the all-steps list. Lock strip (y=97-111), signal words and ISO signs are outside any `<details>` on every set2 page; the close/handover lock questions are plain fieldsets. |

The last three need hydrated captures (or a run against the live app): the SSR files cannot show JS behaviour. The summary also loses its accessible name while open (children are `visibility:hidden`), so a keyboard user who lands on it hears nothing.

## Dark wall theme (1920)
- spec/measure.json: 25 records, min contrast 7.05 (dark text on the amber "เกินเกณฑ์" cell, both themes), next lowest 9.28 (secondary text (180,188,198) on (21,24,29)); no clip, no split, no overlap, no gaps under 8 px below 1200.
- My pixel sampling of `board.1920x1080.png` and `line-overview.1920x1080.png`: body text (242,244,247) on (21,24,29) = 16.2:1, on (11,13,16) = 17.7:1. PASS (>= 7:1).
- Caveat: `system/screens/*.html` render light at 1920 (no `body.wall`), so dark is evidenced from PNGs and measure.json only.

## Regression vs earlier checks
- Fixed since set 1/2: offline top bar no longer clips the station name (chip "หลุด" only); noplaybook fold; board-15 no h-scroll at 360/390 (spec measure: false, my run: 0 px).
- Still true: board-15 button gaps are 5 px at 1280/1920 (desk exemption); a W017 "ข้อควรระวัง" hot step is now shown on tech-step-hot, DC-bus wait "อันตราย" on tech-step-wait-dc.
- Tokens: sizes 18/24/36 and weights 400/600 only; colours match tokens.

## Verdict
CONDITIONAL PASS. Visuals, phone rules, reduced motion, backdrop-close and the dark contrast hold, and nothing safety-critical is hidden. Before sign-off: capture the hydrated app to prove focus-in/return, Escape and the "ปิด" button; widen "ปิด" to 56 px; keep an accessible name on the open backdrop.

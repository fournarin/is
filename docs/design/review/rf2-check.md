# Refresh round 2 check (Q14)

Method: Playwright on the 14 SSR snapshots (set1 x5, set2 x9) at 360x640, 390x844, 1280x800, closed state, plus single-sheet tests; spec screens are PNG + measure.json only (no spec HTML in `refresh/`), so board checks are from those.

| Item | Verdict | Evidence |
|---|---|---|
| One light theme, no dark | PASS (dead rule) | Rendered body, `.v2` and every PNG are light, also with `color_scheme=dark` (page stays light; the 1920 spec PNGs are light). The legacy `@media (prefers-color-scheme: dark)` rule still ships and only repaints the bare `<body>` behind `.v2`. Remove it. |
| App phone rules (42 renders) | PASS | Text min 18, taps min 56, gaps 0 under 8 px, 0 h-scroll, 0 clipped, 0 Thai splits, contrast min 7.05 / 7.90 |
| "ปิด" width | PASS | 56 x 56 (was 50 x 56) |
| Primary above 640 at 360x640 | PARTIAL | Good: tech-job 548, tech-job-two 556, step-normal 628, handover 632, noplaybook first action 570-636. **Below the fold:** tech-step 1040, hot 888, hot-done 888, verify 952, wait-dc 870, restore 792, manual 1297. Builder declares only hot-done. These are the "ทำขั้นนี้แล้ว ถัดไป" buttons, disabled until the points/wait are confirmed, so the thing to tap is the point tile; the tiles are not in the SSR markup, so I cannot place them. Acceptable for hot-done and wait steps (nothing to do but wait); not shown to be acceptable for the isolation step, whose first tile is likely also below 640. |
| Sticky handover bar | PASS, minor | 1-2 form lines sit under the bar at rest (9-15 px overlap) |
| Board first screen | PASS (PNG) | 390: header, 8-number strip + one sentence, "รอคุณตัดสินใจ 7 เรื่อง", focal card, "ยืนยันให้ วิชัย" ends 666. 1280: strip + queue only; people/held/finished are counts behind tabs, with the people drawer in `board-expand`. No KPI strip. |
| Tap opens the reason drawer | PASS (PNG, claim) | `board-drawer.1280x800` shows the drawer (ที่ไหน / ทำไมก่อน / สถานะ / ถ้ารอ / ระบบเสนอ / ใบงาน + actions) with "ปิด". Rows are `details/summary` per ROUNDS; I cannot tap the spec page. |
| Board phone text >= 18 | **FAIL** | spec measure.json: board@390 minFont **15** (142 text nodes at 15 px), board-15@390 and @360 the same (287 nodes). Earlier rounds measured 18 on phone. Phone rule broken on the new phone board. |
| board-15 at 360x640 below fold (778) | ACCEPTABLE | It is the capacity test (15 copies), not the shipped board; the real board at 390 is 666 |
| Floor plan pan on phone | ACCEPTABLE | line-overview@390 hscroll false; the 960 px plan pans inside its box as declared |
| Safety-critical behind a tap | PASS | Sheets hold history, ranking reason + disagree form, all-steps list. Lock strip, signal words, ISO signs and lock answers are outside any `<details>` |
| sheet-behaviour.txt (20 checks) | PLAUSIBLE | Reproduced on SSR: panel animation 0.18 s, 0 s under reduced motion, "ปิด" 56x56, a tap on the dimmed backdrop closes (CSS-only). Enter / focus-in / Escape / focus-return / backdrop name / "ปิด" closes need JS; the markup shows no script and no static `aria-label`, consistent with them being set at runtime. Not independently proven here. |
| spec/measure.json (42 records) | PASS except board font | contrast min 7.05 (dark text on amber), taps 56 / 48, no gaps under 8 below 1200, no clip, split or overlap |

## Verdict
CONDITIONAL PASS. One new regression: the phone board uses 15 px text (spec measure.json). Fix before the board is built in set 3. Also drop the dead dark-mode rule, and either pull the isolation step's first tile above 640 or declare that those steps sit below the fold.

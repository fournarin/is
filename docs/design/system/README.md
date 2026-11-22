# Design system and screen specs - Phase 2 (concept V), GATE 2 fix round

Concept V (GATE 1, 2026-11-15) grown into a design system: tokens, rules, components with their states, and
every screen at the viewports its users have. Everything is generated from one source, rendered in Chrome and
measured. This version answers `design/review/round3-summary.md` (items 1-20), `r3-aesthetics.md` and
`r3-engineer.md`, with beauty first (owner, Q12).

- **Start here:** `spec/index.html` (one page per screen family: users, REQ IDs, every state with renders,
  measured values) and `screens/components.html` (tokens and components).
- **Build (relative paths, runs from any copy of `design/`):**
  `cd _src && PY=../../../tools/pw313/bin/python && $PY build.py && $PY render.py && $PY spec.py`
  (Python 3.13 + Playwright, Chrome via `channel='chrome'`, pages open as `file://`, no server).
  Manual page images: `swift pdfpage.swift ../../data/r-2000ic-maintenance.pdf <page> ../assets/r2000ic-p<page>.png 1.25`
  (macOS PDFKit; the PDF is the repo's synthetic corpus, copied into `design/data/`).
- Data: `design/data/fixture.json` (every `NEW_*` key has a line in `NEW_field_sources`), `design/data/eng-seed.json`
  (the demo seed's API output for loops/health), `design/data/r-2000ic-maintenance.pdf`.

| Path | What |
|---|---|
| `_src/base.py` | tokens (`CSS_BASE`), callout, Thai word breaking, Lucide icons, ISO signs, priority marks, `page()` |
| `_src/phone.py`, `report.py`, `shell.py` | technician, operator, sign-in / cannot-connect |
| `_src/board_calm.py` | shift-lead board since Q14 (phone, tablet, desk, wall) + 15-row capacity test |
| `_src/board.py` | the Q13 board, no longer built; kept for its history |
| `_src/desk.py`, `eng.py`, `line.py` | desk shell; engineer screens; line overview with floor plan |
| `_src/printsheet.py`, `components.py`, `render.py`, `spec.py`, `pdfpage.swift` | A4 sheet; gallery + tokens; measure; spec pages; page images |
| `screens/` (36 pages), `png/`, `spec/`, `assets/` | outputs; `png/measure.json` = 119 page x viewport records; `png/summary.json` |

## Round 3 (2026-11-17) - calm line overview, wall scale, board polish (ADR-141)

- **Line overview** (`line.py`): the board's number strip on top - station numbers appear there only; the plan
  is the one focus (hairline footprints, the lamp bar the only colour, light machine dots, no codes); a tap or
  focus on a station shows its name and machine codes; "สถานีที่ต้องดู" is one line per station opening a drawer;
  machines with open work sit behind a tab. Fits 1080 at 1920. Variants `-tip`, `-drawer` at 1280.
- **Board** (`board_calm.py`): phones 18 px (`--t1`), wall >= 1600 px type x1.25 and 1760 px wide, name before
  number, severity word on the title baseline, one segmented tab row >= 1200 px (8 px apart below).
- **render.py**: a node `checkVisibility()` reports hidden never counts (font floor, contrast, overlap).
- The board is now built in the app (`repo-v2/web/app/board`); the line overview stays a design (FINAL PLAN).

## Q14 (2026-11-17) - one light theme, and a board that asks first (ADR-140)

The owner's correction to the refresh below: **no dark theme anywhere**, and the board's first screen shows only
what the shift lead must decide now. Where the Q13 text below says "dark on the wall", read "light".

- **Board** (`board_calm.py`): a compact line strip (numbers lit by state, one sentence naming the stations over
  or forecast), then "รอคุณตัดสินใจ N เรื่อง": one focal card (what, where, cars lost if it waits, whom the system
  proposes) and one line per other item. People, held by the system, set aside, finished and locks sit behind
  tabs that open a drawer, each with a one-line count. Reading order: what needs me, line status, people.
  Names first, codes only in the drawer, one number per row. A tap (not hover) opens every row's drawer.
- **Line overview** (`line.py`): light; hairline footprints with the lamp the only colour; the stations that
  need a look beside the plan on a desk and above it below 1200 px; the machines with open work below.
- **Engineer gaps** (`eng.py`): one calm list in place of four cards.
- Renders: `shots/v2/refresh/spec/` (board variants drawer, menu, undo, stale, expand at 1280).

## Visual refresh (Q13, 2026-11-16) - intent per screen group, written before building

Target: the calm of Vercel's dashboard and Apple's own apps, still a factory tool. What stays: safety behaviour,
ISO signs, colour only for state, 18 px on phones, 56 px targets, Looped Thai, the andon plate and lamps.
What changes is carried by tokens and components, so every screen moves together.

- **Phone, technician (light, sunlight).** One job, one decision per screen. Each block shows its essentials
  in <= 2 lines; the rest - why it is ranked here, the last jobs' notes, every step - opens in a bottom sheet
  that slides up over a dimmed page (180 ms, none with reduced motion). Grouped white surfaces on a pale
  canvas, 12 px corners, hairlines between rows, no box inside a box. Codes and figures in Plex Mono.
- **Close and handover forms (light).** Numbered questions with air between them; one tile style; the last
  decision sticky under the thumb. Nothing new on screen - less ink around the same questions.
- **Shift-lead board (dark on the 1920 wall, light on a 1024/1280 desk).** A wall is read from three metres:
  black canvas, lamps as the only colour, each queue row two lines - what and where, then cost and the
  proposed person. The reason and the evidence show on hover (desk) or in the drawer on a click; nothing is
  cut off with an ellipsis any more.
- **Engineer desk (light).** Review is reading: each drafted step is two lines (Thai with its marks and page
  on one line, the manual's English on the next); the evidence column carries the detail.
- **Line overview (dark on the wall).** The same lamps as the board, the floor plan in hairlines, the machine
  list as two-line rows.

**Honest comparison.** Vercel: monochrome with one status colour, hairlines, mono for identifiers - this
matches after the refresh; it is denser than Vercel because a shift board has to show a shift at once.
Apple: grouped lists, sheets, generous type contrast - phones match in structure; Apple's type scale has more
steps, ours stays 18/24/36 (+30 for wall headings) because 18 px is the floor in gloves. Neither ships ISO
safety signs or andon lamps; those are ours and stay louder than anything around them, on purpose.

## Design intent per screen group (written before the GATE 2 fix round, Q12)

- **Technician phone.** One job, one next action, under the dark station plate that says where on the line you
  are. Calm grey canvas, white work surface, one ink button, nothing coloured unless a machine is over its
  threshold. You open it because it is faster than calling the lead: step, page, lock state, done.
- **Shift-lead board (desk, wall, tablet).** A quiet ledger, not a dashboard: the line lit only by state, then
  the queue as two-line rows of real sentences, one strong button for the system's first choice. No cards, no
  outlines, no colour that does not mean "over threshold" or "forecast". It should read from 3 m on the wall
  and feel like Linear's issue list at the desk.
- **Line overview (wall).** A drawing of the hall, not a chart: the conveyor, the station footprints, the
  machines where they stand, the aisles, the maintenance room. Grey everywhere except the stations that need
  someone. Beside it, the plain list of machines with open work, so the wall answers "where do I walk".
- **Engineer.** A careful review desk: steps on the left, the actual manual page on the right, only the
  numbers being compared marked, the approval state and its blockers always in the first screen. Safety
  marks are set here and nowhere else. It should feel like a good code-review tool - precise, unhurried.
- **Shell (sign-in, cannot connect).** One centred lockup, generous space, one action. When the network is
  gone the screen says what still works and what is kept, before it explains why.

## Foundations

**Colour.** Canvas `#EEF0F2`, surface `#FFFFFF`, sunk `#E2E5E9`, ink `#111418` (text and the one action colour),
ink-2 `#3D434B`; andon plate `#16191D`, unlit lamp `#2A2F36`. Amber `#E8890C` means only *over threshold*
(solid) and *forecast* (outline). Red `#A3121A` = critical priority, error icons and the "อันตราย" panel.
Green `#1E6B3A` only in small "done" icons. Stale data is an ink strip, test data a neutral chip, a text
mismatch a red underline - none of them amber. Every text pair >= 7:1 (minimum 7.05, ink on amber).

**Type.** IBM Plex Sans Thai Looped 400/600 only (87 KB/page), weights measured 400 and 600 on every screen.
Scale 15 / 18 / 24 / 36, plus 30 for the board clock - measured, nothing else on screen. Phones (and desk pages
below 700 px) >= 18 px. Wall board (>= 1600 px): both lines of every queue row are 18 px (read from 3 m), also
when the queue is dense; the people timeline and side panels 15 px. Print >= 10.5 pt.

**Thai line breaking.** Build-time `Intl.Segmenter('th')` + a glossary of plant compounds; each word is a nowrap
span; codes (MC-, WO-, CP-, ก-, R-2000iC, Wi-Fi) and number + unit stay together. render.py checks that no word
is drawn on two lines.

**Space and shape.** 4 / 8 / 12 / 16 / 24 / 32 / 48. Radius 8 for surfaces, 4 for chips and inner boxes. Separation
by surface tone and space; outlines only on inputs.

**One callout.** White surface, a leading 20 px Lucide icon whose colour carries the meaning (red alert, green
check, ink lock, grey info), the key word in bold. No coloured stripes anywhere (`base.callout()`).

**Icons.** Lucide 1.49.0 (ISC License, Copyright (c) Lucide Icons and Contributors), inline SVG, notice in every
page; no Unicode arrows or glyphs; no warning triangle outside ISO signs.

**ISO signs.** Only on steps the engineer marked: isolate = M021 + W012 + "อันตราย"; hot surface = W017 +
"ข้อควรระวัง"; restore = no sign. 48 px fixed column. Drawn to ISO 3864 geometry; official artwork in the build.

## Screens

| Family (spec page) | Pages | Viewports | Main REQs |
|---|---|---|---|
| งานของฉัน `tech-job` | tech-job, tech-job-empty, tech-noplaybook | 360, 390, 1280 | T-01, T-02, T-15, H-08 |
| ทำขั้นตอน `tech-step` | tech-step (isolate), -hot, -normal, -restore, tech-manual | 360, 390, 1280 | T-05, T-06, H-01..H-06, H-13 |
| ปิดงานและส่งต่อ `tech-close` | tech-close, -locked, -confirm, tech-handover, tech-states | 360, 390, 1280 | T-08, T-10, H-06, G-10 |
| ใบงานพิมพ์ `tech-print` | tech-print (+ png/tech-print.pdf, 1 page) - print only | A4 | T-14 |
| แจ้งซ่อม `report` | report (QR 3 taps), report-manual (5 taps), report-states | 360, 390, 1280 | P-01..P-08 |
| กระดานกะ `board` | board (+ menu, undo, drawer, stale, expanded reason), board-15 | 390, 1024, 1280, 1920 | S-01..S-10, L-04 |
| ภาพรวมสาย `line-overview` | strip + drawn floor plan + machine list | 390, 1024, 1280, 1920 | L-01..L-04, Q5, Q7 |
| ตรวจร่าง `eng-review` | queue, mismatch (step 6), not found (step 7), kind marking (step 1), unsaved, confirm | 390, 1024, 1280, 1920 | E-01..E-07, E-13, E-14, Q9 |
| หน้าวิศวกรอื่น `eng-other` | gaps, loops, health (populated + too short), notes, audit (in progress + closed) | 360, 390, 1024, 1280 | E-08..E-12 |
| เข้าระบบ / เชื่อมต่อไม่ได้ `shell` | sign-in, sign-in-error, unreachable-wifi, unreachable-server | 360, 390, 1280 | I-04..I-06, P-08 |

## Round 3 items - what changed (all re-measured)

1. **Step kinds (Q9) in the engineer review.** Each step carries a kind chip; a keyword guess is labelled
   "ระบบเดา · ตรวจเอง" and blocks approval until confirmed; the panel has the kind control (ปกติ / ตัดพลังงาน /
   พลังงานสะสม รอ / ตรวจว่าไม่มีพลังงาน / คืนพลังงาน) with isolation points, ISO code and signal word
   (`eng-review-kind.html`). Kinds show in the audit snapshot. Lockout/restore drafts go to a second reviewer (จป.).
2. **Failed evidence never counts as seen:** not-found and mismatch steps show "หลักฐานไม่ผ่าน" / "ตัวเลขไม่ตรง".
3. **Approval state in the first screen:** the gate strip (blockers + disabled approve) ends at y=264 (1280) and 239 (1920).
4. **Edit field:** an auto-growing textarea replaces the line (no duplicate Thai line).
5. **360x640 folds:** sign-in-error 534, unreachable 288, eng-review-queue 388 (were 659-686).
6. **Reproducible build:** relative paths; data and the PDF inside `design/data/`. PM overdue: health counts
   overdue PM jobs (MC-001 = 1 job), the board says the job is 2 days late - the same fact, now labelled per column.
7. **S-01 counted on proposals only (handover row excluded):** 15-row test = 15 of 15 at 1920x1080, 10 at 1280x800.
8. **Confirm dialog:** what technicians get (7 steps, 1-6 and 8; safety-kind steps cannot be cut), each open WO
   (WO-000111 not started - gets revision 4; WO-000101 mid-job at step 2 - keeps revision 3 until closed), a tick.
9. **Gaps:** nav tabs 8 px apart; touch gap rule applied to every viewport below 1200 px, and on touch screens of
   any width by `pointer: coarse` (round 4, item 5).
10. **Sources:** every `NEW_*` key name has a line in `NEW_field_sources`.
11. **MC-018:** "ล็อกนิรภัยแจ้งประตูเปิด" (what the interlock reported); no "machine stopped" anywhere.
12. **S-10 at 1024:** the band shows "กำลังทำ" with each person and machine (y=189) above the queue.
13. **No developer strings** (API, `<table>`, Q11, fixtures/corpus, playbook_snapshot); engineer dates carry the year.
14. **Populated states:** machine health over 120 days with the failure/MTBF definition; closed WO-000042 with
    two work segments, wait, lock state and note.
15-20. Amber discipline, 15/18/24/36 scale and 400/600 weights (measured), one callout without stripes, Lucide only,
    handover fade on its own background, engineer tables calmer with only compared values marked, real page image
    + page tabs + open in new window, drawn floor plan with machine list.

## Round 4 items (round4-summary.md) - what changed

1. board-15 at 360/390 now rendered and measured: chips wrap inside the card, no horizontal scroll.
2. Page images say "ภาพหน้าคู่มือ (จำลอง)" and carry a watermark baked into the PNG ("ตัวอย่าง · คู่มือจำลอง ·
   SYNTHETIC"), so the image is labelled even when opened in its own window.
3. Step kinds include "พื้นผิวร้อน รอให้เย็น"; isolation points are editable (id, where, energy type, remove, add).
4. The approval gate is sticky at the top of the page; the evidence panel docks under it.
5. Queue buttons: on touch (`pointer: coarse`, any width) dense rows are 57 px, so the buttons of two rows sit 9 px
   apart; with a mouse (`pointer: fine`: wall, desk) dense rows are 53 px. The width-only exemption is gone.
6. Wall board: both row lines 18 px; one strong "ยืนยัน" (the system's top row), the rest quiet text buttons that
   turn solid on hover; "อื่น ๆ" is an icon with an accessible name; the synthetic banner becomes a header chip;
   empty "หมดเวลา" and "ล็อกอยู่" fold into the queue header; in dense mode held/set-aside fold there too.
7. Line overview: flow arrows only between stations, 9 px machine markers with a hairline footprint and the label
   on one baseline, a 2 m aisle, door swings on the wall; machine list one line per machine with a status chip;
   1920 fits 1080 with plan and list side by side; the "no signal" legend swatch has an outline.
8. Engineer: key hint as key caps on one line; 160 px page thumbnail; the textarea has no resize grip.
9. Confirm button: "ส่งให้ จป. ตรวจก่อน · คุณอนุมัติหลัง จป.".
10. Not done (should): the snapshot steps and A4 print for the closed WO-000042 - Phase 3.

## Round 5 blockers (round5-summary.md) - fixed and checked

1. board-15 phone: chips (and tags) are plain inline text on phones, so a long chip wraps between words. Measured
   scrollWidth = viewport at 360 and 390, with the web font and with it blocked (fallback font: 360/390).
   The round-4 "no h-scroll" claim held on this Mac only because the font loaded; the new fallback-font pass covers it.
2. eng-review-kind: the isolation-point description is a full-width auto-height textarea under the id / energy
   row; every input and textarea shows its full text (scrollWidth = clientWidth at 360 and 1280).
3. render.py now fails a record when the page scrolls sideways or any input/textarea clips its text, and runs a
   second pass on every phone page with the Thai web font blocked (`png/fallback-font.json`: 68 records, 0 fail).

## S-01 and S-10

| Test | Required | Measured |
|---|---|---|
| `board-15.html` (6 fixture + 9 copies, labelled), proposals fully above the fold at 1280x800 | >= 8 | 9 (mouse), 8 (touch) |
| same at 1920x1080 | 15 | 15 with no page scroll, 1080 px (mouse); 14 on a touch wall (57 px rows) |
| real fixture at 1920x1080 | no page scroll | 1080 px |
| 1024x768 tablet: in progress and queue on the first screen | both | in-progress line y=189; queue below, 5 of 6 proposals |
| 390x844 phone: numbers first, confirm the first job | should | numbers band; first "ยืนยัน" ends at y=791 |

Dense mode (queue > 10, >= 1200 px): compact band, 22 px line boxes, 18 px rows at the wall, side panels folded
into the queue header.

## Measurement - 119 page x viewport records, all pass

Checks per record: horizontal scroll; min font; contrast of every text/background pair; tap targets (56 px on
phones, 48 px desk/tablet); gaps < 8 px between targets below 1200 px; fixed elements over content; text over text
(lines as 1.24 em around their centre, clipped by their overflow container); Thai words on two lines; where the
primary action ends. Results: contrast min 7.05; phone text >= 18 px; targets 56/48; no horizontal scroll (the A4
sheet is print only), overlap, close touch targets or split words. A4 = 1 PDF page.

## Benchmarks - honest comparison after this round

- **Technician phone vs MaintainX / Apple HIG:** calmer and more Thai-first than MaintainX; provenance and lock
  state clearer. Apple-level motion and haptics are not part of a static mock.
- **Board vs Linear:** the same quiet ledger idea (two-line rows, one strong action, no cards); Linear is denser in
  keyboard affordances, which this mock does not show yet.
- **Line overview vs WinCC Unified / FactoryTalk Optix:** now draws the hall (conveyor, footprints, machines,
  aisle, rooms) and keeps colour for state only; the HMI products animate live flow, which needs real signals.
- **Engineer review vs Stripe/Linear-quality tools:** a precise review desk (page tabs, real page image, gate strip,
  kind control); still missing keyboard shortcuts and a diff of edits, planned for Phase 3.

## Known gaps

- Technician fixture cites manual pages 142-147 (demo seed); the corpus manual has 11 pages. Phase 3: make the seed
  cite corpus pages so the technician manual viewer and figure thumbnails show real (synthetic) pages (T-06).
- Synthetic and labelled: repair history, engineer drafts, health history, closed WO-000042, floor plan, lock numbers.
- Not yet tested: Chrome 109, keyboard-only use, 200 % zoom, a greyscale render for REQ-H-03.
- Carried from V: G-03 (step/close headers show time without date), G-12 (overrun flag and "ถัดไปได้เมื่อ" computed on screen).

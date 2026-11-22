# Round 4 (GATE 2 re-check) - last fixes (Cowork, 2026-11-16 10:20)

Reviewers (resumed from round 3): r4-aesthetics.md, r4-check.md, r4-engineer.md.
- Aesthetics (owner rule Q12: >= 4/5 for every audience): technician 4, operator report 4,
  board 3.5, line overview 3.5, engineer 3.5 -> GATE 2 NOT passed yet. Judge: remaining work is
  CSS/layout, not redesign; expects a pass on re-check.
- Checker: 17 PASS / 4 PARTIAL / 1 FAIL, no regressions. CORRECTION by Cowork: the one FAIL
  (eng-seed.json and the corpus PDF "missing from data/") was Cowork's packaging error - both
  files are in design/data on the Mac. Remaining reproducibility note: page images use
  _src/pdfpage.swift (macOS-only) - acceptable for Phase 2 mockups; in Phase 3 use a cross-platform
  renderer (ADR if it is a new dependency). Delete system/_src/__pycache__ (holds /Users paths).
- Engineer: pass with fixes (trust 5, speed 4, safety marking 3, evidence 4, appeal 4).

## [M] Must fix for GATE 2
1. RED LINE board-15 at 390: a nowrap chip ("…ส่งต่อ รอคนรับ เครื่องนี้อยู่") makes the page 447 px
   wide -> wrap/truncate the chip; re-test every page at 360/390 for h-scroll.
2. RED LINE label: manual page images say "ภาพหน้าจริง" but come from the synthetic corpus PDF ->
   "ภาพหน้าคู่มือ (จำลอง)" + a light watermark on the image.
3. Q9 completion (engineer): add the hot_surface kind to the step-kind picker; isolation points
   editable (add / edit / remove point, energy type) in eng-review-kind.
4. eng-review gate strip sticky (after scrolling 600 px the approve button is off screen).
5. board-15 dense rows: 30 button pairs 1-2 px apart at 1280/1920 -> >= 8 px; limit the touch-gap
   exemption with @media (pointer: fine), not width alone (1280/1366 touch tablets exist).

## Aesthetics (the judge's starred fixes - needed to reach 4/5)
6. Board 1920: second row line 15 -> 17-18 px ("read from 3 m"); board-15 fits 1080 (now 1288);
   the column of up to 15 grey "ยืนยัน": only the system's top row strong, others quiet/on hover.
7. Line overview: conveyor chevrons must not cut station outlines; lighter machine dots; labels
   placed off the corners; machine list within 1080 at 1920 (page now 1302 px).
8. Engineer: the up/down key-hint icons stack on three lines in the eng-review side panel - fix
   (judge: this alone lifts engineer to 4); larger readable page thumbnail; fill the sparse right
   panel at 1920; plainer tables refined.
9. "ส่งให้ จป. ตรวจ แล้วอนุมัติ": make the signing order explicit (e.g. "ส่งให้ จป. ตรวจ · คุณอนุมัติหลัง จป.").

## Should (after the gate is fine too)
10. eng-audit-closed: show the snapshot steps (text, page, kind) and an A4 print render.
11. Untested: Chrome 109, keyboard-only, 200 % zoom, greyscale - test in Phase 3 with axe-core.

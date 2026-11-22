# R4 re-check - Phase 2 design system after round 3

Method: own Playwright script, Chrome (--no-sandbox), all 36 `screens/*.html` x 5 viewports (360x640, 390x844, 1024x768, 1280x800, 1920x1080) = 180 renders, plus targeted probes. README figures were not used as evidence. Raw data: /tmp/chk/res2.json.

| # | Item (r3 id / [M] id) | Verdict | Measured evidence | Fix |
|---|---|---|---|---|
| 1 | Step kind + isolation points in eng-review ([M]1) | PASS | Kind chips on all 8 steps (ตัดพลังงาน, พลังงานสะสม รอ, ตรวจว่าไม่มีพลังงาน, คืนพลังงาน); the step-8 guess is labelled "ระบบเดา · ตรวจเอง" and listed as a blocker; kind control on `eng-review-kind`; "ส่งให้ จป. ตรวจ แล้วอนุมัติ" button | - |
| 2 | Failed evidence never "seen" ([M]2) | PASS | Step 6 "ตัวเลขไม่ตรง", step 7 "หลักฐานไม่ผ่าน"; "ดูหลักฐานแล้ว" appears only on steps 1-5; approve button disabled ("อนุมัติไม่ได้ · 4 ข้อ") | - |
| 3 | Approve bar + blockers on first screen, sticky ([M]3) | PARTIAL | First screen: strip y=191-239 at 1280, 179-227 at 1920. Not sticky: after scrolling 600 px at 1280 the approve button is at y=-268 (gone). | `position: sticky` on the gate strip |
| 4 | Edit field clips Thai ([M]4) | PASS | textarea scrollWidth = clientWidth (534/534 at 1280, 898/898 at 1920); scrollHeight = clientHeight | - |
| 5 | 360x640 folds ([M]5 / r3 #4) | PASS | primary bottom: sign-in-error 534, unreachable-wifi 288, unreachable-server 288, eng-review-queue 388 (were 659/658/686/686); no sign/unreachable/eng page has its primary below 640 | - |
| 6 | Reproducible build ([M]6 / r3 #22) | **FAIL** | Relative path now (`base.py` FX_PATH uses HERE); `grep /Users` in `_src` = 0. But `data/` still holds only fixture/op/sup/tech.json: `eng-seed.json` (read by eng.py) and the corpus PDF (cited in eng.py) are absent, and no `design/data/` exists. Page images exist only as `assets/r2000ic-p2.png` and `p4.png`; `pdfpage.swift` renders them and is macOS-only. The build cannot run from this copy. | Commit eng-seed.json and the PDF into `data/`; make PDF rendering run on Linux |
| 7 | PM overdue 1 vs 2 days ([M]6) | PASS | eng-health column "PM เลยกำหนด" is a job count (MC-001 = 1); the board's "เลย 2 วัน" is lateness; the headings differ and the facts do not conflict | - |
| 8 | S-01 on proposals only ([M]7 / r3 #14-15) | PASS | board-15 proposals fully above the fold (handover excluded): **10** at 1280x800 (needs 8), **15** of 15 at 1920x1080. Real board at 1920: docH 1080, no scroll. | - |
| 9 | S-10 at 1024 ([M]12 / r3 #17) | PASS | In-progress line "กำลังทำ พิมพ์ชนก MC-012 · สมชาย MC-002 · ..." at y=165-190, above the queue; 5 of 6 proposals fully above the fold | - |
| 10 | Confirm dialog consequences ([M]8) | PASS | eng-review pages name WO-000111 (not started, gets revision 4) and WO-000101 (mid-job at step 2, keeps revision 3); `eng-review-confirm` render exists | - |
| 11 | Gaps >= 8 px: nav and phones ([M]9 / r3 #7-8) | PASS | 0 gaps < 8 px on all 36 pages at 360, 390 and 1024, nav tabs included. Previously 4 px. | - |
| 12 | Gaps in dense board rows >= 1200 px (r3 #8) | PARTIAL | board-15 at 1280 and 1920: 30 pairs between buttons in adjacent rows (เลือกคนรับ / ยืนยัน / อื่น ๆ) at **1 px (1280) and 2 px (1920)**, worse than the 4.5-5 px of round 3. The real board has 0. | See rule judgement below; give buttons 8 px vertical margin or move the 1200 limit up |
| 13 | NEW_* sources ([M]10 / r3 #21) | PASS | 36 distinct NEW_* names; 28 are in `NEW_field_sources` and the other 8 have a sibling `*_source` (NEW_kind, locks_now, my_locks, repair_history and more). 0 without a source. | - |
| 14 | MC-018 wording ([M]11 / r3 #24) | PASS | "ล็อกนิรภัยแจ้งประตูเปิดอยู่" on board, board-15, line-overview, eng-notes, eng-loops; "หยุด (ล็อกนิรภัย)" gone. Remaining "หยุดเครื่อง" is the MC-001 job requirement and conditionals ("ถ้าเครื่องหยุด 37 คัน"). | - |
| 15 | Developer strings and years ([M]13) | PASS | 0 hits across 180 renders for API, `<table>`, Q11, seed, fixtures, corpus, playbook_snapshot, Excel; engineer dates carry the year | - |
| 16 | Populated states ([M]14) | PASS | eng-health: 120-day window (18 ก.ค.-15 พ.ย. 2026) with the failure and MTBF definition; eng-audit-closed WO-000042 (two work segments, wait 240 min, lock state, note); eng-health-empty. All three have PNGs and spec entries. | - |
| 17 | Unicode arrows (r3 [M]18) | PASS | 0 of ↑↓→←▾▸ in 180 renders | - |
| 18 | Honesty: rendered manual page images | PARTIAL | Page images are the synthetic corpus (header "R-2000iC Maintenance Manual - Edition 3, synthetic", 11 px grey, small) and the caption says "Edition 3, synthetic" and "คู่มือจำลองในระบบ". But the label on the image is "ภาพหน้าจริง" ("real page image"), which reads as genuine. The technician manual (pages 142-147) is still text placeholders, labelled. | Rename to "ภาพหน้าตัวอย่าง (จำลอง)"; put a synthetic watermark in the image |
| 19 | Other synthetic labels | PASS | "ข้อมูลจำลอง" banner on 36/36; history, floor plan, closed WO ("ใบงานตัวอย่าง (จำลอง)"), health ("ข้อมูลจำลอง") labelled | - |
| 20 | Regression: hscroll, overlap, Thai breaks, contrast, emoji, external | PASS | 0 hscroll on phone and desk pages (tech-print, board-15 on phones excepted as before); 0 tap/text overlaps; 0 split Thai words (independent Segmenter test); 0 text nodes < 7:1 (min 7.05); 0 emoji; 0 external requests, 0 JS errors. Phone min font 18, tap min 56; desk min 48 / 15 px. | - |
| 21 | Carried PASSes | PASS | tech-job "ถัดไป" row ends 635.2 at 360x640; "คอขวด" one line at 1024 and 1280; ISC notice 36/36 screens and 11/11 spec pages; all 36 screens referenced in spec or README, 116 measure records | - |
| 22 | Chrome 109, keyboard, 200 % zoom, greyscale | PARTIAL | Still untested (README) and not tested here | Test before Phase 3 |

Counts: 22 items - PASS 17, PARTIAL 4 (3, 12, 18, 22), FAIL 1 (6).

## Judgement: "touch gap rule below 1200 px"
Acceptable for the 1024 tablet: it is measured at 1024 with 0 pairs under 8 px, and it covers a 1180/1194 px iPad in landscape. It is weak above 1200 px. Touch tablets at 1280 and 1366 exist (iPad Pro 12.9, many Android tablets), and board-15 at 1280 now has 1 px between adjacent-row buttons, worse than before. Accept it only if the exemption is also limited to a mouse or wall display (for example `@media (pointer: fine)`) rather than a width alone.

## Red lines
1. Build cannot be reproduced from `/home/claude/frontend`: eng-seed.json and the corpus PDF are missing, and the PDF-to-PNG step needs macOS. The path fix is real; the files are not there.
2. The manual page image is labelled "ภาพหน้าจริง" on an engineer safety-review screen. Synthetic content must not read as real.

Not red lines: 360x640 folds, S-01/S-10, the approval state on the first screen, source coverage and the MC-018 wording are fixed.

## Verdict
CONDITIONAL PASS. The functional and measured fixes hold, and nothing regressed. Before GATE 2: (1) add the missing data files and make the build run, (2) relabel the page image, (3) make the gate strip sticky and fix the 1-2 px button gaps in dense rows.

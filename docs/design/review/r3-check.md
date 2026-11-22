# R3 acceptance check - Phase 2 design system

Method: Playwright + /usr/bin/google-chrome (--no-sandbox), all 33 `screens/*.html` x 5 viewports (360x640, 390x844, 1024x768, 1280x800, 1920x1080) = 165 renders, own measuring script (not render.py). Phone verdicts use 360/390, desk verdicts 1024/1280/1920. Sample = all 33 pages, so it includes every new page plus board and tech-job. Raw data: /tmp/chk/res.json.

| # | Item | Verdict | Measured evidence | Fix |
|---|---|---|---|---|
| 1 | No horizontal scroll (phone pages) | PASS | 0 px on every phone page at 360 and 390. Only `tech-print` (A4 sheet, 794 px) scrolls on a phone (343/313 px); `board-15` too, but it is a desk-only test page. | Say in the README that tech-print is print only. |
| 2 | No overlap (taps and text) | PASS | 0 tap overlaps, 0 text-over-text lines in 165 renders | - |
| 3 | Primary action above the fold, 390x844 | PASS | all new pages end at y <= 686 (tech-job 510, sign-in 512, board "ยืนยัน" 781) | - |
| 4 | Primary action above the fold, 360x640 | **FAIL** | sign-in-error 659, unreachable-server 686, unreachable-wifi 658, eng-review-queue 686 (first "ตรวจ"). All below 640. Passing: sign-in 538, tech-job 571, eng-audit 380. | At height <= 640: cut hero or help text and use a sticky bottom action, or put the button before the explanation. |
| 5 | Phone tap >= 56 px | PASS | min 56 on all phone pages | - |
| 6 | Desk tap >= 48 px | PASS | min 48 at 1024/1280/1920 | - |
| 7 | Gaps >= 8 px, phones | PASS | 0 pairs under 8 px at 360/390 | - |
| 8 | Gaps >= 8 px, tablet and desk | **FAIL** | Top-nav tabs 4 px apart on all eng-* (5-7 pairs; 6-7 at 1024, touch) and line-overview (2). board-15 at 1920: 30 pairs 4.5-5 px (เลือกคนรับ/ยืนยัน/อื่น ๆ in neighbouring rows). README decision 4 exempts desk, but 1024 is a touch tablet and the brief says 8 px. | Nav gap 8 px. Dense rows: put the two buttons side by side, or drop the exemption in writing. |
| 9 | Phone text >= 18 px | PASS | min 18 px on every phone render. `tech-print` is 14.67 px (print, README allows 14). | - |
| 10 | Contrast >= 7:1 | PASS | min 7.05 (board, line-overview), 7.42 (tech-job, noplaybook), 7.90 (the rest). 0 text nodes under 7 in 165 renders. These match the README. | - |
| 11 | Thai never broken inside a word | PASS | Every Thai word from `Intl.Segmenter('th')` and every `.w` span: 0 drawn on two lines, in all 165 renders | - |
| 12 | No external requests | PASS | 0 non-file/data requests, 0 external images, no http(s) URL in any screen or spec page | - |
| 13 | No emoji | PASS | 0 in text, title, aria-label, alt | - |
| 14 | S-01 at 1280x800 (>= 8 rows, board-15) | PARTIAL | 8 items fully above the fold (last bottom 748), but item 1 is the handover row. Real queue proposals = **7**. | Count proposals only, or gain ~10 px so row 8 fits. |
| 15 | S-01 at 1920x1080 (15 rows) | PARTIAL | 15 items fully visible (last bottom 1066), but 1 is the handover row. Proposals = **14 of 15**; the 15th spans 1066-1118. | Gain ~40 px (band or line-box 20 -> 18) or state "14 + handover". |
| 16 | S-01 side claim: real fixture at 1920 without page scroll | PASS | board docH = 1080 at 1920 (1419 at 1280, not claimed) | - |
| 17 | S-10 at 1024 | PARTIAL | Table starts y=326; 6 of 7 rows fully visible (row 7 ends 827 > 768). The technician list "ช่างในกะ 10 คน" starts at y=1401, 633 px below the fold. Only the band count shows in-progress work on the first screen. README admits it. | Show a 4-person strip in the band or beside the queue, or mark S-10 as not met at 1024. |
| 18 | tech-job "ถัดไป" row within 640 at 360x640 | PASS | row y 579.2-635.2 (56 px); gap to the primary button exactly 8; margin 4.8 px | Margin is thin; one more line of text breaks it. |
| 19 | "คอขวด" unbroken at 1024 | PASS | board, board-15, line-overview: 1 client rect (one line) at 1024 and 1280. Absent on phone board (hidden). | - |
| 20 | Lucide ISC notice on every page | PASS | 33/33 screens and 11/11 spec pages carry "Lucide ... ISC License" | - |
| 21 | Every NEW_* field has *_source | **FAIL** (strict) / PARTIAL (group) | 73 NEW_* keys. 33 have no same-name `*_source` or `NEW_field_sources` entry. Group sources cover NEW_kind, hazards, isolation/restore/wait, signal word, verify/restore lists, wait choices; NEW_eng and NEW_floor_plan carry an inner `_source`. Not covered by any: `NEW_playbook`, `NEW_eta_local`, `NEW_eta_confidence_minutes`, `NEW_state_detail` (source on proposal 0 only, but 6 uses), `NEW_lock_hold_reasons_th`, `NEW_wait_reasons_th`. | Add one source line per key name, or one `NEW_field_sources` entry per key. |
| 22 | Every on-screen value is in fixture.json | PARTIAL | Time, code and number+unit tokens on 20 pages: all found, except "4,800 นาที" (= capacity_minutes 4800, formatting only). But eng-health and eng-loops read `data/seed1/eng.json`, which is not in `data/` (only fixture/op/sup/tech). The build points to `/Users/narinthon/...` (base.py FX_PATH), so it does not rebuild here. Inconsistency: eng-health says MC-001 PM overdue "นานสุด 1 วัน"; board/fixture say "เลย 2 วัน". | Copy seed1/eng.json into data/ and relative-path the build. Reconcile 1 vs 2 days or label the seed as a different day. |
| 23 | Synthetic content labelled | PASS | Banner "ข้อมูลจำลอง" on 33/33 pages. History chip "จำลอง" (tech-job); "รูปจากหน้านี้ (จำลอง)", "ตัวอย่างข้อความคู่มือ (จำลอง)", "ตัวอย่าง ยังไม่อนุมัติ" (tech-step); "ผังจำลองสำหรับออกแบบ (ไม่ใช่แบบสำรวจจริง)" (line-overview); "ประวัติจำลอง (Q11)" (eng-notes); "ตัวอย่าง (จำลอง)" on the English text of tech-print. board-15 labels its copies as test data. Weak spot: the tech-job history label is a small chip beside the heading. | Put "(จำลอง)" in the history heading text. |
| 24 | No line-stop claim without a source | PARTIAL | No page says the line is stopped. MC-018 "ระบบล็อกนิรภัยหยุดเครื่องอยู่" and "หยุด (ล็อกนิรภัย)" (board, board-15, line-overview) have a source: `NEW_state_source` = door-open interlock "stops the robot cell by design", synthetic. That is an inference, not a machine-state signal. "ถ้าเครื่องหยุด 37 คัน" is conditional and "งานนี้ต้องหยุดเครื่อง" is a job need; both fine. | Word it as "ล็อกนิรภัยแจ้งประตูเปิด" and show "หยุด" only when a machine-state signal exists. |
| 25 | README screen table: every page exists | PASS | 33/33 files, including tech-states, tech-manual, components; every listed PNG viewport exists (19 families); tech-print.pdf exists. measure.json has 95 records, summary.json 33 pages, 0 violations. | - |
| 26 | States listed in each spec page | PASS | All 33 screens are referenced by a spec page. Each family lists its states with the render: board (menu/undo/drawer/stale/expand + board-15), eng-review (queue/mismatch/notfound/unsaved/confirm), shell (4), tech-job (3), tech-close (4), report (3). | - |
| 27 | README gaps (Chrome 109, keyboard, 200 % zoom, greyscale) | PARTIAL | Listed as untested in the README; I did not test them either. | Test before Phase 3. |

Counts: 27 items - PASS 18, PARTIAL 6 (14, 15, 17, 22, 24, 27), FAIL 3 (4, 8, 21; #21 PARTIAL if group sources count).

## Red lines
1. Phone primary action below the fold at 360x640 on 4 new pages (sign-in-error, unreachable-wifi, unreachable-server, eng-review-queue). These are the error and recovery screens.
2. S-01 is met only by counting the handover row: proposals visible are 7 at 1280 and 14 at 1920, not 8 and 15.
3. The build and the eng-health/eng-loops data are not reproducible (Mac absolute path, seed1/eng.json absent), and the PM overdue figure disagrees (1 vs 2 days).

Not red lines: external requests, emoji, split Thai words, contrast and unlabelled synthetic data are all clean.

## Verdict
CONDITIONAL PASS. The measurable base is clean: contrast, font size, tap size, overlap, Thai breaks, offline, emoji and notices all pass. The headline S-01 numbers are overstated by one row, and S-10 at 1024 is not met. Fix the 360x640 folds, the nav and dense-row gaps, and the missing sources, and reproduce the build before sign-off.

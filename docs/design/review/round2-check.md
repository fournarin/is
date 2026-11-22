# Round 2 re-check - concept V, round 4 (2026-11-15)

Method: same as r1-check.md. I re-measured the 15 phone pages at 360x640 and 390x844, and board.html at 1024, 1280 and 1920, with Playwright and /usr/bin/google-chrome. The script checks DOM text overlaps, tap targets and gaps, primary-button fold, page height, Thai breaks per character, contrast for every text node, computed font sizes, font bytes and external requests. Values were checked against the new fixture.json. I looked at the current PNGs (all from 22:13-22:14, the same time as the HTML). The designer's figures in ROUNDS.md were not used.

## A. Round-1 red lines

| # | Item | Result | Evidence | Fix |
|---|---|---|---|---|
| RL1 | tech-job status = fixture | PASS | tech-job at 360/390 shows chip "กำลังทำ", "ขั้น 2 จาก 6 · เริ่ม 10:05 น.", and button "ทำต่อขั้น 2" (360: 521-585, in view). This matches fixture in_progress / 10:05 / step 2 and the board ("กำลังทำ MC-012 เริ่ม 10:05") | - |
| RL2 | Unapproved safety lists | PASS | The verify choices and the restore checklist carry the on-screen chip "ตัวอย่าง ยังไม่อนุมัติ". Fixture has NEW_verify_choices_th, NEW_restore_checklist_th, NEW_restore_test_choices_th + NEW_unapproved_lists_source ("NOT approved"). Wait/reason/lock-hold lists are config with their own _source | - |
| RL3 | ISO 7010 use | PASS | M021 + W012 appear only on the isolate step, W017 only on hot surface; all are 48 px. The restore step has no sign. The visible signal words are "อันตราย" (isolate) and "ข้อควรระวัง" (hot) | - |

## B. round1-summary [M] items 4-11

| # | Item | Result | Evidence | Fix |
|---|---|---|---|---|
| 4 | MC-018 "เครื่องหยุด" | PASS | Station-4 tile and legend say only "เกินเกณฑ์" (1024/1280/1920). Row: "เกินเกณฑ์แล้ว · เครื่องหยุด (ล็อกนิรภัย)". Fixture NEW_state_source names the interlock signal | - |
| 5 | Phone text ≥18 px (G-06) | PASS | Minimum computed font is 18 px on all 15 phone pages at 360 and 390. Board minimum is 15 | - |
| 6 | Board 1024 / 1280 | PARTIAL | 1024: 4 queue "ยืนยัน" buttons within 768 px (bottoms 477/574/653/733; was 1), no sideways scroll. But the in-progress crew list is below the fold (S-10 declared partly unmet), and "คอขวด" breaks inside the word at 1024 ("· คอ / ขวด สถานี 3", legend). 1280: page height 1517, 3 full rows plus part of a 4th; the rationale claim is corrected | Keep "คอขวด" in one nowrap span. A one-line in-progress count in the 1024 band |
| 7 | Manual report path | PASS | report-manual.html: station → machine → stopped → seen → send = 5 taps (station grid drawn). Send button 744-808 at 390x844. QR page is machine-bound (NEW_qr_binding + source) = 3 taps | - |
| 8 | Handover lock question + board action | PASS | 3 options. "ปลดกุญแจ…" is off ("คนรับงานต้องใส่กุญแจของตัวเองก่อน"). "ยังล็อกอยู่" is chosen with CP-3/ก-03/10:31. "ไม่ได้ตัดพลังงาน" is off ("ทะเบียนมีกุญแจ ก-03"). Board shows a "ส่งต่อ รอคนรับ" row with note + "เลือกคนรับ" at all 3 sizes | - |
| 9 | Lock time; "ดู" target | PASS | Strip on steps 3/4/6, close-locked and handover reads "ใส่ 10:31 น. ขั้น 2" (fixture NEW_lock_example + source). Minimum phone target is 56 px; tech-states has no target <56 | - |
| 10 | One MC-004 ETA | PASS | Fixture state_detail, state_th and the board all say 21:10 ±2 ชม. Also fixed: close at step 2 now has "ปลดกุญแจ…" disabled (register empty); locked close numbering is 1→2 | - |
| 11 | rationale.md | PARTIAL | False claims rewritten, Unmet list updated (S-01, S-10 partly, greyscale test). But T-01 is declared met, while at 360x640 the first-screen "ถัดไป 1 งาน" row spans 593-659 px, crossing the 640 fold (it fit in round 1; the 18 px text pushed it down) | Tighten tech-job (e.g. ETA on one line) so the row ends ≤640, or list T-01 at 360 as unmet |

## C. Other round-1 FAIL/PARTIAL items

| r1 # | Item | Result | Evidence / fix |
|---|---|---|---|
| 4 | Report taps | PASS | QR 3 taps, manual 5; urgency "ไม่บังคับ" with no default; "หยุดอยู่ไหม" starts empty |
| 8 | NEW_* → source | PARTIAL | Still no `_source` for NEW_lost_units, NEW_buffer_minutes, NEW_priority_parts, NEW_reason_detail, NEW_stage_times, NEW_observation_choices. Some are covered in the rationale backend table. Manual figure thumbnails have no fixture field. Fix: add one line each |
| 14 | Targets / gaps | PASS | Phones ≥56 (tech-job 64), board ≥48; 0 gaps under 8 px |
| 20 | Values vs fixture | PASS | Spot checks match: crew minutes and sort, lost units 40/37/18/6/70/15, ETA 21:10/03:00, load 2,976/4,800, next round 3 min, held 2, set aside 1, finished 3; operator stages use the fixture words |
| 22-23 | Lock visibility / handover | PASS | See B8, B9 |
| 25-26 | ISO / approved data | PASS | See RL2, RL3 |
| 27-29 | Technician, shift-lead, safety red lines | PASS | No cross-screen conflict found. No one-tap isolation. Close and handover record the lock state. Unlock by owner only. No safety text is presented as approved unless it is |
| 31-33 | Examiner / rationale claims / Unmet list | PARTIAL | Only the T-01 item above; other claims match the measurements (min contrast 7.05, 87 KB, 1920 = 1080 px) |

## D. Regression spot-checks (previous PASS)

| Check | Result | Measured |
|---|---|---|
| Text overlaps | PASS | 0 at every page and viewport (the stacked "สถานี / 3" tile is unchanged by design) |
| Primary action fold 390x844 | PASS | report empty 759-823; report ready state (demo label hidden) 759-823; report-manual 744-808; tech-job 460-524; step-normal 603-667. No fixed or sticky elements on phones, no vh |
| Thai breaks | PARTIAL | Only true word-internal break: "คอ|ขวด" (board 1024). Compound split "หัวหน้า|กะ" on tech-states 390. All others fall between words |
| Contrast | PASS | Minimum 7.05 board, 7.42 tech-job, 7.90 other phone pages; 0 text nodes <7:1 |
| Fonts / network | PASS | 86,940 B on every page (2 woff2), 0 external requests, 0 image requests |
| Board 1920 | PASS | Page height 1080, width 1920; 6 rows in view. Spare space is only 4 px, as the rationale itself says |

## E. Honesty of new content

| Item | Result | Evidence / fix |
|---|---|---|
| Repair history | PASS | tech-job: "ครั้งก่อนที่เครื่องนี้ · จำลอง" (2 jobs); every step: "2 ครั้ง · จำลอง"; fixture NEW_repair_history_source says synthetic |
| Manual figure thumbnails | PASS | Every step's manual row: "R-2000iC · รูปจากหน้านี้ (จำลอง)", drawn as a placeholder (no real image loaded); viewer says no real manual file |
| Lucide licence | PARTIAL | _src/lucide/LICENSE is ISC (Lucide Icons and Contributors); each source SVG carries "@license lucide-static v1.49.0 - ISC"; rationale cites Lucide 1.49.0 ISC. The built HTML inlines the icons with no notice (grep "lucide" = 0). ISC asks for the notice in copies. Fix: one HTML comment, or a third-party notice in the shipped app |
| Synthetic banner | PASS | "ข้อมูลจำลอง · ไม่ใช่สัญญาณจริง" on all 17 pages |

## Counts
**29 PASS · 7 PARTIAL · 0 FAIL** (36 rows). No red line remains, and no new red line was found.

## Verdict
**Ready for the owner's GATE 1: yes, with minor notes.**

None of the notes is a red line:
1. tech-job at 360x640: the "ถัดไป 1 งาน" row crosses the fold (659 px), so T-01 is not met at 360.
2. "คอขวด" breaks inside the word at 1024.
3. Add the Lucide ISC notice to the shipped HTML.
4. Add `_source` lines for the 6 remaining NEW_* fields and the figure thumbnails.
5. S-01 (8 rows at 1280 / 15 at 1920) and S-10 (in-progress list at 1024) stay declared unmet. The owner should accept them knowingly.

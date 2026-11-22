# S1 round 2 check - technician screens (v2 build @21a1789)

Method: the six SSR snapshots in `v2/set1/pages/` (tech-job, tech-step, tech-step-normal, tech-noplaybook, tech-manual, tech-job-empty) render properly under file:// (fonts "IBM Plex Sans Thai Looped" 400 and 600 load, 0 external requests, 0 emoji). Measured with Playwright at 360x640, 390x844 and 1280x800, closed and with every `<details>` sheet opened. States without a snapshot (tech-states-*, tech-offline) were checked from PNGs and measure.json only.

| # | Item | Verdict | Evidence | Fix |
|---|---|---|---|---|
| M1 | tech-job structured blocks | PARTIAL | Now present: "◆ สูง · กำลังทำ · ขั้น 2/6 · เริ่ม 17:10", button "ทำต่อขั้น 2", tiles ตอนนี้ 78 °C / เกณฑ์ 85 °C / เพิ่มขึ้น 1.4 °C/ชม. (equal to fixture my_job signal), tools list, history (chip "จำลอง"), approval footer, "อัปเดต 17:13:33 · หน้านี้อัปเดตเอง". The 5-line paragraph is gone from the page. **"ถัดไป N งาน" row not rendered**: the world's technician has one job, so it is untested. Footer says "ฉบับที่ 1 · 2 พ.ย. 2026 17:10" against the fixture's revision 3, 14:10 (world data, under the banner). | Add a two-job technician capture to prove the next row at 360x640 (spec: ends <= 635 px) |
| M2 | Station plate | PARTIAL | Name "ติดตั้งหลังคา" + 4-lamp strip (amber outline = forecast, own station white). The spec has 8 lamps; the world plant has 4. I cannot verify `/line/lamps` (no repo). | State in the spec that the lamp count follows the plant |
| M3 | tech-step-normal excerpt and figure | PARTIAL | Excerpt "ต้นฉบับจากคู่มือ · หน้า 4 / Remove the belt guard..." is shown, but labelled as the manual's original, with no "(จำลอง)". The text is the synthetic corpus ("Edition 3, synthetic" only in the footer). The figure is an image icon only, not a thumbnail. | Add "จำลอง" to the excerpt label; figure is set 7 (declared) |
| M4 | tech-noplaybook | PASS | Heading 24/600 in the callout; "โทรถามวิศวกร (ปราณี)" row says no number is stored; handover and close rows; manual "(Edition 1, synthetic)" labelled | - |
| M5 | tech-manual page with text; Wi-Fi-lost state | PARTIAL | Page text renders (steps 1-6, 42 Nm). Extraction merges "procedure Symptom:" and runs "Required tools..." into step 6; there is no synthetic label on this screen. Wi-Fi lost: offline strip "Wi-Fi หลุด · หน้านี้ยังอ่านได้..." on the step page (PNG), different from the spec's retry state. On the snapshot, the primary "กลับไปขั้นที่ 4" ends at y=1235 (below the 640 fold); the back button is at the top (y 41-97). | Label manual text จำลอง; keep line breaks from the source; pin the back action |
| M6 | tech-step primary at 360x640 | PASS | Bottom 626 (margin 14 px), tech-step-normal 626, tech-job 610 (margin 30) | - |
| 7 | Polish | PASS | "ขั้นที่ 4 จาก 6" no longer repeated (shows "4/6"); chip + swatch on tech-job uses amber outline only for forecast; textarea/no-grip not checkable (sheets closed in snapshots) | - |
| 8 | MEASURE weights; SSR from v2 | PASS | measure.json has weights, only 400/600; my count agrees (18/400, 18/600, 24/600, 36/600, plus 24/400 on step pages); snapshots carry `.v2` CSS | - |

## Phone rules and tokens (own measurement, 18 records)
- Text min 18 px everywhere; sizes only 18/24/36; weights only 400/600. Contrast min 7.42 (tech-job, noplaybook), 7.90 elsewhere, 0 nodes under 7 (colours = tokens.css).
- No h-scroll, 0 split Thai words (Segmenter test, all pages and viewports), taps min 56 px, 0 gaps under 8 px (390x844 tech-step: one pair 2.7 px, link to textarea, from the closed sheet only; 0 when opened).
- Apparent failures with sheets closed were measurement artefacts: closed `<details>` bodies still report boxes (37-60 "text overlaps", 13 px radio inputs). With sheets opened: 0 overlaps, 0 tap overlaps; radios sit inside 56 x 296 labels.
- Fold at 360x640: job 610, step 626, handover 626 (measure.json). Not above the fold by design or by length: tech-noplaybook (call row ~y 790), tech-manual (1235), tech-offline (720, strip pushes it down; acknowledged in ROUNDS).
- Banner "ข้อมูลจำลอง · ไม่ใช่สัญญาณจริง" on every snapshot and PNG.

## ROUNDS.md claims
- "27/27 MEASURE pass": 27 records (9 captures x 3); numbers consistent with my run where I have a snapshot. Not rerunnable for the 3 captures without a snapshot.
- Primary bottoms 610/626/626: confirmed (job 610, step 626).
- "Only 400/600 found": confirmed.
- Wi-Fi-lost state: only visible on the step page as a strip; the "server-side failure names the manual" state has no capture.

## Verdict
CONDITIONAL PASS, improved from round 1. Blockers 1, 2, 4 and 6 hold. Remaining before the gate: (1) prove the "ถัดไป" row with a two-job technician, (2) put "จำลอง" on the manual excerpt and manual page text, (3) manual page extraction merges lines, (4) offline strip pushes the primary to 720 at 360x640.

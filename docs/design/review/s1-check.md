# S1 check - Phase 3 set 1 (technician screens in the Next.js app)

## What could and could not be measured
- **SSR pages (`v2/pages/*.html`) are the legacy UI, not v2.** Under file:// the CSS path `../_next/static/chunks/3g9a6ok6_kuad.css` resolves, but that is a single 19 KB file (dated Nov 15 01:23) with 0 `.v2` selectors, no `.v2` element, no synthetic banner. Measured at 360x640 (tech_work, tech_work_WO-000001_steps): text 13/13.8/14/15/16/17/19/32 px with weights 400/500/600/700, so it breaks the 15/18/24/36 and 400/600 rules. tech_work_WO-000001_manual.html is a 767-byte empty shell. They cannot support token or phone-rule checks and are excluded from the verdict.
- Fallback: the PNGs in `v2/set1/` (side-by-side against `system/png/` at 360x640 and 390 full) plus `measure.json`. I could not re-run the numbers because the repo and `v2.css` are not on this machine; they are checked for internal consistency and against the PNGs.

| # | Item | Verdict | Evidence | Fix |
|---|---|---|---|---|
| 1 | Token fidelity: colours | PASS | measure.json contrast pairs are exactly tokens.css: ink rgb(17,20,24), ink-2 (61,67,75), sunk (226,229,233), canvas (238,240,242), andon (22,25,29), on-andon-2 (186,193,201), surface white | - |
| 2 | Type scale / weights | PASS (self-reported) | All 24 records use only 18/24/36 px (e.g. tech-job 127x18, 6x24, 1x36); none under 18. Weights not in measure.json; PNGs read as 400/600. | Add computed weights to MEASURE |
| 3 | Phone rules (text >= 18, tap >= 56, gaps >= 8, no h-scroll, no split Thai, contrast >= 7) | PASS (self-reported, consistent with PNGs) | 24/24 records: minFont 18, minTap 56, gaps 0, split 0, hscroll false, min contrast 7.90. No Thai splits visible in any of the 36 PNGs. | - |
| 4 | Primary above fold, 360x640 | PASS, thin | Bottoms at 360x640: tech-job 574, step-normal 555, manual 459, noplaybook 575, handover 555; **tech-step 639** (1 px under the fold) | Give tech-step >= 8 px margin |
| 5 | Synthetic banner | PASS | "ข้อมูลจำลอง · ไม่ใช่สัญญาณจริง" at top of all 8 captures x 3 viewports; manual and noplaybook labelled "(Edition 1, synthetic)" | - |
| 6 | ROUNDS.md claims | PASS | 24 records = 8 screens x 3 viewports; primary bottom range 459-639 at 360x640 matches; empty queue has no primary (true); fixed items visible in PNGs (no per-word pills, "งานที่ 1 จาก 1" on one line, noplaybook button above the fold) | - |
| 7 | "No invented data" | PARTIAL | Data is from the design world (seed_world), not fixture.json, so I cannot trace it. Values that differ from the spec fixture: clock 10:50/10:51 (live), date 16 พ.ย., "ETA 16 พ.ย. 16:48", "สายผลิตเสียราว 135 คัน", job WO-000001, manual "M-710iC (Edition 1, synthetic)". All sit under the banner. | State in ROUNDS.md that world values come from seed_world |

## Blockers vs the approved spec (screen @ viewport)
1. **tech-job @ all.** Missing: station name on the plate (shows only MC-012), priority mark, "ขั้น 2/6 · เริ่ม" progress, step in the button (spec "ทำต่อขั้น 2", built "ทำต่อ"; ambiguous for a job resumed mid-way), the live signal block (78 / 85 °C, trend), tools and lock kit under "เตรียม", the "ถัดไป N งาน" row (spec's 360x640 claim, 635 px). Station strip is a declared gap; the rest is not listed in the known gaps.
2. **tech-noplaybook @ all.** The spec's "โทรถามวิศวกร" action (engineer name, "เบอร์ยังไม่ได้ตั้งค่า") is missing. Built offers only close and a quiet "ส่งต่อให้คนถัดไป" link; the spec offers call, handover, close (each as a button).
3. **tech-step-normal @ 360x640.** Spec shows a manual excerpt "ตัวอย่างข้อความคู่มือ (จำลอง)" and a labelled figure thumbnail; built shows only the "อ่านคู่มือหน้า 145" link. T-06 stays open and the page is thinner than the spec. Lock-owner strip: set 2.
4. **tech-manual @ all.** Built renders only the "ยังไม่ได้อ่านหน้านี้" failure; no page text or image was rendered, and ROUNDS.md says check-the-content-path.py was not run. The spec's offline state ("โหลดไม่ได้ · Wi-Fi หลุด", retry button) is not built either; the built button list differs ("กลับไปขั้นที่ 4", "เปิดไฟล์คู่มือหน้า 145").
5. **SSR evidence.** `v2/pages/` was captured from the pre-v2 UI, so no v2 page was verified in HTML. Re-capture with the v2 build (including the manual page WITH text).
6. **Not in the spec but present:** none that conflict. tech-job-empty (message, megaphone card) and tech-states-disagree/handover match the spec's structure.

## Verdict
CONDITIONAL. The foundations (tokens, type scale, phone rules, banner, Thai handling) match the spec and the claims in ROUNDS.md hold, but I could not re-measure them. tech-job and tech-noplaybook drop spec content (blockers 1-2), and the manual path is unproven (blocker 4). Do not call set 1 complete until these are built and the SSR captures are redone from v2.

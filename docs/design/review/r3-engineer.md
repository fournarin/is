# Round 3 review: วิศวกรซ่อมบำรุง (ปิยะนุช) — หน้าจอ Phase 2 ฝั่งวิศวกร

Reviewed: eng-review-queue, eng-review (+unsaved, confirm), eng-review-notfound, eng-gaps, eng-loops, eng-health, eng-notes, eng-audit, line-overview. Source HTML read, PNGs viewed (1280, 1920 for eng-review).

## Scores (1-5)
| Criterion | Score | Why |
|---|---|---|
| Trust | 4 | "ร่าง ยังไม่อนุมัติ" tag on every review page; synthetic banner on every page; no celebration; empty states say why (eng-health "ไม่จัดอันดับ", loops "0/10"). Mismatch and not-found wording is exactly mine. |
| Speed of review | 3 | Side by side at 1920 works and 8 steps fit, but the approve bar is below the fold at 1920x1080 and 1280x800 (cut at y=1040/ off-screen), so the blockers list I need is not seen. No keyboard step/approve shortcut shown beyond the hint. |
| Safety marking | 1 | No control anywhere to mark a step isolation / hot surface / restore, or to list isolation points per Q9. Steps 1 (lock), 3 (zero energy), 8 (remove locks) look identical to step 5 (measure). The audit screen also shows no kind. |
| Evidence | 3 | Page text with exact-match highlight, mismatch bar, not-found bar with "ระบบไม่เน้นส่วนที่ใกล้เคียง" are right. But the page is text only: no figure, no torque table, no rendered page. Audit shows page numbers but no link to the page. |
| Appeal | 4 | Calm, dense, desktop table layout, readable Thai, top nav, no emoji. Would use it over PDF + Word. Right panel wastes 40% of the height at 1920. |

## Red lines
1. **Approval without evidence: partially hit.** Step 6 (mismatch) shows chip "ดูหลักฐานแล้ว" and the confirm dialog is shown in a state with step 7 rejected. The prototype is consistent that confirm is reachable only after fixes, but the "ดูหลักฐานแล้ว" chip on a step whose evidence failed is misleading: viewing a not-found page (step 7) must not count as "seen evidence". Needs a rule and a visible state.
2. **Unsafe default: HIT.** Safety kinds absent, so an engineer can approve a lockout/restore playbook with nothing marked and the technician screen (tech-step isolate/hot/restore) has no data to show. Step 8 "ปลดกุญแจ" and step 3 hot-surface wait are unmarked. Q9 not honoured on the review screen.
3. **Rejected step semantics unclear.** Confirm says "ปฏิเสธ 1 ขั้น (ขั้น 7)" and then "ใบงานเปิด 2 ใบ จะได้ขั้นตอนนี้ทันที". Does the technician get 7 steps, with the idler step missing? Sequence 6 -> 8 may break a safety flow. Must state what the technician receives.
4. **Silent change to open work orders.** "จะได้ขั้นตอนนี้ทันที" for 2 open WOs with no mention of technicians mid-job (my red line 4 / question 2). Not blocked, not explained.
5. Not hit: unresolved number mismatch cannot reach approve (blocker list says so); synthetic labels present; draft vs approved distinguished by word; approver named with role and date.

## What works
- eng-review: Thai/English/page side by side, numbers boxed on both sides, 24 vs 42 Nm explicit on the line and in the panel, highlight on the exact sentence only.
- eng-review-notfound: red bar, no near-match highlight, offers "ตรวจหน้าอื่นหรือปฏิเสธ".
- eng-review-queue: table with open WO count and fixes needed; needs_review distinct from draft in words.
- eng-gaps: four counts, no celebration. eng-loops: insufficient-data rows now one line each, 5 rules fit in one 1280x800 screen, safety rule note kept. eng-health: honest "ไม่จัดอันดับ", real table.
- eng-audit: WO search with snapshot, approver full date, 3 clicks, print button.

## Problems by screen
- eng-review 1920x1080: approve bar and blockers at y>1040, invisible without scrolling; the unsaved/confirm states are only reachable by scrolling too. Step 6 Thai text is shown twice (heading plus input) which wastes 2 lines.
- eng-review: no "open in second window" for the manual page (R-E1 should). No timezone on dates ("14 พ.ย. 2026 16:20", confirm "15 พ.ย. 10:42 น." without year or zone) vs R-E8.
- eng-review confirm: no revision date/year, no "ใคร" role snapshot beyond name; fine otherwise.
- eng-audit: no state word draft/approved/needs_review on snapshot, no `work_segments` beyond one line, print preview not rendered, and no kind labels. Approval time has no timezone. No export CSV.
- eng-health: 0 days / all zeros is honest but gives me nothing for the reliability meeting: no sortable headers visible, no MTBF/MTTR, no definition of failure (my question 5), no observed_days per row. Can't judge the populated state at all.
- eng-loops: where to change a value is not stated; "ข้อมูลจาก API ของ demo seed (design/data/seed1/eng.json)" is developer text on a user screen.
- eng-notes: no filter link to the playbook step; filters present but "ช่วงวันที่: กะนี้" is not a date range; seed note says "ประวัติจำลอง (Q11)" - internal code.
- line-overview: ETA text "ถึงเกณฑ์ราว 15 พ.ย. 21:10 ±2 ชม." has the date now (good); MC ids still, but station names exist. Not my main screen; fine.
- Cross-screen: `<th>` dev jargon ("playbook_snapshot", "<table>", "fixtures/corpus", "API") appears on engineer screens; replace with plain Thai.

## Top 5 fixes
1. **Add step kind marking to eng-review** (per step: ปกติ / แยกพลังงาน / ผิวร้อน / คืนสภาพ, hazard code, isolation points list, wait minutes). Approval blocked if a step is auto-flagged by the keyword hint (E-14) but unmarked, show "ระบบเดาจากข้อความ ตรวจเอง". Show the same kinds in eng-audit snapshot.
2. **Fix evidence semantics:** a step counts as "ดูหลักฐานแล้ว" only if evidence is found; not-found/mismatch pages never set the chip. Show the blocker list and approve button in the first screen (sticky bottom bar inside the page, not covering steps) at 1280x800 and 1920x1080.
3. **Rejected-step and live-WO consequences in confirm dialog:** state exactly what technicians receive (steps kept/removed, order), and how many WOs are mid-run and at which step; require explicit tick if any WO is already past step 1. Offer a LOTO second-reviewer prompt when kinds include isolate/restore.
4. **Evidence completeness:** render the manual page image (table/figure) beside the text, a "page 2 lockout" jump from steps citing another page, and an "open in second window" button. Dates with year, time and zone everywhere approvals appear (E-08).
5. **Populated states and data honesty:** provide seeded eng-health (sorted table with observed_days, failure definition, MTBF) and an eng-audit closed-WO example (approved WO from 6 months ago, with kinds, work_segments, outcome) plus A4 print render; strip developer strings (API paths, "<table>", "Q11", "fixtures/corpus") from user-facing text.

## Verdict
**Conditional pass: not yet usable for real approval.** Evidence handling, honesty and layout are the best I have seen on this project and I would use the review table and not-found state. But Q9 safety marking is missing, the approve action is below the fold, the effect on live work orders is not stated, and the health/audit screens are only shown empty. Fix 1-3 and show populated states, then I would trust it with a real playbook.

# Round 4 re-check: วิศวกรซ่อมบำรุง (ปิยะนุช)

Checked eng-review-kind, eng-review, eng-health (+empty), eng-audit-closed at 1280x800 and 1920x1080 (PNG plus HTML text).

## Scores (1-5), r3 -> r4
| Criterion | r3 | r4 | Note |
|---|---|---|---|
| Trust | 4 | 5 | Failed evidence now reads "ตัวเลขไม่ตรง" / "หลักฐานไม่ผ่าน", never "ดูหลักฐานแล้ว". Dates carry year, time, zone. Developer strings gone. |
| Speed | 3 | 4 | Gate ("อนุมัติไม่ได้ · 4 ข้อ" + approve button) is in the first screen at both sizes. 1920x1080: all 8 steps, page, kind picker fit with no page scroll. At 1280 the step list scrolls inside, acceptable. |
| Safety marking | 1 | 3 | Kind picker (ปกติ / ตัดพลังงาน / พลังงานสะสม รอ / ตรวจว่าไม่มีพลังงาน / คืนพลังงาน), isolation point CP-3 with tag W012, system guess on step 8 ("ระบบเดา: คืนพลังงาน · ตรวจเอง") that blocks approval until confirmed, second reviewer (จป.) in the confirm. Gaps below. |
| Evidence | 3 | 4 | Page tabs (2 and 4), real page thumbnail, "หน้าต่างใหม่", exact underline only. Thumbnail is tiny and unreadable at both sizes. |
| Appeal | 4 | 4 | See below. |

## Red lines (re-verified)
1. Approve without evidence: cleared. Mismatch (6), not-found (7) and unseen (8) are listed as blockers; approve button is locked.
2. Unsafe default: mostly cleared. Unmarked restore step cannot slip through because of the guess flag. Residual: **no "ผิวร้อน" (hot surface) kind** in the picker. The old audit sample had a wait-until-cool step with "do not touch while hot"; it has no way to be marked now. Q9 asks for hot surface explicitly. Also the isolation point is a read-only line ("จุดตัด: CP-3 ..."); I cannot add or edit points (e.g. a second energy source) on this screen.
3. Rejected step / live WO: cleared. Confirm says technician gets 7 steps (1-6, 8), step 7 removed, safety steps cannot be cut, WO-000101 stays on rev 3 until close, WO-000111 gets rev 4, with an acknowledgement tick. Good, this is exactly my red line 4.
4. Unlabeled synthetic data: cleared (banner on every page, "ใบงานตัวอย่าง (จำลอง)").
5. Draft looks approved: cleared ("ร่าง ยังไม่อนุมัติ" on every review screen).

## Top-5 status
1. Kind marking: done, partial (no hot surface, points not editable, not shown in audit).
2. Evidence semantics and gate in first screen: done.
3. Confirm consequences plus second reviewer: done. Button text "ส่งให้ จป. ตรวจ แล้วอนุมัติ" is ambiguous: does approval happen before or after จป. signs? State it.
4. Page image / jump / second window: done but thumbnail unreadable; no zoom.
5. Populated states: health done (120-day window, definition of failure and MTBF stated in plain Thai, sortable header, numbers consistent: 5 failures in 120 days = 24 days). Audit-closed shows header, work segments, outcome, lock release, note, but **not the snapshot steps**: no step text, page, kind, or revision difference. For an auditor that is the whole point of the screen. Print A4 render still not shown.

## Appeal (honest)
Yes, I would open this daily for review work: calm grey/white, strong hierarchy, Thai readable, black "ร่าง ยังไม่อนุมัติ" tag, status icons plus words, nothing decorative. It beats my PDF + Word routine and is closer to Maximo status banners than to SAP. Holding it back from 5: the right panel is sparse under the picker at 1920 (empty lower third), the up/down hint renders as a stray vertical arrow icon with wrapped text, the page thumbnail is a gray postage stamp, tables (health, audit) are plain with no emphasis on the rows that matter (e.g. highest failure machine, mismatched number inside the line). Nothing ugly, but not yet something I would show a customer auditor with pride.

## Remaining fixes
1. Add "ผิวร้อน" kind (with cool-down minutes and hazard code), and make isolation points editable with an "add point" action; show kinds in audit.
2. eng-audit-closed: render the snapshot table (step, kind, page, revision) with print A4 preview; show draft/approved/needs_review word for every revision referenced.
3. Enlarge the page image (click to zoom or toggle to image view) so tables and figures are actually readable.
4. Clarify the final button: approval happens only after จป. confirms, and show who is waiting.
5. Polish: fix the arrow-hint layout, fill the right panel (show the neighbouring step or page 4 preview), highlight the mismatched number inside the Thai line.

## Verdict
**Pass with fixes.** All three of my r3 blocking issues are resolved except hot surface and audit snapshot. I would trust this for real approvals once fixes 1 and 2 are in; fixes 3 to 5 decide whether it is also a screen I enjoy rather than merely accept.

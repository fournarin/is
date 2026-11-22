# w2-check (independent)

BLOCKERS: none
(report/measure.json and board/measure.json: all records have hscroll false, no clip/overlap, minFont 18, minTap 56 on phone / 48 desk.)

## A. Set 4 report vs spec - MET (structure), PARTLY on one point
- Same structure as spec report*.png: dark station header, "stopped?" radio pair (required), "what seen" checkboxes + "พิมพ์เพิ่ม (ไม่บังคับ)", urgency 3 taps, disabled send bar with "ยังต้องตอบ: ..." hint, calm grey/white look. (report.390x844, report.1280x800, report-answered.*)
- Machine by station list (report-stations: 4 stations, 66 px rows, "สแกน QR" hint) or QR/?machine= preselect. Spec's "which machine" chooser for stations with several machines is not shown in any shot (not needed by data: stations have one machine here).
- Photo: question "4 รูปถ่าย ไม่บังคับ · 1 รูป" visible at 1280; at 390 it is below the fold (only seen in report.1280x800). Result seen in report-sent ("รูป" link) and tech-job-photo.
- Reporter's reports as 4-stage track, no technician names (report-sent.390.full). Met.
- Differences from spec: question 3 header sits at the fold under the sticky bar at 390x844 (urgency partly covered); spec had send bar in flow. Acceptable, scrolls.

## B. REQ-P
- P-01 Built: supported. send visible at 390 and 360 (report-answered.360x640 shows enabled send); 3 answers then send.
- P-02 Partial: supported. station list + ?machine= shown; partial-code typing absent, as claimed.
- P-03 Partial: supported. station name large above code (report.*); no nickname, as claimed.
- P-04 Built: supported. question 1 "เครื่องหยุดอยู่ไหม / ต้องตอบ", own block.
- P-05 Built: supported. four stages with same words in report-stations and report-sent.
- P-06 Built: supported. no names in any track or card; tech names absent in report-sent.full.
- P-07 Partial: supported. report-already shows own open report text; report-refused lists WO-000004/9/13 with "นี่คนละเรื่อง" button.
- P-08 Partial: supported. sentence shown in stations and sent; no phone, as claimed.
- Q15 photo Built: supported by report-sent "รูป", tech-job-photo "รูปจากคนแจ้ง" thumbnail, report.1280 photo field.

## C. Earlier fixes
- C1 MET: board/measure.json "board@360x640" primaryBottom 617 (<640); board.360x640.png shows "ยืนยันให้ สมชาย" fully above the fold. README says "fold 617"; key in json is primaryBottom (same value).
- C2 MET: tech-step-verify.360x640.png sticky bar reads "ต่อไป: วัดที่ CP-3"; step title is "ขั้นตรวจพลังงานเป็นศูนย์".

## Non-blocking notes (worst first)
1. Photo control is only visible in the 1280 shot; add a 390 shot scrolled to question 4 (and a photo-chosen state) so P/Q15 evidence shows on a phone.
2. Section labels ("1 เครื่องหยุดอยู่ไหม", "2 เห็นอะไร") sit on the card's top edge, not inside/above it (visible at 390 and 1280); looks slightly off, not clipped.
3. At 390x844 urgency (q3) is half-hidden behind the sticky send bar on first view; optional field, so fine.
4. README cites "fold 617" but json key is primaryBottom; tidy wording.

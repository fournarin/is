# Phase 3 set 1 review - fixes (Cowork, 2026-11-16 11:25)

s1-aesthetics.md (Opus): technician phone 3.5/5 - below the gate (Q12 >= 4). The build is well made and
faithful in tokens and components (type 18/24/36, weights 400/600, colours = tokens, Lucide, rail, sheets),
but it LOST approved content and turned tech-job from structured data into prose.
s1-check.md (Sonnet): CONDITIONAL - phone rules all pass (taps >= 56, gaps, no h-scroll, no Thai splits,
contrast >= 7.90, banner everywhere); blockers are the same missing content. Note: shots/v2/pages/ holds
LEGACY-UI SSR captures (no .v2 CSS) - re-capture SSR from the v2 build next time.

## [M] Blockers (restore the approved spec; build backend where data is missing - Q8 allows it)
1. tech-job: put back, as in design/system/screens/tech-job.html: status line "กำลังทำ · ขั้น 2 จาก 6 ·
   เริ่ม hh:mm" and button "ทำต่อขั้น 2"; severity marker; signal tiles (value / threshold / trend);
   tools list; "ครั้งก่อนที่เครื่องนี้" repair history (synthetic label); "ถัดไป N งาน" row; approval
   footer (revision, approver, date). Replace the 5-line justification paragraph with the spec's
   structured blocks. These were NOT declared as gaps - say so in ROUNDS.md.
2. Station plate: station NAME (not only the number) and keep a slot for the 8-lamp strip; add a
   technician-readable line endpoint now (small, read-only) rather than waiting for set 3/5.
3. tech-step-normal: manual excerpt with "(จำลอง)" label and figure thumbnail from the cited page.
4. tech-noplaybook: headline 24 px and the "โทรถามวิศวกร" row.
5. tech-manual: render a page WITH text (index the corpus with the authoring worker for the design world)
   and build the spec's Wi-Fi-lost state.
6. tech-step at 360x640: primary button bottom at 639 - give it real margin above the fold.
## Polish
7. Drop the repeated "ขั้นที่ 4 จาก 6"; disagree textarea not prefilled, no resize grip; replace the
   amber-outlined chip with the spec's chip + swatch (amber only for threshold/forecast).
8. MEASURE: add font weights; SSR captures from v2.
## Not scored (set 2)
- tech-step lockout capture shows step 2 as a normal step (no ISO signs / isolation points) - set 2; this
  capture must not be read as approved.

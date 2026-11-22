# Round 0 panel - consolidated fixes for concept V (2026-11-15 17:25)

Six fresh reviewers judged the 16:41 snapshot of A/B/C. Full files in this folder:
aesthetics.md, technician.md, shift-lead.md, safety.md, production-it.md, examiner.md.
Apply EVERYTHING below to design/concepts/V (base C + borrowed parts, see HANDOFF.md).
Items marked [M] are blocking for the next review.

## Rankings
aesthetics C>A>B · technician C>A>B · shift lead C>A>B · safety C>B>A ·
production-IT B>C>A · examiner A>C>B. => C as base confirmed (4 of 6 first; no red line
in C that is not a one-line fix).

## Red lines found (must not reappear in V)
- [M] "สายหยุด" on station 4 (C): the system cannot know the line stopped (no Andon feed;
  REQ-S-01). Use "เกินเกณฑ์" / "เครื่องหยุด (ผู้แจ้งระบุ)" only where a source exists.
  Remove NEW_line_stopped from the fixture.
- [M] Hazard-tape stripes for "คาดว่าจะเกิน" (C); safety-yellow triangle for severity (A).
  ISO 3864 safety colours/shapes must not encode predictions or severity. One calm amber
  (no stripes) for "predicted", shape+text for severity (A's ■ ◇ ○ idea).
- [M] Text overprint (B sign page, "10 N·m"). V must be checked at 360 for any overlap.
- [M] Operator report needs 4 taps because urgency is mandatory (all). Urgency optional, no
  default; "เครื่องหยุดอยู่ไหม" starts empty; backend derives urgency (NEW_urgency_source).
  QR path <= 3 taps, manual <= 5.
- [M] Submit button below the fold at 390x844 (C report). Sticky action bar in normal flow
  (no 100vh/100dvh layout; A's clipped on Android Chrome 100-107).
- [M] Close/lock contradiction (all): close must read the step state; if the lock step was
  done but the unlock step was not, show a stop box naming the step and refuse "ปลดกุญแจแล้ว
  เครื่องคืนสู่การผลิต". Undone-steps list built from the same state as the step page.

## Honesty / data (examiner) - Cowork's own fixture error
- [M] The English "manual original" lines and the document code B-83284EN/09 in fixture.json
  were invented by Cowork when writing the fixture. Page numbers 142-147 come from the repo
  demo seed. In V: drop the document code; label the English line "ตัวอย่างข้อความคู่มือ (จำลอง)"
  until real manual text exists. Fix the fixture accordingly.
- Use only fixture data (no invented lock-number fields or report options; add to fixture as
  NEW_* with a stated source if needed). "มาตรฐาน" -> "ประมาณ" for time estimates.
  Outcome wording "ไม่พบอาการ" (REQUIREMENTS) not "ไม่พบปัญหา". tech-job shows status assigned.
- [M] rationale.md: every on-screen element -> REQ ID; every NEW_* field -> source.

## Missing states to draw [M]
Technician: manual viewer + load failure; offline "เก็บในเครื่อง ยังไม่ส่ง" -> "ส่งแล้ว hh:mm";
new-job bar; handover screen (next person locks before the first unlocks); disagree sheet;
"ถัดไป N งาน" on the first screen.
Shift lead: set-aside reason picker (S-06); 5-s undo + "ส่งถึงช่างแล้ว" (S-04); stale-data
banner (I-04); expired proposal place; row click -> read-only ticket drawer; expandable reason.
Operator: after-send states (WO number + server time; or queued, Wi-Fi vs server down,
maintenance extension, typed text kept); logout on shared device with queued report.

## Board layout
- [M] 1024x768 must work (REQ-S-10; A scrolled sideways, C one word per line).
- [M] 1920x1080: whole board without page scroll, using the full width.
- Rows <= 2 lines; full priority reason visible (no "..."), expandable detail.
- One primary action per row; reassign/hold as quieter controls.
- Technician strip visible at 1280; sorted by free minutes; flag overruns > 50% of estimate
  as text; name jobs by machine, not WO number; on a wall screen hide names/minutes (PDPA).
- "Same machine already has an open job" chip; reassign panel warns when the person already
  has a proposal (B's idea). One source for every value (MC-004 ETA = 21:10, not 21:00).

## Visual craft (aesthetics; owner: as important as function)
- About 5 type sizes; spacing scale 4/8/12/16/24/32/48; one canvas tone + raised surface;
  half the borders (outlines for inputs only).
- Replace grey explanatory sentences with visual encodings (bar, shape, bold number).
- Thai: one family (Plex Sans Thai Looped body; loopless only for large headings/numerals);
  no breaks inside words (nowrap spans / Intl.Segmenter + <wbr>, text-wrap: balance).
- Right controls: radios/segmented for single choice; solid but not pure-black selected
  state; no dashed borders for future states; no repeated chevrons; one coherent 24-px icon
  set (flag icon not reused for two meanings).
- Glove use: >= 8 px between targets; decision text >= 18 px dark ink; no typing at the
  machine (tap-to-pick for lock state).
- Fonts <= 120 KB per page (one Plex Mono weight, subset).

## Safety (isolation steps) - DECIDED: IN PHASE A (owner, 2026-11-15 17:08)
Safety reviewer: with owner decision Q2, the normal step screen lets the CP-3 lockout step
pass with one tap, so no concept is usable on a real machine; the Phase B isolation screen
fixes it. Owner decided (Q9): make engineer-marked isolation steps (B's
sequence: breaker off -> my lock -> lock number -> zero-energy check after all points;
hot-surface wait with start time; restore checklist where only the lock owner unlocks; lock
ownership shown on steps, close, handover and a "เครื่องที่ล็อกอยู่ตอนนี้" list on the board)
part of V and of Phase A (backend: Step.kind, isolation points, lock records, with an ADR).
Design it as the main step screen for isolate/hot-surface/restore steps; normal steps keep the
normal screen; also drop A's "เครื่องไม่มีพลังงานค้าง" claim (state what was observed);
use official ISO 7010 artwork.

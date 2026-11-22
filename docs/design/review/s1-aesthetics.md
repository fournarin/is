# S1 aesthetics - Phase 3 set 1 build vs approved spec (role 6)

Method: I put the build captures (v2/set1, 390x844 and 390 full) next to the GATE 2 spec PNGs (system/png) for tech-job, tech-step-normal, tech-step, tech-manual, tech-states vs disagree/handover, tech-job-empty and tech-noplaybook, and compared tech-job at 1280 the same way. I read measure.json and ROUNDS.md only after looking.

## Score: technician phone (build) = 3.5 / 5. Below the gate.

What carried over well:
- The chrome is faithful: type is only 18/24/36 (measured), Plex Looped 400/600, the black primary button, white grouped rows with Lucide icons, the step rail with check squares, the canvas/surface/sunk layering, the synthetic banner, and the station number tile.
- Measurements are clean: no h-scroll, clipping, split words or overlap, 56 px taps.
- The new 4/6 counter is a nice compaction.
- The disagree and handover sheets, the job-empty screen and the manual-failure state match the spec closely.

The problem is not the craft. The build drops the content elements that made the spec feel premium and trustworthy, and what remains is mostly text in white cards.

## Fidelity diffs, ranked

1. **tech-job, all viewports, plate.** The station name ("ติดตั้งหลังคา") and the 8-lamp strip are gone, and the title is now "MC-012". The strip was the system's signature (it also forms the sign-in wordmark). Without it the plate is a generic dark header. *Declared gap. It hurts the score: about -0.5.*
2. **tech-job 390 full: data blocks lost, not declared.** Missing are the sensor tiles (78 / 85 °C / 1.4 °C/ชม. with the forecast swatch), "ครั้งก่อนที่เครื่องนี้" history, the tools list, the "ถัดไป 1 งาน" row and the provenance footer ("ฉบับที่ 3 · อนุมัติโดย…"). In their place is a 5-line justification paragraph ("ทำไมต้องทำงานนี้ก่อน") that repeats the severity and symptom. The page goes from structured to prose. This is the biggest appeal loss.
3. **tech-job 390, status line.** The severity marker ("◆ สูง") and "ขั้น 2/6 · เริ่ม 10:05" are gone. The button says "ทำต่อ" instead of "ทำต่อขั้น 2". The new amber-outlined chip "ยังไม่เสีย · วางแผนซ่อม" is a chip style the spec does not have (forecast is the outline swatch next to a label). Use the sunk chip plus the swatch.
4. **tech-step-normal / tech-step 390, step card.** The manual excerpt (English quote with page) and the figure thumbnail are replaced by a plain "อ่านคู่มือหน้า 145" link row. "ขั้นที่ 4 จาก 6" repeats the counter directly above it; drop it.
5. **tech-step 390 (the lockout step).** It renders as a normal step: no ISO M021/W012, no "อันตราย", no isolation-point list. *Declared as set 2.* It is not scored here, but this capture must not be read as approved.
6. **tech-noplaybook 390.** The 24 px headline "ไม่มีขั้นตอนที่อนุมัติสำหรับงานนี้" is now an 18 px line in a card. The "โทรถามวิศวกร" row is gone. The handover row card has empty padding below its label. Restore the spec hierarchy.
7. **tech-states-disagree 390.** The textarea is prefilled with the selected radio's text ("มีงานอื่นต้องทำก่อน" appears twice) and shows a resize grip. Leave it empty with a placeholder and hide the grip. The same grip appears on handover.
8. **tech-manual.** It shows "ระบบยังไม่ได้อ่านหน้านี้" (declared). This does not lower the score, but the core manual view (page text and image, back-to-step bar) is **unverified**, so I cannot certify it.
9. **Declared new-job bar / offline strip missing.** No effect on these static screens' beauty. It is a functional gap for production-it and technician; it does not count against the score.

## Blockers to reach 4/5

- **B1.** Restore the tech-job data blocks (diff 2) and the status line (diff 3) from data that already exists: severity, current step, sensor reading, history and provenance. Cut the justification paragraph to one line plus "ดูเหตุผล".
- **B2.** Restore the plate identity. Show the station name now (from the work order or station config). The 8-lamp strip can wait for the line endpoint, but leave the slot for it rather than collapsing the plate.
- **B3.** Restore the step-card manual excerpt and figure thumbnail (diff 4). Labelled placeholders are fine, as in the spec.

Diffs 6-7 are quick polish. They do not block on their own, but they are needed together with B1-B3 to clear 4.

## Verdict

**Not yet. Set 1 passes on craft and fails on fidelity: 3.5/5.** The build kept the design system's skin but lost its substance on the job and step pages. With B1-B3 done, plus diffs 6-7, I expect 4/5. The tech-manual page-with-text render is needed before the technician audience can be signed off.

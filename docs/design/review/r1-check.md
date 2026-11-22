# R1 acceptance check - concept V (2026-11-15)

Method: Playwright + /usr/bin/google-chrome. Phones at 360x640 and 390x844 (14 pages), board.html at 1024x768, 1280x800 and 1920x1080. A script measured the DOM: text-rect overlaps, tap targets and gaps, primary-button bottom versus fold, scroll size, Thai line breaks per character, contrast for every text node, computed font sizes, font bytes and external requests. I looked at the current contact sheets (sheet-360-0..3, board.*.png; the sheet-390full PNGs are older than the HTML, so I did not use them). Every value was checked against data/fixture.json.

## Results

| # | Item | Result | Evidence (screen, viewport, measured) | Fix |
|---|---|---|---|---|
| 1 | [M] No line-stop claim | PARTIAL | "สายหยุด" is gone from screens. It appears only in the operator emergency hint, which is fine. NEW_line_stopped is gone from the fixture. But "เครื่องหยุด" appears 6 times on the board for MC-018: the station-4 tile at 1920 says "เกินเกณฑ์ · เครื่องหยุด", the legend says "MC-018 เครื่องหยุด", and the row and drawer say the same. Its fixture source is a *condition* proposal whose state_th has no source. The real API dumps only say "ถ้าเครื่องหยุดตามที่พยากรณ์" | Add a NEW_ source (interlock signal), or reword to "ระบบล็อกนิรภัย: ประตูเปิด". Put it on the machine, not the station tile |
| 2 | [M] No ISO stripes or yellow for prediction/severity | PASS | Predicted = amber outline; severity uses ■◇○ + word. The only repeating gradient is an ink "ส่งต่อ" bar | - |
| 3 | [M] No text overprint at 360 | PASS | 0 overlapping text rects on all 14 phone pages at 360 and 390, and on the board at all 3 sizes | - |
| 4 | [M] Report taps | PARTIAL | Urgency is "ไม่บังคับ" with no default. "เครื่องหยุดอยู่ไหม" starts empty. QR path = stop + symptom + send = 3 taps. The manual path is not drawn; estimated "เปลี่ยนสถานี" → station → machine → stop → symptom → send = 6 taps (more than 5). The machine is preselected (MC-025) for a QR that is bound to the station | Draw the manual path with ≤5 taps. Preselect a machine only for a machine-bound QR |
| 5 | [M] Send in view at 390x844, no vh | PASS | report.html at 390: send button 768-832 px (empty state). Ready state is also 768-832 once the demo label is removed. No vh/dvh, no fixed elements. The margin is only 12 px, and the button is not sticky (it is at 863 at 360x640) | Note: in-browser chrome will push it below the fold |
| 6 | [M] Close/lock contradiction | PASS | tech-close-locked: "ปลดกุญแจของฉันแล้ว…" is disabled ("ทำขั้น 6 ก่อน"), a stop box names step 6, and "ยังล็อกอยู่" is preselected with CP-3/ก-03 from the register. tech-close-confirm lists undone steps 2-6 from the same state. Remaining gap: on tech-close (step 2, register empty) "ปลดกุญแจของฉันแล้ว" is still enabled | Disable "ปลดกุญแจ" when the register holds no lock of mine. Fix numbering 1→3 on the locked variant |
| 7 | [M] Manual text honesty | PASS | No B-83284 anywhere. The English line is labelled "ตัวอย่างข้อความคู่มือ (จำลอง)" on all 4 step pages. Fixture has NEW_manual_text_is_sample + source | - |
| 8 | [M] rationale: element→REQ, NEW_*→source | PARTIAL | The table maps decisions, not elements. No source given for NEW_state_detail, NEW_priority_parts, NEW_reason_detail, NEW_stage_times, NEW_observation_choices. Several on-screen lists exist in neither the fixture nor the REQs (see 26) | Add the missing sources. List every on-screen option set |
| 9 | [M] Technician states | PASS | Manual failure (tech-manual: "โหลดหน้า 143 … ไม่ได้", retry + back); viewer placeholder; offline → "ส่งแล้ว 10:43"; new-job bar; handover; disagree sheet; "ถัดไป 1 งาน" on first screen | - |
| 10 | [M] Shift-lead states | PASS | Set-aside reasons = REQ-S-06 list, button off until chosen; toast "ยกเลิก (5)" + "ส่งถึงวิชัยแล้ว" row; stale banner; "หมดเวลา 0 ใบ" place; read-only drawer; reassign warns "ระบบเสนอ MC-028 ให้แล้ว" | - |
| 11 | [M] Operator states | PASS | Sent (WO + time), queued Wi-Fi, server down + retry 30 s, extension "ยังไม่ได้ตั้งค่า", logout with queue (send/discard), no technician names | - |
| 12 | [M] Board 1024x768 | PARTIAL | No sideways scroll (scrollWidth 1024). Only 1 proposal row is above the fold (table starts at y≈590), and rows wrap to 3-4 lines | Collapse the crew strip to one line, or move it below the table, at <1200 px |
| 13 | [M] Board 1920 no page scroll | PASS | scrollHeight 1080 = viewport; full width used | - |
| 14 | Tap targets / gaps | PARTIAL | Phones ≥56 px except the new-job bar "ดู" at 45x56 (tech-states, 360 and 390). Board ≥48. 0 neighbouring-target gaps <8 px | "ดู" ≥56 px wide |
| 15 | Thai breaks inside words | PASS | Per-character check: 0 breaks inside a word on all pages and viewports. The flagged breaks (e.g. "ลองส่ง|ใหม่", "ส่ง|แล้ว") fall between words. Some sentences are not span-segmented and rely on Chrome's own word breaking | - |
| 16 | Truncation | PASS | No ellipsis, no clipped overflow; priority_reason is shown in full | - |
| 17 | Contrast | PASS | Minimum 7.05 on the board (ink on amber), 7.42 on tech-job, 7.90 on other phone pages. 0 text nodes below 7:1 | - |
| 18 | Fonts / network | PASS | 86,940 B per page (Plex Sans Thai Looped 400+600); 0 external requests; no emoji | - |
| 19 | REQ-G-06 phone body ≥18 px | FAIL | 15 px text on phones: tech-step has 519 of 974 characters at 15 px, report 576 of 835. This includes the lock-owner strip "ล็อกอยู่ CP-3 · กุญแจ ก-03…", the energy type "ไฟฟ้า", "จุดตัดพลังงาน 1 จุด", and the duplicate-report notice "แจ้งไว้แล้ว 09:52…" | 18 px for all phone content; 15 px only on desk |
| 20 | Values vs fixture | FAIL | tech-job shows status "รอเริ่ม" and a "เริ่มงาน" button. The fixture has my_job.status=in_progress, started_at 10:05, current_step 2; the board shows "พิมพ์ชนก กำลังทำ MC-012 เริ่ม 10:05", and the step pages are at step 2. Everything else matches: crew minutes and sort, lost units 40/37/18/6/70/15, ETA 21:10 and 03:00, load 2,976/4,800, next round 3 min, held/set-aside/finished, "ไม่พบอาการ". Fixture-internal problem: MC-004 NEW_state_detail says "21:00" but state_th says 21:10. Operator stage labels ("หัวหน้ากะส่งช่างแล้ว…") do not match fixture `stages` | Show "กำลังทำ · ขั้น 2 จาก 6 · เริ่ม 10:05" + "ทำต่อขั้น 2". Fix the 21:00 field. Use the fixture stage labels |
| 21 | Isolation step | PASS | Per-point ticks (breaker → my lock → lock no. tap ก-03/ก-04 → try-start observation), Next disabled with "ยังต้องยืนยัน…"; no "no residual energy" claim | - |
| 22 | Lock ownership visible | PARTIAL | Strip on steps 3/4/6, close and handover shows owner + point + lock no. but "ใส่เมื่อขั้น 2" has no time (R-H8 asks for time). Board "เครื่องที่ล็อกอยู่ตอนนี้" = "ไม่มี" (matches empty NEW_locks_now) | Add applied_at "10:2x" |
| 23 | Handover | PARTIAL | No-gap order (receiver locks first; my unlock disabled until then) and routing via the lead are good. But REQ-H-06's 3-option lock question is missing on handover, and the board has no action for "ส่งต่อ รอคนรับ" (WO-000105 only shows as a crew-card tag) | Add the question; add a handover row with a "เลือกคนรับ" action on the board |
| 24 | Restore by lock owner | PASS | "ปลดกุญแจ ก-03 ของฉันที่ CP-3 · ปลดได้เฉพาะเจ้าของกุญแจ · พิมพ์ชนก" | - |
| 25 | ISO marks (REQ-H-03, H-13) | FAIL | Marks are 40 px (<48 px AC). M021 "ตัดการเชื่อมต่อก่อนซ่อม" is used on the *restore* step, which is the wrong meaning. No Thai signal word (อันตราย/คำเตือน/ข้อควรระวัง) is visible on the isolation or hot-surface steps | 48 px; drop M021 from restore; add signal words |
| 26 | Safety text only from approved data | FAIL | These lists are not in the fixture or the snapshot but appear under "วิศวกรกำหนด · ฉบับที่ 3": the restore checklist (เก็บเครื่องมือ / ไม่มีใครอยู่ในพื้นที่ / แจ้งพนักงาน), the restore and verify outcome choices, the locked-reason "รอคนช่วย", and the wait chips 0/15/30/60 | Add NEW_restore_checklist_th etc. with a source (engineer/EHS), or label them "ตัวอย่าง ยังไม่อนุมัติ" |
| 27 | Technician red lines | FAIL | RL3 (screen ≠ reality): item 20. RL1, RL2, RL4, RL5, RL6 OK | item 20 |
| 28 | Shift-lead red lines | FAIL | RL2 (status conflict between two screens): item 20. RL1, RL3-RL6 OK; RL3 is weak for handover (item 23) | item 20, 23 |
| 29 | Safety red lines | FAIL | RL6 (unapproved safety text): item 26. RL7 (symbol meaning): item 25. RL1-RL5 OK | items 25, 26 |
| 30 | Production-IT red lines | PASS | Synthetic banner on every screen; operator sees no names; queued states are explicit; ≤3 taps from QR | - |
| 31 | Examiner red lines | PARTIAL | Data is labelled. But the rationale claims compliance that measurement does not support (item 32) | Correct the claims |
| 32 | rationale.md claims | PARTIAL | True: contrast min 7.05, fonts 87 KB, send in view at 390, close reads step state. False or overstated: "10-second scan without scroll" (1280: scrollHeight 1409, 4 full rows; 1024: 1 row); G-06 claimed but phone text is 15 px; "safety from approved data" (item 26); H-13 claimed (item 25) | Rewrite those rows |
| 33 | "Unmet Must REQs" list | FAIL | The listed items are honest (S-01, T-14, H-08, H-10, T-06, G-03, G-12, I-02/I-07). Missing: G-06, H-03 (48 px), H-13, H-06 (handover), S-10 (1024), T-01 (status word), P-01 (manual path) | Add them |

**Counts: 16 PASS · 9 PARTIAL · 8 FAIL** (33 items).

## New red lines found in V
1. **Cross-screen contradiction.** tech-job says "รอเริ่ม / เริ่มงาน" while the board says "กำลังทำ เริ่ม 10:05" and the step pages are at step 2. This hits shift-lead RL2 and technician RL3.
2. **Unapproved safety text shown as engineer-approved.** The restore checklist and outcome choices sit under "วิศวกรกำหนด · ฉบับที่ 3" but are not in the snapshot or fixture. This hits safety RL6.
3. **ISO sign used with the wrong meaning.** M021 (disconnect before maintenance) appears on the restore step. This hits safety RL7 / REQ-H-13.

Still open from round 0: "เครื่องหยุด" for MC-018 has no stated source (item 1).

## Verdict
**Not accepted for round 1 (3 new red lines).** The [M] layout, honesty and state items are mostly met. The board, close/lock logic, isolation flow, contrast, fonts and Thai breaking all hold up under measurement. All the blocking fixes are small and local:
1. tech-job status;
2. ISO marks (48 px, no M021 on restore, signal words);
3. source or label the restore and option lists;
4. phone text ≥18 px;
5. source the MC-018 "เครื่องหยุด" wording.

Then: the handover lock question and board action, the "ดู" target, the lock time, and updating rationale.md (claims + Unmet list).

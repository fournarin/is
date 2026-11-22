# Round 0 review: technician (role 1, "คุณวีระ")

Scope: phone screens of A, B, C (tech-job, tech-step, tech-close + confirm, Phase B isolation, report).
Method: read every png at 360x640 and 390 full, then opened the HTML with Playwright at 360x640 to measure
tap targets, gaps, fixed elements, font sizes and contrast. I did not read any rationale (none exists yet).
I asked one question of each screen: with gloves on, in glare, one hand on a pendant, does it get me to the
next action faster than calling the lead?

## Scores (1-5; 3 = pass with fixes, 4 = pass)

| Criterion | A | B | C |
|---|---|---|---|
| Glance in 3 s (R-T1, R-T12) | 4 | 4 | 5 |
| Gloves (R-T2) | 4 | 3 | 4 |
| Glare / readability (R-T3) | 4 | 3 | 4 |
| Step page (R-T5, R-T6, REQ-H-01) | 4 | 4 | 4 |
| Close + confirm (R-T8, R-T13, REQ-H-06) | 4 | 2 | 5 |
| Trust: offline, auto-update, nothing lost (R-T9, R-T10) | 2 | 3 | 3 |
| Appeal: would I open it instead of calling | 4 | 3 | 4 |
| **Red line hit** | none | **#3 (FAIL)** | none |

**Ranking: C > A > B.** C is good enough to build on. A is close behind, and two of its ideas should go into C.
B fails right now because of one confirm-page bug and one data mismatch. Both are quick to fix, but as rendered
the screen I sign on shows the wrong thing.

## Red lines (from my interview, section 5)

1. Manual/step does not open, or a safety step is covered: no concept covers step text. None of the three
   renders the **manual viewer or its load-failure screen** (REQ-H-11), so I cannot check my top red line. That
   screen has to come next round.
2. Close data lost: no concept shows the offline state "เก็บในเครื่อง ยังไม่ส่ง (n)" and then "ส่งแล้ว hh:mm".
   **A has no offline or autosave wording anywhere on the phone.** B (step, sign page) and C (note, confirm) at
   least say that data is kept on the device.
3. **Screen disagrees with reality: B is hit.** On `B/tech-close-sign` (360 and 390), step 6 renders "10 N·m"
   pushed into the number column on top of "แล้ว", so the torque reads as garbage. Cause: the `li` is a 2-column
   grid and the `<span class="nw">10 N·m</span>` becomes its own grid item. Separately, the list says
   "ยังไม่ได้ทำ 4 ขั้น จาก 6" (steps 3-6) and offers "กลับไปทำขั้น 3". But the step page is on step 2, not
   ticked, and the close page's back button says "ขั้น 2". So the page I sign **drops the lockout step (2) from
   the not-done list**. A and C both correctly show 5 not done (2-6).
4. Manual refresh to see new work: none of the three shows the "มีงานใหม่/งานเปลี่ยน" bar (R-T10). C says
   "หน้านี้อัปเดตเอง", which is the right promise. It is not shown, so it is not met.
5. Close without confirm: all three have a confirm page. A and C handle the double-tap well (see best ideas).
6. Long typing or useless required fields: nothing forces typing. Two risks: "ยังล็อกอยู่ (ระบุจุดและเหตุในโน้ต)"
   in all three pushes typing at the machine, and Phase B in B and C adds a free-text "เลขกุญแจ" box.

## Concept A: stark black-and-white tool, fixed action bar

Best idea to steal: on the review page, the fixed bottom slot that held "ตรวจทานก่อนปิดงาน" becomes
"กลับไปทำขั้น 2". A nervous double-tap sends me back to work and cannot close the job by accident, while
"ปิดงานเลย" sits in the flow above it. The 78 / 85 / 1.4 °C readout on the job card also does more to convince
me than any sentence.
Worst: an app shell with an inner scrolling `<main>`. At 360x640 the step text gets **429 px** of 640 (header
120 + footer 90, measured), and on a real phone the browser bar takes about 56 more. Inner scroll also fights
pinch-zoom. On top of that, A has no offline or sync wording.

Scores below 4, with fixes:
- Trust 2: 360x640, all phone screens. Add the save state line ("บันทึกในเครื่องแล้ว" / "ยังไม่ส่ง (1)" /
  "ส่งแล้ว 10:44") to the header strip, and show a sample of the new-job bar on tech-job.

Other fixes:
- tech-job 360: "คาดว่าถึงเกณฑ์ 15 พ.ย. ประมาณ 14:00" is 16 px grey (#3a3f44). It is decision text, so make it ≥ 18 px ink.
- tech-close 360: the minute buttons 0/15/30/60/อื่น ๆ are 6 px apart. Make it ≥ 8 px.
- tech-close: outcome and lock are single choice but drawn as checkboxes. Use radio rings like C. Also show
  that 0 minutes is the default (the render has 30 pre-selected, so I cannot tell).
- isolation-phaseB 360: "ล็อกเอา|ต์" breaks before the karan (mid-word Thai break). Add a no-break span or `word-break: keep-all` on that title.
- Make the shell thinner: one 56 px header row, then let the page scroll normally and keep only the primary button sticky.

## Concept B: calm, boxed form, navy action colour

Best idea to steal: the vertical step rail "2 จาก 6", plus "ความคืบหน้าเก็บไว้ในเครื่องนี้ ปิดแอปแล้วกลับมาที่ขั้น 2
ได้" under the buttons. That answers my question 1 on the screen. The disabled "ตรวจทานแล้วลงชื่อ" with
"ยังไม่ได้ตอบ: ข้อ 3 สถานะกุญแจ" tells me exactly what is missing.
Worst: the sign page shown under red line 3 above, which is the one screen I trust the most.

Scores below 4, with fixes:
- Close + confirm 2: `tech-close-sign` 360/390. Wrap the `li` text in one element so "10 N·m" flows inline,
  and make the not-done list and "กลับไปทำขั้น N" come from the same step state as the step page (5 not done,
  back to step 2).
- Gloves 3: `tech-close` 360. Outcome 2x2, minutes row and `report` urgency/stopped/observations are tiles with
  **0 px gaps** (shared borders). Gloved thumbs land on the border. Separate them with ≥ 8 px gaps.
- Glare 3: in sunlight the selected state (pale blue tint, thick navy border, small check) is weaker than an
  inverted black fill. Use a full inverted fill for the selected choice. Labels such as "สาเหตุที่ออกใบ",
  "ต้นฉบับในคู่มือ" and the header sub-lines are 15 px. That is fine for labels, but the 360 close header truncates "MC-..." mid-code.
- Appeal 3: it reads like a well-made form, not a tool I would reach for. It is also the only concept with a
  second colour (navy) that carries no meaning beyond "button".

Other: B's report screen invents observation choices ("น้ำมันซึม", "ขนาดชิ้นงานคลาดเคลื่อน") instead of
the 4 in `report_form.NEW_observation_choices`. C uses the fixture correctly.

## Concept C: station-first, black ink, safest confirm

Best idea to steal: the confirm page puts "กลับไปทำขั้น 2" as the big black primary and "ปิดงานเลย ทั้งที่ยังไม่ครบ"
as the deliberate secondary. That is the correct bias when 5 steps are not done. "รอเพราะอะไร" stays disabled
until minutes > 0, and the minute buttons default to "0 ไม่ได้รอ", labelled. The black station block "สถานี 3"
is the fastest arm's-length read of all three.
Worst: the station minimap 1-8 on `report` (360) looks like a row of buttons about 20 px tall, but it is plain
`span`s. With gloves I will tap it and nothing will happen. The manual button on `tech-step` also sits **below
the fold at 360x640**, under the primary, and I open it 2-4 times per job.

Fixes:
- tech-step 360: move "เปิดคู่มือ หน้า 143" directly under the English text, above "ทำขั้นนี้แล้ว ถัดไป" (as A and B do).
- tech-step 360/390: English original is 17 px and "ต้นฉบับในคู่มือ · หน้า 143" is 15 px. Make the English ≥ 18 px,
  because I compare its numbers against the Thai.
- tech-job 360: the reason line ("มอเตอร์สายพานร้อนเกินกำหนด ที่เครื่อง ... แต่แนวโน้มชี้ว่า...") is 17 px grey. Make it 18 px.
  The NEW_signal numbers (78 / 85 / 1.4 °C) are buried as a sentence lower down. Take A's readout tiles.
- tech-step: the flag icon means "ปิดงาน" here but "ไม่เห็นด้วยกับลำดับ" on tech-job. One icon must mean one thing (R-T16).
- report 360: make the minimap 56 px buttons that switch station, or remove it.
- tech-close: minute buttons are 6 px apart. Make it ≥ 8 px.

## Applies to all three

- Lock answer vs steps: every concept lets me confirm "ปลดกุญแจของฉันแล้ว เครื่องคืนสู่การผลิต" (A, B) or
  "งานนี้ไม่ได้ตัดพลังงาน" (C) while the lockout step 2 and unlock step 6 are listed as not done, and nothing
  links the two. Phase A cannot guess (REQ-H-02), but the confirm page should print the lock answer right next
  to the not-done list. Phase B (with `Step.kind`) should name the restore step and stop on the contradiction (REQ-H-06).
- Not delivered yet and needed before I can sign off: manual viewer + failure state, handover with
  "ถึงขั้นที่ N จาก M" pre-filled (R-T14), the "ไม่เห็นด้วย" sheet and the "who sees it" answer (R-T15), the
  post-send result screen, the new-job bar, and the offline queue state.

## Top 5 fixes for today (in order)

1. **B sign page**: fix the grid bug that garbles "10 N·m", and make the not-done list and the back button use
   the same step state as the step page (lockout step 2 must appear). This clears B's red line.
2. **Draw the missing trust states** on the chosen base: offline "เก็บในเครื่อง ยังไม่ส่ง (n)" → "ส่งแล้ว hh:mm",
   the "มีงานใหม่" bar, the manual viewer and its "โหลดหน้า 143 ไม่ได้" screen with retry and back. A needs this most.
3. **Manual button on the first screen at 360** (C), and **give the step text more of the screen** (A's
   429 px window). The step, its English original and the manual must fit in one look.
4. **Gloves**: ≥ 8 px between every target (B tiles 0 px; A and C minute rows 6 px). Make C's minimap real
   56 px buttons or plainly not a button. Show the selected choice as an inverted fill (B).
5. **Decision text ≥ 18 px ink**: A ETA 16 px grey, C English 17 px and reason 17 px. Replace "ยังล็อกอยู่
   (ระบุในโน้ต)" with chips for the isolation point(s) and preset reasons, so I never type at the machine.

Verdict: build on **C**. Take A's sensor readout and fixed-slot double-tap protection, and B's step rail and
"progress saved on this device" line.

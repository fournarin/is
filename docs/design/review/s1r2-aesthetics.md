# S1 round 2 aesthetics - technician phone build vs approved spec (role 6)

Method: I put the new captures next to the GATE 2 spec PNGs, one pair per screen at 390x844, plus tech-job as a full page, and zoomed in on the offline strip. I read measure.json (now with weights) and ROUNDS "Round 2" after looking.

## Score: technician phone = **4 / 5. PASS** under the owner's rule.

The build is now a faithful realisation of the spec. Type is only 18/24/36 at weights 400/600 (measured). There is no h-scroll, clipping, split words or overlap on any of the 27 captures. Surfaces, rows, Lucide icons, the plate, the rail and the primary buttons all match.

## Blockers verified

| # | Ask | Result |
|---|---|---|
| B1 | tech-job data blocks and status line | **Done.** The page shows "◆ สูง · กำลังทำ · ขั้น 2/6 · เริ่ม", the button "ทำต่อขั้น 2", three reading boxes with the forecast swatch, "ครั้งก่อนที่เครื่องนี้", tools, the approval footer, and a live "อัปเดต hh:mm:ss" line. The 5-line justification paragraph moved into the disagree sheet. Laid side by side, the full page has the spec's rhythm. The "ถัดไป" row is absent only because this world has one job, which is acceptable. |
| B2 | Plate identity | **Done.** Station name plus a lamp strip. It has 4 lamps, matching the real plant config; forecast stations are outlined amber and the own station is white. The signature is back. |
| B3 | Step-card manual excerpt + figure | **Done.** "ต้นฉบับจากคู่มือ · หน้า N" with real manual text under the Thai. The figure is a labelled icon tile until PDF.js arrives, which is acceptable because it is labelled. |
| Polish | noplaybook 24 px heading + "โทรถามวิศวกร"; no repeated "ขั้นที่ N จาก 6"; disagree textarea empty with no grip; chip + swatch instead of the amber chip | **All done.** |

## Remaining (none block)

1. **tech-manual 390, page text.** The extracted text runs the page title into the body ("…corrective procedure Symptom: belt motor…"). Set the page title on its own line at 600 weight and keep the line breaks from the PDF. It is readable, but it looks like a raw dump next to the crafted chrome.
2. **tech-offline 390, strip icon.** The wifi-off icon is about 10 px and grey on andon, so it is nearly invisible. Make it 20 px in `--on-andon`, as on the components page.
3. **tech-job 390, symptom line.** "มอเตอร์สายพานร้อนเกินกำหนด ที่เครื่อง MC-012 · …" repeats the H2 directly above it. Start the line at "ยังไม่เกินเกณฑ์…" as the spec does.
4. **tech-job 390, history heading.** The "จำลอง" label is now a sunk chip, while the spec has bold plain text. It is harmless, but use one form system-wide.
5. **tech-step 390 (lockout, step 2)** still renders as a normal step with no ISO M021/W012, no "อันตราย" and no isolation points. This is declared for set 2, so it is not scored. **It must not ship as is**, and set 2 must be judged against spec tech-step.

## Verdict

**PASS: technician phone 4/5.** All three blockers and the polish items are verified in the captures. Items 1-3 are quick and would push this toward 4.5. Item 5 is a set-2 gate item, not a set-1 one.

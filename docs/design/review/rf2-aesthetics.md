# RF2 aesthetics - refresh round 2 (Q14: light only, calm first) (role 6)

Method: I looked at the refreshed spec PNGs (board 390/1280-drawer/1920, line-overview 1920) and the app re-captures at 390 (tech-job, tech-step-normal, tech-close-locked, report), and zoomed in on the board rows at 1920. I read ROUNDS "Round 2" after looking. Each audience gets a separate **calm** score (is it obvious where to look first?), and dense screens fail. Note: PANEL.md does not contain the Q14 calm rule yet (its last section is the Q12 gate). I applied the rule as the coordinator described it.

## Scores (vs Vercel / Apple)

| Audience | Score | Calm | Target | Note |
|---|---|---|---|---|
| Board | **4.5** (wall 4) | **5** | 4.5 | It now looks like the owner's own words: one focal card ("วิกฤต", the title, one number, the name, "ยืนยันให้ วิชัย"), 5 one-line rows, the strip as 8 numbers, and the rest behind tabs. The drawer at 1280 is Apple-grade. A clear improvement on R1. |
| Technician phone | **4** | 4 | 4.5 | tech-step is calm and lovely: the new thin rail with one outlined step, one sentence, one button. tech-job still says the forecast twice (see below). |
| Line overview | **3.5** | **3** | 4 | **Fails the calm rule.** Station strip, floor plan and "สถานีที่ต้องดู" all compete for first look. The page is taller than 1080 at 1920, so the machine list falls below the fold. |
| Engineer | 4 | 3.5 | 4 | Review is reading work, and its density is earned. eng-gaps is now one list. |
| Operator report | 4 | 4 | 4 | Light tokens; three questions with one action. |

## Still dense (screen + viewport + element)

1. **line-overview 1920.** Station numbers appear three times: in the card strip (8 cards with name + status), in the plan, and in the side panel. Each plan box carries 1-2 "MC-0xx" codes plus heavy black dots (12 codes). The side panel repeats the MC code, status, ETA and buffer for each item.
2. **tech-job 390, forecast duplicated.** "ถึงเกณฑ์ราว 17 พ.ย. 16:22 น. · ±2 ชม." sits under the title, and "คาดว่าจะถึงเกณฑ์ราว 17 พ.ย. 16:22 น. (คลาดเคลื่อนได้ ± 2 ชม.)" repeats it under อุณหภูมิมอเตอร์. The status row also carries 4 items (◆ สูง · กำลังทำ · ขั้น 2/9 · เริ่ม 10:22).
3. **board 1920 wall, type and width.** The rows are about 15-16 px inside a column about 1376 px wide, leaving about 270 px empty on each side and about 130 px empty at the bottom. It is calm, but not readable from 3 m. The severity word ("ปานกลาง") sits about 3 px above the title baseline.
4. **board 390/1920, rows.** The number comes before the name ("37 คัน ธนพล"); the rule says names first. The button label "ยืนยันให้  วิชัย" has a double space.
5. **board, the tab chips under the queue** ("ช่างในกะ ว่าง 5 จาก 10 คน" …) look like small floating cards with centred text. Make them a real segmented tab row, label + count on one line, aligned to the queue edge.
6. **tech-close-locked 390, the lock question.** It is a 5-line explanatory paragraph. Reduce it to one line ("กุญแจ ก-11 ยังล็อก CP-3") and put the rest behind "ทำไม".
7. **measure.json** counts 15 px nodes at 390 for board and board-15 (142 and 289), probably hidden drawer content. Count visible text only, so that the 18 px phone floor can be proved.

## Minimum fixes to reach the targets

- **Line overview (to 4, calm 4):** use the board's compact 8-number strip in place of the 8 cards. Make the plan the single focus: lamps only, dots without codes, and the MC code shown on tap. Make "สถานีที่ต้องดู 3" one line per station (name + state), with details in the drawer. Move the machine list to a tab with a count. Fit 1080.
- **Technician phone (to 4.5):** drop the second forecast line and keep the readings and swatch. Make the status row "◆ สูง · ขั้น 2/9". Apply fix 6.
- **Board wall (keep 4.5 overall):** at ≥1600 px scale the content by about 1.25 (rows 18-20 px, focal title 36) so it fills the width. Align the severity word to the baseline, put the name first, and fix the double space.

## Verdict

**Not yet.** The board passes at 4.5 with calm 5. It is now something an advisor would proudly show a plant, and it beats my previous favourite. The technician phone is at 4 (target 4.5) and needs only text cuts. The line overview fails the calm rule at 3.5/3 and needs the strip/plan/list hierarchy fixed. Engineer and report pass at 4.

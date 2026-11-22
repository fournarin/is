# RF aesthetics - visual refresh (Q13), judged against Vercel / Apple (role 6)

Method: before/after pairs at 390 (tech-job, tech-step, close, handover, history sheet, board phone). Refresh spec PNGs: board and line-overview at 1920 dark; board, eng-review, eng-review-queue and eng-gaps at 1280; phone sheet at 390. I read the spec measure.json after looking: no h-scroll, clipping or split words on any capture; sizes are 15/18/24/30/36. The benchmark is now Vercel's dashboard and Apple's own apps, not HMIs.

## Scores

| Audience | Before | After | Target | Note |
|---|---|---|---|---|
| Technician phone | 4 | **4** | 4.5 | The bottom sheets are genuinely Apple-like: dimmed page, "ปิด", 2-line history rows with a chevron. Plex Mono for codes is a good Vercel touch. But tech-job and tech-step above the fold are almost pixel-identical to before, so the visible surface did not move. |
| Board | 4 | **4** (wall 4.5, phone 3.5) | 4.5 | The 1920 dark wall is the best screen in the project: black canvas, lamps as the only colour, two-line rows with no ellipsis, one inverted "ยืนยัน". The 390 phone board is still text-heavy and cramped. |
| Line overview | 4 | **3.5** | 4 | At 1920 it is the old light layout recoloured. The floor plan is dark boxes on dark with low separation, the bottom half (aisle, rooms) is dead space, and about 200 px is empty below. |
| Engineer | 3.5-4 | **4** | 4 | eng-review's two-line steps with the evidence column read like a Linear/Vercel diff view. The queue is clean. eng-gaps' four number cards edge toward a bento template, but it is acceptable. |
| Operator report | 4 | **not re-captured** | 4 | It is not in the refresh sets. I carry 4 provisionally; it needs a 390 capture on the new tokens. |

## Did "less text, detail behind a tap" hurt?

- **Technician: no.** Severity, step, forecast, the three readings, lock strip, ISO signs and the manual's English all stay on screen. Only history notes, ranking reason and the step list moved into sheets, which is correct.
- **Shift lead: a risk at the wall and on tablets.** The reason is now a *hover* preview or the drawer. A wall has no pointer and a 1024/1280 tablet has no hover. The row still carries symptom + ETA/status, which is enough to decide most rows. Make sure a tap opens the drawer on touch and that the drawer is captured. I did not verify this. It is not a blocker if it works.

## Top fixes (ranked)

1. **line-overview, 1920 wall: floor plan.** Use hairline station outlines (on-andon-2 at 40 %) with no filled boxes. Lamps on the plan should carry the only colour, matching the strip. Shrink the aisle/rooms band to about 60 px and give the plan the freed height, or end the page at the list. *Needed to reach 4.*
2. **board, 390: header and KPI band.** The subtitle wraps to 3 lines next to the clock, and the KPI band takes about 250 px, so the first queue card starts at about y 640. Put the subtitle on one line with the clock on its own row, use a single-row KPI strip (6 ใบ · 4 งาน · งานปกติ · 3 นาที), and collapse the 4-line queue meta to "เสนอ 10:40 · หมดเวลา 11:10" with the rest in a sheet. *Needed for board 4.5.*
3. **tech-job, 390: above the fold.** Make the forecast one bold line ("ถึงเกณฑ์ราว 05:23 น. ±2 ชม.") and move "ยังไม่เกินเกณฑ์…" and "อัปเดต hh:mm:ss" into the reading block's caption. Trim the plate to station + MC-012 and put R-2000iC and WO in the sheet. This is what Apple would cut. *Needed for phone 4.5.*
4. **tech-close-locked / tech-handover, 390: legend overrun persists.** "ต้องตอบ" ends at about 382 against a card at 374 (flagged in S2). The outcome radios still sit in a shared card while the lock options are tiles, which makes two option styles.
5. **board, 1920 and 390: red left bar on the critical row/card.** This is the stripe trope I removed elsewhere. The red square + "วิกฤต" already says it, so drop the bar.
6. **board, 1920: people panel.** About 325 nodes at 15 px on a wall. Use 18 px for names and minutes and keep 15 px only for skills.
7. **board, 1920: "คุณพักไว้ 1 ใบ" card.** It is half empty. Size it to its content or merge it with "ระบบกันไว้".
8. **eng-gaps, 1280.** Replace the four equal cards with one grouped list: number + label on line 1, items below. This is calmer and less bento.

## Verdict

**Not yet at the new bar.** It is better than before and nothing is broken, but only the 1920 wall board reaches Vercel/Apple level. The scores are phone 4 (target 4.5), board 4 (target 4.5), line 3.5, engineer 4, and report not captured. Would an advisor proudly show it to a real plant? **The wall board and technician phone, yes. The line overview, not yet.** Fixes 1-3, plus a report capture, are the minimum to meet every target. Fixes 4-8 are polish.

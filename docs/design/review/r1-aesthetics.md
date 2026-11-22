# R1 aesthetics review - concept V (role 6)

Seen: all 16 pages via contact sheets and board renders (1024/1280/1920, menu/undo states), plus a live Playwright pass (chromium) at 390 and 1920 to measure type, borders and Thai breaks. I read rationale.md only after scoring.

## Scores (1-5)

| Criterion | Score | Note |
|---|---|---|
| First impression | 4 | Looks deliberate, not like a template: the dark andon plate with a lamp line, a calm grey canvas, one ink action colour. It reads as industrial software, not a SaaS kit. It is not yet Linear/Stripe-premium. |
| Typography | 4 | Plex Looped Thai renders cleanly. Measured live: 15/16/18/24/30/36 px and weights 400/600 (one 700). Big step numerals ("ขั้น **2** จาก 6") work well. 15 px body is small for a 1920 wall screen. |
| Layout | 3 | Phone pages have good rhythm. The board at 1920 has an unbalanced bottom zone and uneven row heights. At 1024 it gets cramped. |
| Colour | 4 | Colour earns its place. Amber outline means forecast, solid amber means now, red is only for critical. The ISO-yellow safety signs sit close to the prediction amber. |
| Detail / icons | 3 | Three chip languages, Unicode glyphs (⧗ ■ ◇ ○) mixed with drawn icons, and stale contact sheets. |
| Desirability | Phone 4 / Board 3 | A technician would open the phone app: it feels calm, has one clear next action and trustworthy provenance. The board is credible but reads like a spreadsheet, not a screen you would be proud to put on the wall. |

**Red lines:** none hit in the live HTML. It is not template-looking, Thai is not clipped, and decoration always carries meaning. Close calls: visual weight on the board (a column of 6 black buttons), and one mid-word Thai break that shows only in a stale PNG (see fix 10).

## Predecessor asks: were they done?

| Ask | Status |
|---|---|
| About 5 type sizes | Mostly done. 6 sizes. The 16 px is used on only 2 nodes; fold it into 15 or 18. |
| Fewer borders | Mostly done. Phone pages have 4-8 bordered elements and rely on surfaces. The board still has 56, mostly row rules plus outlined chips. |
| Surface hierarchy | Done. Grey canvas, white work surfaces, dark plate. Grey is overused, though: secondary, disabled and stat cells all share one value. |
| Calm amber, no hazard stripes | Done. The only hatching is the small "ส่งต่อ รอคนรับ" bar on the people timeline, and it has a meaning. |
| Thai breaks only between words | Done in the live HTML (span.w nowrap; 0 broken words measured at 360/390/1920). The 390 contact sheet is stale and shows "ขันสก/รู". |
| One primary per row | Done (ยืนยัน + quiet "··· อื่น ๆ"). |
| Coherent icon set | Partly done. Monoline UI icons are consistent. The ⧗ ■ ◇ ○ text glyphs and full-colour ISO 7010 signs are separate languages. |

## Compared with the benchmarks
- **Siemens WinCC Unified / FactoryTalk Optix:** V is cleaner and more humane, with far better type. The andon plate is as legible as their line overviews.
- **MaintainX / UpKeep:** V's mobile flow is calmer and more opinionated, with better Thai. MaintainX's list and grouped-cell components are more polished.
- **Linear / Stripe:** V falls short on spacing rhythm, table refinement (lighter rules, aligned baselines) and chip discipline. The board is where the gap shows.

## Top 10 visual fixes
1. **Board 1920, bottom zone** (ระบบกันไว้ / คุณพักไว้ / หมดเวลา / เครื่องที่ล็อก): four cards of uneven heights leave dead canvas below. Make one row of equal-height panels aligned to the table's bottom edge, or a single tabbed "อื่น ๆ ในกะ" strip.
2. **Board 1920, ระบบกันไว้ card:** the "○ ต่ำ" word sits above the title baseline. Put the priority on its own line, as in the main table.
3. **Board 1280/1920, decision column:** six stacked 48 px black "ยืนยัน" slabs pull the eye more than the critical row does. Use 40 px height, top-align to line 1 of the row, and give the critical row the only extra emphasis (a red left rule).
4. **Board 1280/1920, PM row (MC-001):** the ETA "ครบกำหนด 13 พ.ย. · เลยมา 2 วัน" wraps, so the row is taller than the others. Shorten it to "เลย 2 วัน" or widen ETA by about 40 px so every row is exactly 2 lines.
5. **Board 1920, "เสร็จในกะนี้":** the result tags mix a grey-filled "แก้แล้ว" with black-outlined "ไม่พบอาการ"/"ซ่อมชั่วคราว", and the Thai upper vowels nearly touch the box. Use one chip style (tinted fill, no border, 4 px vertical padding) system-wide. That also covers "รอเริ่ม" (a pill on tech-job) and "อำนาจ กำลังทำเครื่องนี้อยู่".
6. **Board 1920, station strip:** card baselines drift. The station 2/3 outlined headers and the 2-line station 4 header "เกินเกณฑ์ · เครื่องหยุด" push the names down, and the ⧗ "คอขวด" glyph is a font character. Fix the header at one line high and draw a bottleneck icon from the set.
7. **Board 1280/1024, technician strip:** 10 boxed cards each have a grey bar of unclear meaning, which is the most generic-looking element in V. Replace them with one divided strip (no boxes) and a labelled bar, or reuse the 1920 timeline in compact form.
8. **Board 1024:** column headers wrap to 2 lines, the first row title wraps to 2 and its reason to 3, and the dark plate grows to about 220 px with the KPIs stacked. Either declare 1024 unsupported, or drop the "เสนอมา" and skill columns and inline the KPIs into the plate's right side.
9. **Phone 360/390, tech-step-hot:** stat cells, the disabled "ถัดไปได้เมื่อ 11:12" button and the nav rows are all the same grey, so the disabled button reads as a secondary action. Show the countdown as one large numeral on white, give the disabled button a lock icon and reduced text contrast, and group the nav rows as one inset list with dividers rather than 3 separate cards (on all tech-step pages).
10. **Icons and finish (all phone steps):** the ISO signs (32 px, full colour) crowd the step header on tech-step (two signs). Give them a fixed 40 px left column, and check that ISO yellow and prediction amber cannot be confused. Add the missing space in "ปิดเบรกเกอร์ CP-3แล้ว" (tech-step 390, check 1). Re-render the contact sheets, because sheet-390full-a is stale.

Also: raise board body text to 17-18 px at 1920 or above (a wall screen is read from 2-3 m), and remove the stray 16 px size.

## Best and worst idea
- **Best idea (keep):** the dark andon plate. The station tile, Thai name first and the 8-lamp line position are on every screen, with amber meaning forecast or now and nothing else. It gives V an identity and a meaning at once.
- **Worst:** the board's mix of chip and tag styles together with boxed technician cards. That is where V slips toward a generic dashboard.

## Rationale check (read after scoring)
The claims match what I saw: lamp equals station state, priority by shape plus word, one primary per row. The rationale over-claims a "coherent icon" story, since glyph characters are still used.

## Verdict
**Yes after fixes.** The phone flow is already at the 4/5 level. The board needs a layout and detail pass (fixes 1-8) to match the phone. Nothing structural needs redoing.

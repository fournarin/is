# Aesthetics review - Round 0 (role 6)

Basis: every png/ render of A, B and C, looked at by eye and zoomed in; a Playwright pass on board/tech-step/report/tech-job (1280, 1920, 360) measuring truncation, clipped text and page height; the CSS checked for type sizes, radii, line-heights and spacing. No rationale.md exists yet. I formed this view without reading anyone else's notes.

## Scores (1-5; 3 = pass with fixes, 4 = pass)

| Criterion | A | B | C |
|---|---|---|---|
| First impression (3 s) | 3 | 3 | **4** |
| Typography (Thai, scale, figures) | 3 | 2 | **4** |
| Layout / grid / rhythm | 2 | **4** | 3 |
| Colour | **4** | 3 | 3 |
| Detail / finish | 3 | 2 | 3 |
| Desirability | 3 | 3 | **4** |
| **Red line** | none | **HIT** (see B-1) | none |

**Ranking: C > A > B.** As it stands, B fails for me because of the red line. If B-1 is fixed, B moves up to second, because its 1920 board grid is the best of the three.

None of the three looks AI-made: no gradients, no emoji, no soft cards. But all three share one weakness that holds them below Linear or Stripe. They explain things in grey prose instead of showing them. Every row, panel and legend carries a grey sentence (for example "เรียงจาก... · ตัวเลขขวา = ... · แถบ = ..."). Each type scale also has 12 to 15 font sizes (A: 14-30 px including 17/19/21/23; C even uses 14.5 px). Linear uses about 4. Until the scales are cut and the explanatory sentences become encodings, none of them reads as premium. Compared with the newest HMIs (WinCC Unified, FactoryTalk Optix), A and C sit closest to ISA-101 "grey until abnormal", which is right for a wall screen. Compared with MaintainX/UpKeep, only C's phone screens feel as easy to pick up.

**Highest ceiling of beauty and use: C.** Build on C. Steal B's 1920 composition and A's colour discipline and priority shapes.

---

## A - "Carbon-style control sheet"

**Best idea:** priority coded by shape as well as colour (■ วิกฤต, ◇ ปานกลาง, ○ ต่ำ) on the board, plus the three sensor tiles on tech-job (78 °C / 85 °C / 1.4 °C). The tiles are real data presented as a quiet instrument readout.
**Worst idea:** a grey admin canvas (#E9EAEB) with white boxes on it. At 1920 it looks like IBM Carbon defaults, and the layout leaves dead grey space.

Top fixes:
1. **board 1920**: the left column ends at y≈900 and leaves an empty grey field, while the right column ("เสร็จแล้ว") runs off the bottom (page height 1221). Rebalance the columns so the board fits 1080 with no scrolling. A wall screen must never scroll.
2. **board 1920/1280, line strip**: the station boxes are 28 px, squeezed into a quarter-width card with buffer numbers in between. The production line is the hero, yet it looks like a footnote. Give it the full width and real height, as C does.
3. **tech-step 390x844**: about 200 px of empty grey slab between the "ทุกขั้น / ปิดงาน" buttons and the footer. It looks unfinished. Pin the secondary actions above the CTA, or let the white content fill the space.
4. **tech-step 360x640**: the provenance line "โดย ปราณี (วิศวกร)" sits half-hidden under the fixed footer at first view. Add bottom padding equal to the footer height.
5. **tech-close 390**: the outcome options (แก้แล้ว/ซ่อมชั่วคราว/...) use **checkboxes for a single choice**. Use radio marks, or fill the whole selected tile with no mark at all.
6. **board, top bar**: grey #8A8F95-ish text on #17191C ("กะเช้า 15 พ.ย.", "อัปเดต") is too faint at wall distance. Raise it to at least the second ink level.
7. **board rows 1920**: machine names are truncated ("เชื่อมเสริมความ...") even with 1920 px available. Give the machine column more width, or stack station under machine.
8. **Type scale (all files)**: 13 sizes. Collapse them to 5: 14 / 16 / 18 / 22 / 30.
9. **Board, crew strip**: ten equal mini-cards with 4 px bars. The bars are too thin to read and the cards are crowded. Make it one table row per person with a 10-12 px bar, or merge it into the right-hand "กำลังทำ" panel. Today the same people appear twice.
10. **Looped Thai (Plex Thai Looped)**: reads well, but next to Plex Mono it looks like a government form. Keep looped type for long body text on the phone if the technician interview demands it. Use loopless type for headings and the board.

## B - "Printed shift sheet (ใบคุมงาน)"

**Best idea:** the **1920 board composition**. A full-bleed ruled grid, a summary band across the top, the queue on the left, the crew table with 8-slot hour bars on the right, and three equal columns at the bottom (กันไว้ / พักไว้ / เสร็จแล้ว). It is the only board that actually uses 1920 px.
**Worst idea:** a ruled box around everything on the phone, plus a lavender (#ECEEF7) selected fill with a thick indigo border. Together they look like a GOV.UK or Bootstrap form, not a premium tool.

Top fixes:
1. **RED LINE - tech-close-sign 390x844, "ยังไม่ได้ทำ" step 6**: "10 N·m" breaks out of the hanging indent and **overlaps "แล้ว"** (the glyphs collide). Fix the hanging-indent CSS (use a grid for number + text, not a negative text-indent) and re-check every numbered list.
2. **Font pairing**: Noto Sans Thai Looped (with Noto Latin) next to Plex Mono. Two different design systems collide on every line that mixes a code with Thai. Move to the Plex family.
3. **board 1920, crew header**: "ช่างในกะ 10 / คน" wraps and leaves the unit orphaned, and the note "ช่องละ 1 / ชม." wraps too. Shorten the note and keep number and unit together.
4. **board, action column**: every row has "ให้คนอื่น ⌄" and "พักไว้ ⌄" with chevrons. That makes 12 chevrons of noise. Show the chevron only on hover or focus, or use a single "⋯".
5. **board**: the indigo #26307F accent has no relation to the status colours (red/orange). Either make indigo the single "action" colour everywhere, or drop it for black.
6. **report 390, "เครื่องหยุดอยู่ไหม"**: checkboxes for a yes/no single choice. Use a segmented control.
7. **tech-step 360**: the left step rail (52 px numeral plus a 6-box column) takes about 60 px of width and pushes the Thai heading to 4 lines. Put the rail above the heading below 400 px.
8. **tech-job 390**: the title wraps "เกิน / กำหนด" with a lone word. Use text-wrap: balance plus no-break spans for compound words.
9. **Synthetic-data banner**: the diagonal hatch in the corner is decoration. If it stays, it should be the one consistent "synthetic" mark on every surface, including the board header.
10. **Priority glyph** "||||" (4 bars) reads as signal strength or battery. Use A's shapes, or a numbered rank.

## C - "Line-first signage"

**Best idea:** the **station tile** (a black block with "สถานี / 3") on the phone and the board, together with the full-width line schematic as the board's hero. It looks like plant signage, carries a strong identity, and gives the phone screens a clear first read.
**Worst idea:** **orange hazard-tape stripes** for "คาดว่าจะเกิน" on the board. They are the loudest thing on screen for something that has not happened yet. On a shop floor, hazard tape means present danger, so the stripes lie and add visual noise.

Top fixes:
1. **board 1920/1280, stations 2-3**: replace the hazard stripes with an orange outline or a 4 px orange top rule plus the word "คาดว่าจะเกิน". Keep solid fill only for "สายหยุด".
2. **board 1920, station cards**: about 60 % of each card is empty white (stations 1 and 5-8). Cut their height by roughly 40 %, or put the useful data in them (the oldest WO, minutes).
3. **board 1920**: the page is 1118 px tall and the crew panel runs past the fold. Tighten the crew rows (they are 3 lines each) so the board fits 1080.
4. **Buffer tally marks** "||||||||" under the line: dense hairlines that visibly clump and cannot be counted at a glance. Use one short bar scaled to the count, or just the bold number.
5. **Crew timeline (right panel)**: the bars are about 8 px tall and thinner than the "now" rule. Raise them to 12-14 px and align the 07:00-15:00 tick labels exactly to the track segments.
6. **Thai compound breaks**: "ช่างไฟ / ฟ้า" (crew, 1920), "สายประกอบตัว / ถัง A" (report 390), "ติดตั้ง / หลังคา" (tech-step header 360), "เกิน / กำหนด" (tech-job 390). Wrap compound terms in `white-space:nowrap` spans and use `text-wrap:balance` on titles.
7. **tech-step 390, stepper**: future steps are dashed boxes, and the waiting-reason options on tech-close are dashed too. Dashes read as "placeholder / unfinished". Use solid light-grey outlines for future and disabled states.
8. **Two oranges** (#F9A900 and #E8890C) plus red. Pick one amber.
9. **Numbered section badges** (black 1/2/3 squares) on the board: they compete with the station-number tiles, which use the same black square. Keep black squares for stations only, and set section titles in plain bold.
10. **Type scale**: 15 sizes, including 14.5 px, and line-height 1 on Thai in 13 rules. Collapse to 5 sizes and keep Thai at a line-height of 1.3 or more except in the single-line tiles.

---

## The five fixes that matter most overall

1. **Fit the board in 1920x1080 with no scrolling and use the whole width.** Use B's grid with C's line schematic as the hero.
2. **Cut every type scale to about 5 sizes, and replace explanatory grey sentences with encodings** (a bar, a shape, a bold number). This is the gap between these concepts and Linear or Stripe.
3. **Treat Thai typography as craft**: one family (Plex Sans Thai; looped only for long phone body text if needed), no-break spans for compound words, balanced title wraps, no overlaps (B-1).
4. **Colour only for state, and honest**: no hazard tape for a forecast, one amber, one red, and either no accent colour or a single action colour.
5. **Correct control vocabulary and finish**: radios or segmented controls for single choice, solid rather than dashed borders for future and disabled states, no dead grey zones on phone screens, no repeated chevrons.

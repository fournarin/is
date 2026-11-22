# R3 aesthetics review - Phase 2 design system (role 6)

Method: existing PNGs (phone contact sheet; full-size eng-review 1280/1920, line-overview 390/1920, board-15 1920, eng-health 1280, sign-in 1280, unreachable-wifi 390, tech-noplaybook 390, tech-print A4, components 1280 with crops). Then a Playwright pass (google-chrome) over all 33 screens at 390 and 1920 to collect computed font sizes, weights, radii and non-Lucide glyphs, plus checks on the eng-review input and footer. I read README "Decisions" only after scoring.

## Scores (1-5)

| Criterion | Score | Evidence |
|---|---|---|
| First impression | 3 | The technician phone screens still look crafted: calm canvas, one black action, the dark station plate. The new desk screens look like admin CRUD: eng-health 1280 is a zero-filled table over 60 % empty canvas, and sign-in 1280 is an unstyled default form that hugs the top. MaintainX and Linear look better on both. |
| Typography | 3 | Phone screens are disciplined (18/24/36, 400/600). The whole system is not. Measured sizes: 15, 17, 18, 20 (board 390), 24, 30, 36, plus weight 900 (eng-gaps numerals) and stray 700 (eng-review, tech-step, components). tokens.css defines only t1-t4. 15 px decision text on a 1920 wall board is too small. |
| Layout | 3 | line-overview 1920: the floor plan uses about 1100 of 1920 px, leaves the right side empty, has an empty band above the blocks, and only redraws the station strip as 8 boxes (no space, aisles or footprints). eng-* 390: the six tabs wrap onto two rows. eng-review 1920: the approve bar sits below the fold because the page is 1166 px tall and the bar is not sticky. |
| Colour | 3 | Amber has lost its meaning. It now marks: over threshold (correct), the forecast outline (correct), the "ทดสอบความจุ 15 ใบ" test-data chip (board-15), a stale-data strip (components), reassurance ("งานของคุณไม่หาย", unreachable-wifi) and the mismatch highlight in the manual (eng-review). R1 praised amber as signal. Phase 2 spends it on noise. |
| Detail / icons | 3 | The Lucide set is adopted, sized and gridded well (components icon table), and ISO signs appear only as signs. Problems: Unicode glyphs remain (↑↓ eng-review, → eng-audit/line-overview/report-manual/tech-states, ▾ board sort). Swatch cards on components 1280 wrap one Thai word per line. The fade on board-15 1920 paints a white block on the tinted handover row (x≈890, y≈300). The wifi-off icon in the components status strip sits on its own line above the text. Radii are 3, 4 and 8. |
| Coherence | 3 | One chip language holds on phone screens, but it splits on the desk. eng-review adds grey highlight pills on every number in both columns. board-15 adds inline name pills and an amber chip. Print uses outlined boxes for hazard tags (fine, because it is paper). Coloured left-stripe callouts (amber, red, black, green) appear on 6+ screens. This is the one trope that reads as "AI dashboard". |
| Desirability | Tech 4 · Board 3 · Line 3 · Eng 2.5 | A technician would still open this. An engineer would tolerate eng-review: the side-by-side manual evidence is a strong idea, but it looks like a diff viewer. No plant manager would put line-overview on the wall as it is now. |

Benchmarks: the phone pages are at MaintainX level or better: calmer, Thai-first, with clearer provenance. The desk/eng pages are below Linear and Stripe in density craft, hierarchy and empty states. line-overview is below WinCC Unified and FactoryTalk Optix, whose newest line views draw real geometry and state with far less text. The print sheet is good, better than most CMMS PDFs.

## Red lines

- **HIT: Thai text clipped.** eng-review 1280, step 6 edit field. It is a single-line `<input>` with scrollWidth 681 and clientWidth 530, so "…แล้วขันสกรู่" is cut mid-glyph. Fixable, but under the rules it fails until fixed.
- Close calls, not hit: (a) the coloured left-stripe callouts drift toward template; (b) eng-review number pills on every value make visual noise that slows reading.
- Not AI-made overall. The phone system is clearly authored.

## Top 10 fixes

1. **eng-review 1280/1920, step 6 editor.** Use an auto-growing textarea at the same size as the Thai line. Drop the duplicate Thai line above it, because the step text currently appears twice.
2. **Amber discipline, all viewports.** board-15 "ทดสอบความจุ" chip → ink/sunk chip. unreachable-wifi/server "งานของคุณไม่หาย" → neutral surface with a Lucide check. Components stale strip → sunk + ink-2. eng-review mismatch highlight → stop-red underline, because it is an error, not a forecast.
3. **One callout form.** eng-health, eng-review mismatch, tech-noplaybook, unreachable-*, and the components status strips should use one style: a white surface, a leading 20 px Lucide icon, a semantic word in bold, and no coloured left stripe.
4. **line-overview 1920, floor plan.** Draw a real plan: conveyor line, station footprints, aisles, and the maintenance room and stores at their positions. Use the full width, or place it in the right 40 % beside a machine list. Remove the empty top band. As it is, it repeats the strip.
5. **line-overview 1920/390, station strip.** Card bodies run up to 8 lines of ink-2 text. Clamp each to MC id + one status chip. Move the "20 คัน 20 นาที" buffer from the stacked 40 px gutter onto one line on a connector beneath the strip.
6. **board-15 1920.** Fade truncation onto the row's own background (this fixes the white block). Make the 15 grey "ยืนยัน" buttons quieter and keep only the focused row solid. Raise the dense decision line from 15 to 17 px minimum.
7. **Type scale, system-wide.** Collapse to 15/18/24/36, with 30 kept only for the clock. Remove 17 and 20, weight 900 (eng-gaps) and 700. Fix the components swatch cards, which wrap one word per line because the description needs `display:block`/normal wrapping on the `span.w` wrapper.
8. **Icons.** Replace ↑↓ → ▾ with Lucide arrow-up/down/right and chevron-down. Put the wifi-off icon inline with the title on unreachable-wifi 390 and the components status strip. Unify radius to 4 (chips) and 8 (surfaces).
9. **sign-in 1280/390.** Centre the form optically (about 40 % from the top) and give it a real wordmark lockup (plant + line, Plex 600). Set the session note as quiet 15 px text, not a card. Right now it is the least designed screen in the set.
10. **eng-* 390 and eng-review 1920.** Turn the two-row tab wrap into a horizontally scrolling tab bar with a fade. Make the eng-review footer (approve / changes) sticky at 1920. Remove the grey pills on unchanged numbers and highlight only the values being compared.

## README decisions I would challenge

- **#3 Dense mode 15 px at ≥1600:** challenge. The wall board is read from 2-3 m. Keep 17-18 px and gain rows by removing the second meta line instead.
- **#6 Floor plan as a pannable box:** fine on phones. The issue is what is drawn, not how it pans (fix 4).
- **#2 One-line fade:** accept, but only with fix 6. Today it shows as a rendering bug on tinted rows.
- #1, #4, #5, #7: agree.

## Verdict for GATE 2

**Pass after fixes.** The phone system is coherent and good. Fixes 1-3 and 7 are required before the gate, because they cover the red line and the system-wide coherence. Fixes 4-5 are needed before line-overview is shown on a wall. Fixes 6 and 8-10 can be done in Phase 3 polish.

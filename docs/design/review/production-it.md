# Review, role 4: production + plant IT (Round 0, snapshot 16:41)

Reviewer lens: Khun Manop (line lead, speaking for operators) and Khun Kitti (IT/OT). Focus: operator report flow, PDPA, devices, performance, offline, accessibility.
Sources: interviews/production-it.md, REQUIREMENTS.md sections 3.6, 3.8 and 4.7 (plus G-03/04/06/07/09/10/11 and T-11 where they touch my screens).

## How I checked (measured, not taken from the designers)
- I read every report*.png at 360x640, 390x844 and full page, plus the boards at 1280 and the tech screens.
- I loaded every page with Playwright (google-chrome, --no-sandbox, file://) at 390x844, 360x640, 640x400 (a 1280x800 PC at 200% zoom) and 1280x800. For each page I logged every request, console errors, horizontal overflow, the submit button's bounding box, fixed/sticky elements, all tap targets under 56px, font sizes under 18px, and the contrast of every text node against its nearest opaque background.
- I grepped all HTML for CSS that Chrome 100 or 109 can't handle, for technician names on operator screens, and for offline/freshness wording.
- Results that hold for all three: 0 external requests, 0 console errors, `lang="th"`, no horizontal scroll, no emoji, no fixed element over content. On the report screens no text is below 7:1. The fixture's 10 technician names never appear on any report*.html.

## Red lines
| Red line (interview) | A | B | C |
|---|---|---|---|
| P1: more than 3 taps or forced typing (REQ-P-01: ≤3 from the QR/machine link, ≤5 by hand) | **HIT.** Urgency is tagged "ต้องตอบ", so the QR path takes 4 taps (stopped, urgency, symptom, send) | **HIT as drawn.** The QR screen (report.html) shows urgency as numbered step 3 and doesn't say it's optional, so 4 taps | **HIT as drawn.** Same: urgency is step 3 and not optional |
| P (rejected outright): submit needs scrolling at 390x844 | ok (sticky footer, y=766-830) | ok (y=743-807, normal flow) | **HIT.** Submit is at y=899-963, below the fold |
| P2: a report fails silently / no "ยังไม่ถึงระบบ" | not drawn | not drawn | not drawn |
| P3: screen says something untrue (tech name before confirm, wrong status) | ok. MC-012 shows "ช่างกำลังซ่อม", which matches fixture `in_progress` | ok. MC-024 (held) shows "รับเรื่องแล้ว" | ok. MC-025 (proposed to สุนทร) shows "รับเรื่องแล้ว" with no name |
| P4 / I: synthetic banner; 0 external requests | ok | ok | ok |
| I4: Chrome 109 PC | ok on 109 (see the Android 100 issue below) | ok | ok |

**Result: as drawn, all three fail for this reviewer.** Each failure is a one-line design fix (see the top fixes). "Not drawn" is not counted as a hit in Round 0, but it will be one at the gate if the screens are still missing.

Why the urgency hit is real: the approved flow in REQ-P-01 and section 4.7 is machine, "เครื่องหยุดอยู่ไหม", symptom, send. Urgency is not one of the counted taps. REQ-P-04 only says urgency must not be merged with "stopped". It does not say urgency must be mandatory.

## Scores (1-5; 3 = pass with fixes, 4 = pass)
| Criterion | A | B | C |
|---|---|---|---|
| Report flow (taps, typing, fold, duplicate warning) | 3 | 4 | 2 |
| Status of my reports (4 stages, readable in 5 s, honest) | 3 | 3 | 4 |
| PDPA (names per role) | 3 | 4 | 4 |
| Devices (Chrome 109 / Android 100, shared kiosk, logout) | 2 | 4 | 3 |
| Performance (payload, fonts) | 3 | 4 | 3 |
| Offline and freshness (I-04, T-11 for reports) | 2 | 2 | 2 |
| Accessibility (contrast, keyboard, targets, zoom, no-JS) | 4 | 4 | 3 |

### Evidence for every score below 4
**A**
- Report flow 3 (report.html, 390x844): all 8 stations and 12 machine chips are drawn inline every time. That pushes "เครื่องหยุดอยู่ไหม" and the open-report warning ("MC-012 มีเรื่องเปิดอยู่…") below the fold, so the operator never sees the warning at the moment of choosing (REQ-P-07). Fix: collapse the list to the chosen machine with a "เปลี่ยน" button (as in B), and put the warning directly under the chosen chip.
- Status 3 ("เรื่องที่คุณแจ้ง" card): the 4-stage track uses empty and filled squares that look like the form checkboxes just above, and there is no time per stage. Fix: use a non-input shape with stage times, like C's horizontal track.
- PDPA 3 (board.html, 1280x800): the "ช่างในกะ 10 คน" strip shows every technician's name, free minutes and state at the top of the board. Production Q5 asks for this board to go on the line-head wall screen. Fix: a read-only/wall mode that drops this strip, or shows skills without names.
- Devices 2 (all phone files, `.shell{height:100vh;height:100dvh}` with an inner scrolling main): `dvh` needs Chrome 108. On Android 9 with Chrome 100-107 it falls back to `100vh`, which is the height with the URL bar hidden. Because the document itself never scrolls, the URL bar never hides, and the bottom of the footer (the submit / "เริ่มงาน" button) stays clipped. Report has no "ออก" either. Fix: normal document flow plus `position:sticky; bottom:0` for the action bar, and a visible "ออก" on the report screen.
- Performance 3: report loads Plex Looped ×3 plus Plex Mono ×2, about 227 KB of woff2. Board adds Mono Regular, about 277 KB. That leaves almost nothing of the 300 KB budget (REQ-I-03) for the Next.js runtime.
- Offline 2: an "อัปเดต 10:42:00" stamp is present, but there is no sent, queued or failed state for a report.

**B**
- Status 3 (report.html, "เรื่องที่ฉันแจ้ง"): the stages are drawn as radio circles inside a bordered list, so they read as tappable inputs, and only "ตอนนี้" is given without stage times. Fix: same as A.
- Offline 2: the "อัปเดต" stamp is there (good), but no report failed/queued state, and no Wi-Fi vs API wording.

**C**
- Report flow 2 (report.html, 390x844): the submit button "ส่งแจ้งซ่อม MC-025" is at y=899, below the fold. This is the exact thing Manop rejects in op_report.phone.png. The "พิมพ์เพิ่ม" link is 48px tall, under the 56px R-P4 minimum. Fix: tighten the station header (the 1-8 position strip plus the "เปลี่ยนสถานี" block take about 130px) or make the action bar sticky in normal flow, and make "พิมพ์เพิ่ม" 56px tall.
- Devices 3: there is no "ออก" on the report screen even though it is a station-shared device. The choices are `<button role="radio">`, which do nothing without JS (Kitti Q4 asks whether report works without JS). Fix: native radio/checkbox inputs inside a `<form>`, as B does.
- Performance 3: Plex Thai ×3 plus Mono ×2, about 218 KB.
- Offline 2: the report has a clock but no "อัปเดต hh:mm:ss", although "my reports" is live data (REQ-I-04 M). No failed/queued state. (tech-close's "เก็บในเครื่องนี้ทันทีที่พิมพ์" is the right idea and should carry over to report.)
- Accessibility 3: the JS-dependent ARIA radios noted above, and the 48px target.

## Cross-cutting observations
- **Default answers.** All demo states arrive pre-filled (A/B use `checked`, C uses `aria-checked`). In the build, "เครื่องหยุดอยู่ไหม" must start empty. A default of "ยังเดินอยู่" would under-report stoppages, which makes it a data-honesty issue. Please also draw the empty initial state.
- **Who is "มาลี"?** All three show a signed-in operator name. Kitti says no operator will type a password with gloves on, and asks for a station kiosk account plus an employee code. C's "คุณอยู่ที่สถานีนี้" already assumes a station-bound device, but none of the concepts shows how the reporter is identified. Decide the model (kiosk account per station, reporter as a tapped or scanned employee code) and show it.
- **Fonts.** Every concept ships 2-3 weights of IBM Plex Mono (about 50 KB each) only for MC-/WO- codes and times. B splits Noto Thai/Latin with `unicode-range` (about 11 KB per file), which is the right pattern. One Mono weight subset to `0-9 A-Z - : ·` comes to about 5-10 KB.
- **Maintenance extension (REQ-P-08, S).** Not on any report screen. C's "ใช้ andon หรือวิทยุ" line is good and should get the configurable extension number next to it.
- Checked and fine: there are no `color-mix`, nesting, subgrid, popover or `@container` rules. A's board `:has()` works on Chrome 109 but not on Android tablets with Chrome 100 (popover z-index only). Contrast is ≥7:1 on all report text, and the smallest text is 14px, on labels only (G-06 allows that).

## Best and worst idea per concept
- **A.** Best: a sticky submit that names the machine ("ส่งแจ้งซ่อม MC-012"), so the operator always sees what will be sent. Worst: the whole station/machine grid inline on every report, plus a 100vh shell that clips the action bar on Android 9.
- **B.** Best: a QR-preselected machine with a single "เปลี่ยน", built as a native `<form>` that works without JS, with "ออก มาลี" visible on the shared device and "ล็อกเองเมื่อไม่ใช้ 15 นาที" stated on the board. Worst: status stages drawn as radio buttons with no times.
- **C.** Best: a station-bound report. The device knows its station, the operator picks between the 2 machines there, and the open-report badge sits on the chip ("MC-025 มีเรื่องเปิดอยู่ 1"). It also has the horizontal status track with stage times. Worst: the submit button below the fold at 390x844.

## Ranking and verdict
**B > C > A.** B is the safest base for IT and for the operator: native form, no fragile CSS, smallest payload, submit above the fold, visible logout. C has the best ideas for the operator (station-bound kiosk, chip-level duplicate warning, status track with times) but breaks the fold rule and needs JS. A's action-bar approach works on desktop and new Chrome but has the Android clipping bug and the longest form. B is good enough to build on if it takes C's three ideas. Nothing needs to be redone from scratch.

## Top 5 fixes (in priority order, for all concepts unless named)
1. **Make urgency optional.** No default; the backend derives it from "stopped" (yes = high, no = medium) when blank, as NEW_`urgency_source: derived|operator`. That gives 3 taps from QR (stopped, symptom, send) and ≤5 by hand. Remove A's "ต้องตอบ" from urgency. Draw the empty initial state with nothing pre-selected.
2. **Draw the send outcomes on report.**
   - Sent: WO number, server time, "รับเรื่องแล้ว".
   - Not sent: "ยังไม่ถึงระบบ · เก็บในเครื่อง (1) · ส่งเองเมื่อเชื่อมต่อได้", with Wi-Fi-down vs system-not-responding wording, the configurable maintenance extension, and form text kept (REQ-I-04, T-11, P-08).
   - State what happens to a queued report at "ออก" on a kiosk (REQ-I-06).
3. **Keep submit visible at 390x844 on Chrome 100 Android.** C: move submit above the fold. A: drop the `100vh/100dvh` shell for normal flow plus `position:sticky` (B's flow is the reference).
4. **Shared-device identity and PDPA.** Show "ออก" on the A and C report screens. Show the kiosk/employee-code model. Add "อัปเดต hh:mm:ss" to C's report. Hide per-technician minutes and names (A's "ช่างในกะ" strip) in a read-only wall mode of the board.
5. **Font budget.** One Mono weight subset to code characters (or tabular figures from the Thai face), at most 3 Thai weights split by `unicode-range` like B. Target ≤120 KB of fonts so the page plus Next.js runtime stays ≤300 KB gzip under Fast 3G (REQ-I-03). Use native inputs in a `<form>` (C) so report works with JS off.

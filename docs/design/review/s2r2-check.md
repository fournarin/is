# S2 round 2 check - screen items S1-S7, P1 (889d040)

Method: Playwright on all 14 SSR snapshots (set2 x7, set1 x7) at 360x640, 390x844 and 1280x800 (42 renders, sheets opened), plus PNGs for tech-close-confirm and tech-step-offline, which have no snapshot. Backend not reviewed.

## Regression sweep (42 renders): PASS
Text min 18 px, sizes 18/24/36, contrast min 7.42 (set1) / 7.90 (set2), taps min 56 px, 0 gaps under 8 px, 0 tap or text overlaps, 0 h-scroll, 0 split Thai words, 0 external requests, 0 emoji, 0 JS errors. Banner "ข้อมูลจำลอง · ไม่ใช่สัญญาณจริง" on all pages. measure.json: close-confirm has a sticky submit with 0 overlaps.

| # | Item | Verdict | Evidence | Fix |
|---|---|---|---|---|
| S1a | Signal word by hazard | PASS | Isolation, DC-bus wait, verify and restore all show "อันตราย"; "ข้อควรระวัง" appears nowhere (electrical hazards only) | - |
| S1b | Hot step uses W017 | **PARTIAL (declared)** | No W017 in any snapshot: the world's wait is the DC-bus discharge, so it carries W012. ROUNDS says the manual has no hot-surface step. The spec's hot-surface variant is still unverified. | Add a seeded hot-surface step, or mark the variant "untested" |
| S1c | Signs >= 48 px tall | PASS | Triangle signs 55x48, round M021 48x48; restore shows W012 55x48 + "อันตราย" | - |
| S2 | Wait wording | PARTIAL | Running: "เหลือ N นาที · ระหว่างรอ ห้ามแตะฝาครอบ" (no longer says safe to touch). The finished state "ครบเวลารอแล้ว · ตรวจก่อนแตะ" appears in no snapshot (0 hits), so I could not verify it. The wording is "ตรวจก่อนแตะ", not "ตรวจอุณหภูมิก่อนแตะ"; for a DC-bus wait that is arguably right (the check is voltage). | Capture the finished state |
| S3a | Lock strip content | PASS | "ล็อกอยู่ CP-3 · กุญแจ ก-03 ของคุณ (พิมพ์ชนก) · ใส่ 22:18 น. ขั้น 2" on hot, restore, close-locked and handover (isolation has none: no lock yet, correct) | - |
| S3b | Offline state on isolation step | **FAIL (defect found)** | `tech-step-offline` PNG: the "Wi-Fi หลุด" chip takes the clock's place and cuts the station name: "ติดตั้งห" at 360, "ติดตั้งหลังค" at 390 (no ellipsis; Thai word cut). measure.json reports no clip. Banner text kept; note "ยังไม่ได้บันทึก · ทำตามใบพิมพ์" is in the points section per ROUNDS (PNG not scrolled to it). | Truncate with an ellipsis or drop the station name while offline; make MEASURE catch it |
| S4 | tech-close-locked lock question | PASS | Lock question is #2, legend at y=574 at 360x640 (was #3, below). The heading is above 640 but its choices are mostly below. | - |
| S5 | tech-close-confirm | PASS | PNG: primary "กลับไปทำขั้น 4", secondary "ปิดงานเลย", offline/register note, "แก้คำตอบ"; submit sticky (measure.json) | - |
| S6 | tech-noplaybook above 640 | **PARTIAL** | Actions now start at y=601 (ส่งต่องาน 601-667, ปิดงาน 675-740) at 360x640: the first row is cut by the fold (bottom 667 > 640). No primary button; previously y=790. | Trim the callout ~30 px more |
| S7a | Banner kept while offline | PASS | Banner row unchanged; chip is in the top bar | - |
| S7b | "ซ่อมชั่วคราว" wording | PASS (declared) | "แก้ชั่วคราว" kept and declared in ROUNDS | - |
| P1a | Option tiles / legend inside the card | PARTIAL | Legends are inside the white fieldset cards (legend top = card top). Tiles are one style (white, 8 px radius, ring when chosen) except wait reasons: grey checkbox tiles; lock options also grey (disabled or sunk). | Use one tile for reasons too, or state why |
| P1b | Excerpt label on its own line | PASS | "ต้นฉบับ หน้า N · จำลอง" is its own paragraph above the text on all step pages | - |
| P1c | "5 นาที" unbroken | PASS | One line rect for "5 นาที" and "20 นาที" | - |
| P1d | Sticky primary: close-confirm and handover | PARTIAL | Close-confirm sticky (measured). Handover not sticky: declared, since a sticky bar over a short form overlaps text; its button is at y=1368. | Accept as declared, or sticky with padding |

## ROUNDS.md claims
"27/27 MEASURE pass" is consistent with my numbers on the 14 snapshots. "Step button 628 at 360 online and offline": 628 confirmed online (tech-step-normal); offline not verifiable without a snapshot, and the measure misses the clipped name.

## Verdict
CONDITIONAL PASS. Signal words, sign size, lock strip, locked-close order, confirm review and the polish items hold, and nothing regressed. Before the gate: fix the offline top bar (clipped station name), pull the noplaybook action fully above 640, and capture the W017 and "ครบเวลารอแล้ว" states.

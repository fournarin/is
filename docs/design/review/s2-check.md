# S2 check - Phase 3 set 2 (isolation, hot, verify, restore, close, handover) + set-1 carry-over

Method: Playwright on every SSR snapshot at 360x640, 390x844, 1280x800, sheets opened (set2: 7 pages, set1: 7 pages incl. new tech-job-two = 42 renders), plus PNG comparison with `system/png/`. No snapshot exists for tech-close-confirm, tech-offline and tech-states-*: those are judged from PNGs and measure.json only.

## Phone rules and tokens (all 42 renders)
Text min 18 px (sizes 18/24/36, weights 400/600), contrast min 7.42 (set1 job pages) / 7.90, taps min 56 px (the 13 px inputs are inside 56 px labels), 0 gaps under 8 px, 0 overlaps, 0 h-scroll, 0 split Thai words, 0 external requests, 0 emoji, 0 JS errors. PASS. Banner "ข้อมูลจำลอง · ไม่ใช่สัญญาณจริง" on every page.

| # | Item | Verdict | Evidence | Fix |
|---|---|---|---|---|
| C1 | Carry-over: "จำลอง" on excerpt and manual text | PASS | Excerpt "ต้นฉบับ หน้า 4 · จำลอง"; manual header "หน้า 4 · … · คู่มือจำลอง"; history "2 ครั้ง · จำลอง"; one form (text after a middle dot) | - |
| C2a | Offline strip vs fold | PASS, with a cost | Step button at y=608 at 360x640 online and offline (was 720). The strip replaces the banner row: "Wi-Fi หลุด · ที่ทำไว้ไม่หาย · จำลอง", so the full "ไม่ใช่สัญญาณจริง" wording is dropped while offline. | Keep "ไม่ใช่สัญญาณจริง" on the strip |
| C2b | tech-noplaybook primary above 640 | **FAIL** | Actions start at y=790 (ส่งต่องาน 790-856, ปิดงาน 864-929) at 360x640; the 24 px callout fills the screen. The page has no primary button. | Compact the callout or put one action under it |
| C3 | Manual line breaks | PASS | Title, numbered items 1-6, "Required tools:", "Estimated time:", "Required skill:" each on their own line; no merging | - |
| C5 | "ถัดไป" row tested | PASS (PNG-level) | tech-job-two exists (primary "รับงานและเริ่มทำ" ends 573); row visible within the page | - |
| S1 | Isolation step (tech-step) | PASS | M021 + W012, both 48 px, signal word "อันตราย" (red), points one by one with tick, lock picker ก-03 / ก-04 / free text, disabled "ทำขั้นนี้แล้ว ถัดไป" with "ยังต้องยืนยัน: ใส่กุญแจ". All actions are below the fold (907-1153 at 360x640); the spec was lower (about 1470). | Move the excerpt below the points |
| S2 | Hot / wait step | PARTIAL | Timer "5 นาทีเหลือก่อนแตะได้ · เริ่มรอ 21:16 · ครบ 21:21", "ถัดไปได้เมื่อ 21:21", sign 48 px, "ข้อควรระวัง". The sign is W012 (electrical, DC-bus wait), **not W017 hot surface**; the spec's hot-surface variant (W017 + "ห้ามแตะฝาครอบขณะร้อน") has no capture. | Capture a W017 step, or say it is untested |
| S3 | Verify step | PASS | One tile per test point (TP-1, TP-2), 48 px W012 + "อันตราย"; disabled next with the reason | - |
| S4 | Restore step | PASS | No ISO sign (as spec), "ขั้นคืนพลังงาน", owner-only "ปลดกุญแจ ก-03 ของฉันที่ CP-3", OSHA order line | - |
| S5 | Lock strip (owner/point/lock no./time) | PARTIAL | "ล็อก CP-3 · ก-03 ของคุณ · 21:16 น." One line, on all step/close/handover pages. The spec shows owner name, "ใส่", time and the step. Owner is only "ของคุณ", step is missing. Declared as shortened. | Add the step and a verb ("ใส่ 21:16") if width allows |
| S6 | tech-close / close-locked | PARTIAL | All four blocks present; lock reason chips and "ยังล็อกอยู่ · ขั้น 7 ..." text present. Copy drift: "ซ่อมชั่วคราว" became "แก้ชั่วคราว" (undeclared; only "ไม่พบปัญหา" is declared). Primary below the fold, like the spec. | Declare or revert the wording |
| S7 | tech-close-confirm | PARTIAL | PNG: summary (ผล, รอ, กุญแจ with register reason, โน้ต) and the list of undone steps. The spec's primary is "กลับไปทำขั้น 2" with "ปิดงานเลย ทั้งที่ยังไม่ครบ" secondary and an offline-queue note; built has "ยืนยันปิดงาน" primary and "แก้คำตอบ" and no "ปิดงานเลย", no offline note, while 4 steps (incl. restore) are undone. | Primary should lead back to the undone step when steps remain |
| S8 | tech-handover | PASS | Lock question (3 choices), gap-free order, note prefilled "ถึงขั้นที่ 4 จาก 7 ·", button "ส่งต่องานให้หัวหน้ากะ"; no transfer button, stated | - |
| S9 | Honesty | PASS | "(จำลอง)" on history, excerpt, manual; approval line "Edition 3, synthetic"; skipped "ตัวอย่าง ยังไม่อนุมัติ" lists are declared. Lock numbers and dates are world data under the banner. | - |
| R | ROUNDS.md claims | PARTIAL | "24/24 MEASURE pass" matches my numbers on the 7 snapshotted pages. primaryBottom null on step pages is by design (no primary); "step button 608" confirmed. Not verifiable without a snapshot: the REQ-H-05 stop bar (declared not captured), tech-close-confirm. | - |

## Verdict
CONDITIONAL PASS. Phone rules, tokens, ISO marks (48 px with Thai signal words), per-point confirmation and the carry-over honesty labels hold. Remaining before the gate: (1) tech-noplaybook actions below 640 at 360x640, (2) hot-surface W017 not shown, (3) close-confirm leads with "ยืนยันปิดงาน" instead of going back to undone steps, (4) lock strip omits owner name and step, (5) undeclared "แก้ชั่วคราว" copy change.

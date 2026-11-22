# R5 final GATE 2 re-check

Method: own Playwright run (Chrome, --no-sandbox). All 36 screens x 5 viewports (180 renders), plus touch emulation (`has_touch`, `is_mobile`, so `pointer: coarse` = true) for board-15 and for a 360/390 h-scroll sweep of every screen. README figures not used.

| # | Item | Verdict | Measured evidence | Fix |
|---|---|---|---|---|
| 1 | board-15 no h-scroll at 360/390 ([M]1, RED LINE) | **FAIL** | board-15 still scrolls sideways: scrollWidth 425 at 360 and 448 at 390 (desktop and touch emulation). Same culprit as before: `td.rs > span.chip` ("กิตติพงษ์ ส่งต่อ รอคนรับ เครื่องนี้อยู่…") ends at x=425/447. All other 34 pages: 0 px at 360 and 390 (tech-print and components excluded, print/desk gallery). | Let the chip wrap (`white-space: normal`) or truncate; board-15 only, `board.html` is fine |
| 2 | Page-image label + watermark ([M]2) | PASS | "ภาพหน้าคู่มือ (จำลอง)" on eng-review, -kind, -notfound; "ภาพหน้าจริง" gone (0 hits). Image files (p2, p4) carry a diagonal grey watermark "ตัวอย่าง · คู่มือจำลอง · SYNTHETIC" plus the header "Edition 3, synthetic". | - |
| 3 | hot_surface kind + editable isolation points ([M]3) | PASS | eng-review-kind picker: ปกติ / ตัดพลังงาน / พลังงานสะสม รอ / **พื้นผิวร้อน รอให้เย็น** / ตรวจว่าไม่มีพลังงาน / คืนพลังงาน. Isolation panel: "รหัสจุด" and "จุดอยู่ที่ไหน" text inputs (editable), energy buttons ไฟฟ้า / ลม / ไฮดรอลิก, ลบ, "+ เพิ่มจุดตัด", with "ป้าย W012 · คำสัญญาณ อันตราย". | - |
| 4 | Sticky approval gate ([M]4) | PASS | After a 700 px wheel scroll at 1280 the "อนุมัติฉบับที่ 4" bar sits at y=25-73 (was y=-268), on eng-review, -kind and -notfound; it was at y=191 before the scroll. Signing order is explicit: "ส่งให้ จป. ตรวจก่อน · คุณอนุมัติหลัง". | - |
| 5 | board-15 button gaps, `pointer: coarse` ([M]5) | PASS | With coarse pointer at 1280, 1366 and 1920: 0 pairs under 8 px (35 targets, min height 48). | - |
| 6 | Desk (`pointer: fine`) rule | PARTIAL | With a mouse the same 30 pairs are 5 px apart at 1280, 1366 and 1920 (up from 1-2 px). Acceptable under a pointer-fine exemption; the touch-gap rule is now keyed on pointer, not width, so 1280/1366 touch tablets are covered. A hybrid laptop with a touchscreen reports `fine` first, so it gets 5 px. | Raise to 8 px unless the 15-row fit at 1080 breaks |
| 7 | S-01 on proposals only | PASS | board-15 proposals fully above the fold (handover excluded): 9 at 1280x800 (need 8; was 10), 15 of 15 at 1920x1080. board-15 docH at 1920 = 1080 (was 1288), so it fits one screen. Real board at 1920: docH 1080. | - |
| 8 | S-10 at 1024 | PASS | In-progress line at y=165-190, above the queue; 5 of 6 proposals above the fold | - |
| 9 | Reproducibility | PASS | `data/` now holds eng-seed.json, r-2000ic-maintenance.pdf, fixture.json, seed1/. `_src/base.py` uses a relative path; `grep "/Users"` over `system/` finds 0 (text files), and `_src/__pycache__` is gone. Page renderer `pdfpage.swift` is macOS-only: Phase 3 item. | - |
| 10 | 360x640 folds | PASS | No sign-in / unreachable / eng page has its primary below 640 (checked all new families); tech-job "ถัดไป" row ends at 635.2 | - |
| 11 | Regression sweep (180 renders) | PASS | 0 h-scroll on any desk page; 0 tap or text overlaps; 0 split Thai words (Segmenter test); contrast min 7.05, 0 nodes < 7; phone text min 18 px, phone tap min 56; desk tap min 48, text min 15; 0 emoji, 0 external requests, 0 JS errors. Phone gap pairs under 8 px: 0. | - |

Counts: 11 items - PASS 9, PARTIAL 1 (#6), FAIL 1 (#1).

## Red lines
1. board-15 still scrolls sideways on a phone (425/448 px). This is [M]1, reported as a red line in round 4 and not fixed. It is a test page, not a shipped screen, but the brief and the coordinator both asked for it.

## Verdict
CONDITIONAL PASS for GATE 2. Four of five round-4 [M] items are fixed and measured, and nothing regressed. One CSS fix on the board-15 chip remains before it is a clean pass. Not tested: Chrome 109, keyboard-only, 200 % zoom, greyscale (Phase 3).

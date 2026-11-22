# S2 aesthetics - Phase 3 set 2 safety screens + set-1 carry-over (role 6)

Method: I put the build captures next to the spec PNGs at 390x844 (tech-step, hot, restore, close-locked, close-confirm, handover; verify and close have no direct spec twin). I rendered the SSR tech-close-locked page at 390 and measured its fieldsets, re-read the set-1 captures (21:15-21:17), and read measure.json after looking.

## Score: technician phone, safety screens = **4 / 5. PASS**

**Calm and unmistakable, both achieved.**
- *Unmistakable:* the ISO signs are 48 px and appear only where the engineer marked them: M021 + W012 on isolation, W012 on verify and the DC-bus wait. The signal words are red "อันตราย" and yellow "ข้อควรระวัง". A one-line black lock strip ("ล็อก CP-3 · ก-03 ของคุณ · 21:16 น.") sits on every job screen. Isolation points are confirmed one by one in numbered tiles. The hot wait shows "ถัดไปได้เมื่อ 21:21" as a disabled button with a lock icon.
- *Calm:* there are no stripes, no flashing and no red outside the signal word. The type stays at 18/24/36 with weights 400/600 (measured). The lock strip is tidier than the spec's two-line block. The page rhythm matches set 1, so the safety screens feel like the same app, only firmer.

No h-scroll, clipping or split words on any capture.

## Fidelity diffs (none block)

1. **tech-close / tech-close-locked, 390: three option styles on one form.** Outcome radios sit inside one white card with no tile per option, the minutes picker is bare segments on the canvas (only the selected one gets a tile), and the wait reasons are sunk tiles. The spec uses one tile style per choice. Unify on the handover's tile style.
2. **Same screens: section legend misaligned.** In the SSR, the fieldset is 16-374 px but the legend row is offset: "1 ผลการซ่อม" starts at 24 and "ต้องตอบ" / "ค่าเริ่มต้น 0" end at about 382, 8 px past the card edge. Fix: `legend{padding:0; width:100%}` and the same inset as the card.
3. **tech-close-locked, 390: lock question order.** The build puts "รอไปกี่นาที" at #2, which pushes "สถานะกุญแจ" to #3, below the fold. The spec has the lock state at #2 and visible with a red lock icon. When a lock is on, ask about it right after the outcome.
4. **Manual excerpt label, all step screens (set 1 and set 2): regression.** "ต้นฉบับ หน้า 4 · จำลอง Remove the belt…" now runs the grey label and the quote together on one line. Set-1 round 2 had the label on its own line. Restore that.
5. **tech-step-hot 390, wait timer.** "5" and "นาที" stack on two lines on the left, while the spec sets "30 นาที" inline at 36/18. Put them on one baseline.
6. **tech-close-confirm / tech-handover 390.** The primary button sits at 1139 / 1350 px. That is acceptable for a review page, but a sticky "ยืนยันปิดงาน" / "ส่งต่องาน" bar would match the step screens.
7. **Intentional differences accepted:** no "ตัวอย่าง ยังไม่อนุมัติ" checklists (more honest), and "ไม่พบปัญหา" wording. Restore has no ISO sign, as in the spec.

## Set-1 carry-over (set1-round2-summary items 4-5)

| Item | Result |
|---|---|
| Manual title spacing | **Done.** The title is bold on its own lines and the paragraphs are spaced; it reads as a page now. |
| Offline Wi-Fi icon | **Done.** About 20 px white wifi-off in a one-line strip ("Wi-Fi หลุด · ที่ทำไว้ไม่หาย · จำลอง"). |
| Symptom repeat on tech-job | **Done.** The line now starts at "ยังไม่เกินเกณฑ์…". |
| One "จำลอง" form | **Done.** It is plain text after the heading ("ครั้งก่อนที่เครื่องนี้ · จำลอง"). |
| Two-job capture / sticky back on manual | Not verified in these captures; not blocking. |

## Verdict

**PASS: technician phone, set 2, 4/5.** The safety screens get the balance right. Diffs 1-4 are quick CSS and order fixes that would lift it toward 4.5. Diff 3 matters most for a technician closing with a lock still on.

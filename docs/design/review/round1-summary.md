# Round 1 (concept V) - consolidated fixes (Cowork, 2026-11-15 22:05)

Reviewers (economy round, 2 fresh agents): r1-aesthetics.md (aesthetics judge) and
r1-check.md (acceptance check of every [M] item in round0-summary.md + all role red lines,
measured with Playwright, values checked against fixture.json).
Verdict: aesthetics "yes after fixes" (phone ~4/5, board 3/5, no red line); acceptance NOT
accepted: 16 PASS / 9 PARTIAL / 8 FAIL, 3 new red lines. All fixes are small and local.
GATE 1 waits for these fixes + a short re-check (checker only).

## [M] Red lines - fix first
1. tech-job shows "รอเริ่ม / เริ่มงาน" but the fixture job is in_progress (started 10:05, step
   2) and the board says "กำลังทำ เริ่ม 10:05". Show "กำลังทำ · ขั้น 2 จาก 6 · เริ่ม 10:05" with
   "ทำต่อขั้น 2". If the pre-start state is wanted, draw it on WO-000107 (assigned) instead.
2. Restore checklist, verify/restore outcome choices and wait/reason chips appear under
   "วิศวกรกำหนด · ฉบับที่ 3" but exist in neither fixture nor snapshot. Add them to the fixture as
   NEW_* with a stated source, or label them "ตัวอย่าง ยังไม่อนุมัติ" on screen.
3. ISO 7010: M021 (disconnect before maintenance) is wrong on the restore step - remove it;
   all ISO marks >= 48 px (REQ-H-03, now 40 px); add the Thai signal word (REQ-H-13).

## [M] Other fails
4. "เครื่องหยุด" for MC-018 appears 6x on the board incl. the station-4 tile with no stated
   source (round-0 item still open): label the source (operator report / signal) or reword
   to "เกินเกณฑ์", and take it off the station tile.
5. REQ-G-06: about half the phone text is 15 px (incl. the lock-owner strip) -> >= 18 px.
6. Board at 1024x768 shows 1 proposal row above the fold (S-10): compress the header/strip.
   Board at 1280 is 1409 px tall: rationale's "without scroll" is false - fix the claim or
   the layout (1920 already fits).
7. Operator manual report path (no QR) not drawn; estimate 6 taps vs <= 5 (P-01). Draw it.
8. Handover: add the 3-option lock question; the board needs a "ส่งต่อ รอคนรับ" action.
9. Lock strip shows no time (owner, point, lock no., TIME). "ดู" button 45 px wide -> >= 56.
10. Fixture: MC-004 ETA 21:00 in one field and 21:10 in another -> one value (21:10).
11. rationale.md: correct the false claims ("without scroll", G-06, H-13, "safety from approved
    data") and add G-06, H-03, H-13, H-06, S-10, T-01, P-01 to Unmet until fixed.

## Visual (aesthetics; owner rates as important as function)
12. Board: 56 bordered elements -> remove most; one chip style (not three); technician strip
    as a calm list/row, not boxed cards; lighten the column of 6 black "ยืนยัน" (one
    emphasis level for the top row or on hover/selection, quieter for the rest).
13. Board 1920 (wall screen): body 17-18 px; equal-height bottom panels, no dead space; fix
    "○ ต่ำ" baseline; PM row ETA must not wrap; station-card baselines aligned; 1024 less cramped.
14. Icons: replace text glyphs (⧗ ■ ◇ ○) with Lucide (Q10, approved) in one stroke style; keep
    ISO signs only as signs, in a fixed column, never as UI icons.
15. Hot-surface step: stat cells, the disabled "next" and nav rows share one grey - the
    disabled button must read as disabled; nav cards -> one grouped list; "CP-3 แล้ว" (space).
16. Re-render stale contact sheets (sheet-390full-a.png).

## Backlog to include now (owner decisions made while V was built)
- Q11: manual figure beside the step it cites (crop from the cited page, labelled sample) and a
  repair-history panel "ครั้งก่อนที่เครื่องนี้/รุ่นนี้" (synthetic, labelled) on tech-job/step.
- Q10: Lucide icons (see 14).

Keep: andon plate with the 8-lamp line position on every screen (best idea), calm amber
(outline = forecast, solid = now), 6-size type scale, Thai word-boundary breaks, 7:1 contrast,
fonts 87 KB/page, close/lock refusal, per-point isolation ticks, owner-only unlock.

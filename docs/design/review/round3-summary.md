# Round 3 (Phase 2 design system) - GATE 2 fixes (Cowork, 2026-11-15 23:40)

Reviewers: r3-aesthetics.md (Opus, aesthetics), r3-check.md (Sonnet, acceptance: own Playwright,
33 screens x 5 viewports = 165 renders), r3-engineer.md (Sonnet, engineer stakeholder, first time).
Verdicts: aesthetics pass after fixes (overall 3/5; phone 4, board 3, overview 3, engineer 2.5);
acceptance conditional pass (18 PASS / 6 PARTIAL / 3 FAIL); engineer not usable yet (safety 1/5).
GATE 2 waits for [M] items + a checker re-check (engineer re-check on items 1-3).

## [M] Red lines
1. Engineer review has no way to mark step kind (isolate / hot_surface / restore) or list
   isolation points (Q9, Phase A) - add to eng-review and show kinds in the eng-audit snapshot.
   Lockout/restore steps ask for a second reviewer at confirm.
2. eng-review: a step whose evidence failed (not found / mismatch) shows "ดูหลักฐานแล้ว" - evidence
   that failed can never count as seen; approval blocked until resolved.
3. eng-review approve bar + blocker list below the fold at 1280 and 1920 -> sticky, first screen.
4. eng-review step 6 edit field clips Thai (scrollWidth 681 > 530 at 1280) -> auto-growing textarea.
5. Primary action below the fold at 360x640: sign-in-error (659), unreachable-wifi (658),
   unreachable-server (686), eng-review-queue (686) -> compact stack or sticky action.
6. Reproducibility: base.py reads an absolute home path; data/seed1/eng.json not in data/ -> relative
   paths, copy the data in. Reconcile PM overdue "1 วัน" (eng-health) vs "เลย 2 วัน" (board/fixture).
7. S-01 counted the handover row: real proposals visible are 7 at 1280 and 14 at 1920. Gain ~10 px /
   ~40 px so 8 and 15 proposals fit, or restate S-01 honestly.

## [M] Other
8. Confirm dialog: say what technicians get when a step is rejected, and what happens to live work
   orders / a technician mid-job.
9. Gaps < 8 px: nav tabs 4 px on every eng-* page and line-overview (also on 1024 touch); board-15
   dense rows 4.5-5 px at 1920. Fix to 8 px, or write a desk-mouse exemption into the spec and
   drop the 8 px claim for 1024 touch (1024 is a tablet: fix it).
10. *_source for every NEW_* key (33 missing incl. NEW_playbook, NEW_eta_local,
    NEW_eta_confidence_minutes, NEW_state_detail, wait_reasons_th, lock_hold_reasons_th).
11. MC-018 "ระบบล็อกนิรภัยหยุดเครื่องอยู่" rests on an inference -> word it as what the interlock
    reported ("ล็อกนิรภัยแจ้งประตูเปิด") unless a source says the cell stopped.
12. S-10 (1024): technician list starts 633 px below the fold - show a compact strip or mark S-10
    "not met" in README.
13. Remove developer strings from user screens (API paths, "<table>", "Q11"); dates with year.
14. eng-health and eng-audit: add populated states (health table with the failure/MTBF
    definition stated; a closed WO from months ago; print render).

## Visual coherence (owner: as important as function)
15. Amber means only "over threshold" (solid) and "forecast" (outline). Test-data chip, stale strip,
    reassurance box and mismatch highlight get other treatments (neutral / info / red for mismatch).
16. Type scale back to the tokens (about 5 sizes, weights <= 700); wall board body 17-18 px (reject
    README decision 3 "15 px dense").
17. One callout style; remove coloured left-stripe callouts (6+ screens, the one template-looking
    pattern).
18. Replace Unicode arrows ↑↓→▾ with Lucide; fix board-15 handover-row white fade; components
    swatches wrapping one Thai word per line; eng tabs wrapping to two rows at 390.
19. Engineer screens up to the phone screens' craft: denser, calmer tables, evidence page image with
    jump-to-cited-page and "open in second window" (engineer fix 4).
20. Line overview floor plan: real geometry (line path, machine positions) or side-by-side with a
    machine list; must earn its 1100 px.

Keep: technician phone screens, Lucide + ISO-as-signs-only, print sheet, side-by-side review with exact
match and 24 vs 42 Nm mismatch bar, synthetic labels, measurements (contrast 7.05, 0 split words).

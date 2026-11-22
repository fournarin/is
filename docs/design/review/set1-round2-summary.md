# Phase 3 set 1, round 2 - PASSED with carry-over (Cowork, 2026-11-16 21:05)

s1r2-aesthetics.md: technician phone 4/5 - PASS (Q12). s1r2-check.md: conditional pass - phone rules,
tokens (18/24/36, 400/600), contrast >= 7.42, no h-scroll, no Thai splits, restored content verified.
Decision (Cowork): set 1 passes; the items below are carried into the set 2 round (fix them first,
re-capture set 1 pages that change) instead of another set-1 round, to save a review cycle.

## Carry-over [M] (fix at the start of set 2)
1. Honesty: manual excerpt on the step card and the manual page text come from the synthetic corpus but
   have no "(จำลอง)" label - label them like the history and figures.
2. Fold at 360x640: the offline strip pushes the primary action to y=720 - compact the strip (one line)
   so the primary stays above 640; tech-noplaybook actions below the fold - bring the primary up.
3. Manual text extraction merges lines ("procedure Symptom:", "Required tools" running into step 6) -
   keep line/paragraph breaks from the indexed page.
## Carry-over polish
4. Manual page: title runs into body (spacing); offline strip Wi-Fi-off icon ~10 px grey on black -> 24 px,
   readable; tech-job symptom line repeats the heading; one form for "จำลอง" across the system (chip or
   text, as the spec).
5. Add a two-job capture so the "ถัดไป N งาน" row is tested; tech-manual primary (y=1235) - fine with the
   back button on top, but consider a sticky "กลับไปขั้นที่ N".
## Reminder for set 2
- The lockout step (tech-step, step 2) still renders as a normal step - set 2 must match the spec's
  isolation step (ISO signs 48 px, signal word, isolation points, per-point confirmation, lock strip).

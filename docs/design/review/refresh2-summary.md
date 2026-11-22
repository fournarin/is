# Refresh round 2 (Q14) - review summary (Cowork, 2026-11-17 11:15)
rf2-aesthetics.md: board 4.5 / calm 5 (target met; "an advisor would proudly show it"; wall 4); technician
phone 4 / calm 4 (target 4.5); line overview 3.5 / calm 3 (FAILS calm); engineer 4 / calm 3.5; operator report 4.
rf2-check.md: conditional pass - light only, phone rules hold on 42 SSR renders, tap opens the reason drawer,
nothing safety-critical behind a tap.

## [M] Fix round (effort high for item 1, the rest is a concrete list)
1. Line overview - restructure for calm: the board's compact 8-number strip on top (not 8 cards); floor plan
   with lamps only (machine codes on tap, lighter dots); "สถานีที่ต้องดู" = one line per station; the machine
   list moves to a tab; station numbers shown once; fits 1080 at 1920.
2. Technician phone (to 4.5): tech-job shows the forecast once (drop the repeat under the temperature tiles);
   status row "◆ สูง · ขั้น 2/9"; tech-close-locked: the 5-line lock paragraph -> one line + "ทำไม" sheet.
3. Phone board text: 15 px nodes on board@390 and board-15@360/390 -> >= 18 px (and make MEASURE ignore hidden
   nodes so the floor is proved, not just counted).
4. Isolation step at 360x640: prove the primary/next action is reachable above the fold (or sticky); wait
   steps' disabled "next" below the fold is accepted.
5. Wall board 1920: scale type ~1.25 at >= 1600 px so rows read from 3 m (now 15-16 px).
6. Board polish: name before number ("ธนพล · 37 คัน"); severity word on the title baseline; single space in
   "ยืนยันให้ วิชัย"; the count chips under the queue become a real tab row.
7. Remove the dead prefers-color-scheme: dark rule.
Then: owner looks at board + line overview + phone; Cowork re-checks only the changed items.

# Visual refresh (Q13) review - one more round (Cowork, 2026-11-17 10:20)

rf-aesthetics.md (vs Vercel/Apple): wall board 1920 = 4.5 (target met, "best screen in the project");
technician phone 4 (target 4.5); engineer 4; board on phone 3.5; line overview 3.5. Advisor could proudly
present the wall board and technician phone now; not the line overview.
rf-check.md: conditional pass - phone rules hold on 42 renders, sheets open/close (outside tap, no JS),
reduced motion = 0 s, nothing safety-critical behind a tap, dark body text 16-18:1.
rf-safety.md: C1-C5 closed; refresh did not soften any safety element.

## [M] To reach the targets (aesthetics) - Effort: high
1. Line overview (1920 dark): redesign the floor plan - hairline outlines, lamps the only colour, smaller aisle
   band, no muddy dark-on-dark, use the lower half (machine list / station detail), not a recoloured old layout.
2. Board on phone (390): one-line subtitle, single-row KPI strip, short queue meta -> first card above ~420.
3. tech-job / tech-step above the fold must actually change (today near pixel-identical): one-line forecast,
   trimmed plate, more air; aim for the bottom-sheet screens' Apple feel on the main pages too.
4. Board on wall/touch: the priority reason is a hover preview - a TAP must open the drawer (wall touch,
   tablets). Capture it.
5. Re-capture the operator report at 390 in the refreshed style.
## [M] Behaviour (checker)
6. Prove on the hydrated app (live run, not static snapshots): focus moves into the sheet and back, Escape
   closes on desk, "ปิด" closes; give the backdrop an accessible name; "ปิด" >= 56 px wide.
## Polish
7. Close/handover legend 8 px past the card; one option style on those forms; drop the red left bar on critical
   board rows (stripe pattern) - use the marker + word; wall people panel 15 -> 17-18 px; "คุณพักไว้" card half
   empty; eng-gaps four cards read as a bento template - make it a calm list/table.
8. Safety minor: witness lockout after 5 failures blocks a lead for 15 min - show who/when and allow a
   supervisor reset; password field autocomplete="new-password"; handover screen says release from
   "กุญแจของฉัน" with the lead present.

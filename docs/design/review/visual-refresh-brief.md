# Visual refresh - "Vercel / Apple calm premium, still a factory tool" (owner Q13, 2026-11-16 22:48)

Owner: today's screens work in a plant but are not beautiful enough; target the feel of Vercel and Apple's
own apps; where a screen has too much text, show less and reveal details on demand (pop-up / sheet). The
result must be good enough for the advisor to present to a real plant.

Decision (Cowork, owner asked for a recommendation):
- Keep everything that makes it work in a plant: safety behaviour, ISO signs, status colour only for state
  (Vercel itself is monochrome + status colour, so this fits ISA-101), 18 px phone minimum, 56 px targets,
  looped Thai body text, the andon plate with lamps.
- Change the look, system-wide, through tokens and components (so sets 1-2 re-skin cheaply):
  1. Less on screen: every list item / card shows its essentials in <= 2 lines; explanations ("why this
     priority", evidence, history detail, manual excerpt) move behind a tap -> bottom sheet on phones,
     side drawer / popover on desk (hover preview + click on desk). No long-press (gloves, discoverability).
  2. Whitespace and hierarchy like Vercel/Apple: larger headline contrast, more air between groups,
     content width capped on desk, calm grid.
  3. Surfaces: hairline 1 px separators in a light neutral, radius 10-12 px, one subtle elevation for
     sheets/drawers only; no boxed-everything.
  4. Numbers and codes in tabular mono (Plex Mono, one weight); Thai in Plex Sans Thai Looped.
  5. Motion: 150-200 ms fade/slide for sheets, drawers, toasts and step changes; honour reduced motion.
  6. Dark theme for wall screens (board at 1920, line overview) - premium look and less glare on a wall;
     light theme for phones (sunlight) and the engineer desk. Both themes from the same tokens, contrast
     >= 7:1 body in both.
- Gate: the aesthetics judge scores against Vercel / Apple directly (not against HMIs); target >= 4/5 for
  every audience, 4.5 for the board and phone. Function rules unchanged.

Order: finish set 2 (safety round in progress) -> REFRESH round (design/system tokens + components + the
spec screens for board/engineer/overview updated; sets 1-2 re-skinned; dark wall theme) -> Cowork judges ->
sets 3-5 built on the refreshed system. Later (Cowork): a short demo script / deck for the advisor to
present to a plant.

## Owner correction Q14 (2026-11-17 10:05) - supersedes the dark wall theme above
The owner finds the dark board busy and confusing ("ลายตา งง") - for ALL of these reasons: the black background,
too many things on one page, dense text/numbers/codes, and no clear place to look first. Decisions:
- NO dark theme anywhere. Light theme for every screen (board, line overview included).
- The board's first screen shows ONLY what the shift lead must decide now: the decision queue (one clear focal
  point, the top item obviously first) and a compact line strip. Everything else - per-technician timeline,
  held by system, set aside by me, finished today, handover detail - moves behind tabs or a tap-to-open drawer,
  with a one-line count each ("ช่างว่าง 4 คน", "เสร็จแล้ว 3") so nothing is lost.
- Fewer codes and numbers on screen: machine name / station first; WO numbers, MC codes, minutes and ETAs
  only where the decision needs them, the rest in the drawer. One number per row at most in the main view.
- A clear reading order: what needs me now -> line status -> people. Generous whitespace, larger type for the
  focal item, quiet everything else.
- The owner's eye is the final judge: a screen he finds busy fails even if a reviewer scores it 4.5.

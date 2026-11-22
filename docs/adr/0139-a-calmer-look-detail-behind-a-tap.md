# ADR-139: A calmer look, with the detail behind a tap

Written on 2026-11-16. Extends ADR-133 (one design system). Carries out the
owner's decision Q13: the screens worked in a plant but were not beautiful
enough, and the target is the feel of Vercel's dashboard and Apple's own apps
while staying a factory tool. Decided by the agent on the owner's delegation
(ADR-090), with the design intent and an honest comparison written first
(ui-redesign-work/design/system/README.md).

## Decision

1. **The same rules, quieter surfaces.** Everything that makes the screens work
   in a plant stays: safety behaviour, ISO signs, colour only for state, 18 px
   on phones, 56 px targets, Looped Thai, the andon plate and lamps. The tokens
   change:
   - a paler canvas;
   - 12 px corners;
   - 1 px hairlines in a lighter neutral;
   - one elevation, used only by sheets and drawers;
   - 180 ms motion, with none under `prefers-reduced-motion`.
2. **Codes and figures in IBM Plex Mono**, one weight (400), self-hosted by
   `next/font` like the other faces. This adds no package. Machine ids, work
   orders and lock numbers now read as identifiers.
3. **At most two lines per item; the rest behind a tap.**
   - A sheet opens as a bottom sheet on a phone and a drawer from the right on
     a desk.
   - Its summary turns into the dimmed backdrop when open, so a tap outside
     closes it with no script; a "ปิด" button closes it too.
   - On the job page, the last jobs' notes and the ranking reason open this
     way, and so does every step on the step page.
   - The manual's original sentence on a step stays on the screen without a tap
     (REQ-H-01).
4. **A dark theme for wall screens** (the board at 1920 and the line overview),
   drawn from the same tokens. Every text pair stays at least 7:1, and text on
   amber is always dark. The board's queue rows become two lines; the ranking
   reason shows in a hover preview or the drawer instead of being cut off with
   an ellipsis.

## Consequences

The design system's spec screens for the board, the line overview and the
engineer review are rebuilt on these tokens, so sets 3-5 start from them. Sets
1-2 in the app are re-skinned through `v2.css` and the sheet panels; no rule or
endpoint changed.

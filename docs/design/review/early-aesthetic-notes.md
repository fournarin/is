# Early aesthetic read (Cowork, 2026-11-15 16:55) - NOT the gate review

Read of the renders as they stood at 16:41 (before Claude Code's finishing pass). The
independent 6-reviewer panel still runs after READY.md. These notes are design direction,
written because the owner rates beauty/appeal as equal to function.

Overall: all three are clean, honest and clearly NOT AI-slop (no emoji, no gradients, no
card soup, real data, real hierarchy). But none is beautiful yet. They read as very good
wireframes / government forms: correct but austere. "Correct but dull" fails the brief.

Shared problems (fix in all three)
1. Border overload: nearly every element is a 1-2px outlined box (buttons, tiles, steps,
   KPI cells). Premium industrial UI (Linear, Siemens WinCC Unified, Apple) separates with
   space and 1-2 surface tones, and keeps outlines for inputs only. Cut borders by half.
2. Equal-weight buttons: on the board every row carries 3 buttons (confirm / reassign /
   hold) x 6 rows = 18 boxes forming a heavy right column that dominates the page. Keep one
   clear primary per row (or act on the selected row with a detail pane), secondary as quiet
   text/menu.
3. Truncated reasons with "..." on the board: the priority reason is the core of the system
   and is cut on every row at 1280. Give it its own line or a column that wraps to 2 lines.
4. Thai line breaking: B and C break inside words ("ป้ายของตัว / เอง", "สายประกอบตัว /
   ถัง"). Thai has no spaces; use word segmentation (Intl.Segmenter at build time -> insert
   <wbr> or wrap words in nowrap spans) so breaks fall between words. A examiner/aesthetics
   judge will catch this instantly.
5. No surface hierarchy: white page, white panels, black text everywhere. Introduce one
   subtle canvas tone + raised work surface, and a deliberate typographic scale (e.g. 4
   sizes only) with consistent spacing steps (4/8/12/16/24/32/48).
6. Icons: drawn but generic (list, arrows, pencil). Make one coherent set on a 24 grid with
   the same stroke and corner style as the type.

Per concept
- A (HMI): best information design on the board (line strip with buffers, technician load
  strip, summary row). Weak: tech-step at 390 has a dead grey void mid-screen; KPI cell
  boxes and "MC-012" outlined chip look dated; top bar black band is heavy.
- B (document): margin step number "2 / จาก 6" is the most elegant idea of all three;
  provenance line (revision, approver) feels trustworthy. Weak: navy + many outlined boxes
  look like a 2000s intranet; severity "bar" glyph is unclear; the report form's checkbox
  grid is noisy.
- C (andon): strongest first impression - big clock, step rail with ticks, station badge
  "สถานี 3", line schematic first. Weak: hazard-tape hatching for "คาดว่าจะเกิน" is loud and
  reads as construction warning, not prediction; buffer tick marks are noisy; report uses
  solid black fills for selected tiles (very heavy) and mixes radio and checkbox styles.

Ideas worth combining later (for GATE 1 discussion): C's step rail + station badge + clock,
B's margin step number + provenance, A's technician load strip + line-with-buffers summary.

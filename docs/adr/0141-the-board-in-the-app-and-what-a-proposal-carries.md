# ADR-141: The board in the app, and what a proposal carries for it

Written on 2026-11-17. Builds ADR-140's board in the app (set 3 of the
frontend rebuild) and closes the third refresh review's list. Decided by the
agent on the owner's delegation (ADR-090), inside the owner's final plan for
November: the board is built, the line overview stays a design (spec only).

## Decision

1. **`/board` is the calm board of ADR-140.** It has four parts:
   - the line as one strip of station numbers, lit by state, with one
     sentence naming what is lit;
   - "รอคุณตัดสินใจ N เรื่อง": the top proposal as the one focal card, the
     rest one line each;
   - a drawer per item, opened by a tap: where, why first, state, the cost
     of waiting, whom the system proposes and why, and the work order;
   - tabs that open drawers, each with a count: people on the shift, held by
     the system, set aside, finished, and locks on now.

   Every answer is a plain form posted to the routes that already existed:
   confirm, give it to somebody else (ADR-132), set aside with a reason, bring
   back, and release with a reason. The page still composes no sentence of its
   own beyond labels. People are the ones the board can see: those holding
   work, and those the round could give work to. Locks are read from the
   tickets of the work out on the floor.
2. **A proposal carries `downtime_units`.** This is what the line loses in
   cars if the job waits. It comes from the same `downtime_or_unknown` the
   score uses (ADR-021), rounded to one place, and is `null` where the layout
   cannot place the machine. It is the board's one number per row, so the
   screen never makes a second estimate.
3. **A proposal carries `assigned_because`.** This is the trial's "ได้งานนี้
   เพราะ" line, in one line. Each part is something the round checked before it
   placed the job:
   - the skill the order asks for, or that it needs none;
   - minutes left in the shift. With none, the job is unassigned, not
     proposed (ADR-102).
   - what the person holds now, read from the orders.

   Nearness is not claimed: the plant gives no positions for people.
4. **Board banners carry no glyphs.** The screen puts a Lucide icon beside
   them, because the design system has no Unicode arrows or ticks.
5. **Technician screens, from the review's list:**
   - The forecast is shown once.
   - The status row is "◆ สูง · ขั้น 2/9".
   - The close screen's lock question is one line, with its reason behind
     "ทำไม".
   - On an energy step, a link to the next point waits at the bottom of the
     first screen until the points are reached.
6. **The old stylesheet's dark-mode block is removed.** ADR-140 left no dark
   theme, and that block was the last of it.

## Consequences

The proposal endpoint does one more order read and one more `assigned_to` per
proposal. A shift has a handful of proposals, so this costs nothing.

The board needs no new table and no new endpoint. People's free minutes and
the issued-padlock and abandoned-lock records stay future work. The board
says only what it can see.

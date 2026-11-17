# ADR-140: One light theme, and a board that asks first

Written on 2026-11-17. Replaces item 4 of ADR-139 (a dark theme for wall
screens). Carries out the owner's decision Q14 after the first refresh review:
the dark wall board scored well with the reviewer but not with the owner, who
found it busy. Decided by the agent on the owner's delegation (ADR-090).

## Decision

1. **No dark theme anywhere.** The board on the wall and the line overview use
   the same light tokens as every other screen. Colour still means state only.
2. **The board's first screen is what the shift lead must decide now.**
   - It starts with a compact line strip: station numbers lit by state, plus
     one sentence naming the stations that are over or forecast.
   - Under it is the decision queue. One focal card holds the top item: what
     is wrong, where, what waiting costs in cars, and whom the system proposes.
     The other items are one line each.
   - Everything else sits behind tabs that open a drawer, each with a one-line
     count: people in the shift, held by the system, set aside, finished, and
     locks.
   - Reading order: what needs me, then line status, then people.
3. **Names first, one number per row.** Rows lead with the machine's and
   station's names. Codes move into the drawer.
4. **A tap opens the reason.** Every queue row and the focal card open their
   detail drawer on a tap: where, why first, state, the cost of waiting, the
   proposal and the work order. Nothing depends on hover, so the wall's touch
   screen and tablets work.
5. **The line overview follows the same calm.**
   - The floor plan uses hairline footprints, with the lamp as the only colour.
   - Beside it sit the stations that need a look. Below 1200 px those come
     first and the plan follows.
6. **Sheets behave as dialogs on the hydrated app.**
   - Opening one moves focus into it, and the dimmed backdrop gets an
     accessible name.
   - Escape closes it, and focus returns to the row that opened it.
   - "ปิด" is at least 56 px square.
   - This is a small client component (`SheetFocus`); the sheets still open and
     close without script.
7. **A held witness can be cleared by another lead.**
   - After five refused passwords, ADR-138's rate limit holds that witness for
     15 minutes.
   - The refusal now says who is held, when the last failure was and when the
     hold ends.
   - A different supervisor can clear it with
     `POST /witness-lockouts/{user}/reset`. Clearing your own hold is refused,
     and the reset is written to `access_log`.

## Consequences

The design system's board and line overview are rebuilt light. The dark
variant and its CSS are gone, so there is one theme to test.

The witness reset is the only backend change. It adds no table, because a hold
is counted from `access_log` after the last reset.

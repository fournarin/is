# ADR-094: A person's minutes are real minutes, even in a demo

Written on 2026-09-27, while rebuilding the screens after the owner's trial
(ADR-092, ADR-093).

## Context

[ADR-044](0044-the-trigger-loop-what-ticks-it-and-what-feeds-it.md) §4 compresses
the twelve-hour synthetic scenario by running `worker-runtime` on a
`ScaledClock` at 60x. The speed sits on the clock and not on the feed, so every
window in the system stays on one timeline with the data.

That is right for machine windows, such as a rule's `for_seconds`, a cooldown or
an ETA. It is wrong for windows that measure a person. A proposal gives the
shift lead `proposal_expires_minutes: 30` to confirm it. At 60x that is thirty
seconds, and proposals returned to the queue before anyone had loaded the
board. In the owner's trial the board and the technician's screen were empty
while the system reported work released, which is one of the reasons the
screens read as confusing.

## Decision

1. **Demos and trials run at real speed.** `SIGNAL_SPEED` defaults to 1 in
   `docker-compose.yml` and `.env.example`. Compression is still available for
   a run nobody has to act in.
2. **The synthetic feed can start part-way into its scenario.**
   `SIGNAL_HEAD_START_HOURS` (default 7 in the compose file) makes the feed hand
   over the first seven hours of readings at once, as one backlog batch (the
   case `Feed.due` already handles), and then advance at the clock's pace. The
   trend is there to extrapolate from immediately, so forecasts appear straight
   away. The first threshold crossings (the cabinet fan at 7:30 and the belt
   motor at 7:40 in the scenario's own ground truth) arrive about half an hour
   into the session.
3. The clock remains the single time port (ADR-028). Nothing reads wall time
   beside it. The head start is an offset on the source, not a second clock.

## Consequences

- A thirty-minute confirmation window is thirty minutes on the board, and the
  times shown on tickets are the times on the wall.
- A full twelve-hour run at real speed takes twelve hours. A demo that needs the
  whole arc, including the late crossings on MC-004 and MC-012, either waits or
  sets `SIGNAL_SPEED` and accepts that people's windows shrink with it.
- `ReplaySource` is unaffected: the head start applies to the synthetic feed
  only.

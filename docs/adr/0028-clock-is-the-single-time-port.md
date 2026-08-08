# ADR-028: `Clock` is the single time port for the system

## Context

The dispatch signature already took a clock, but no document said where *the rest
of the system* reads time from - while time-dependent behaviour is everywhere:
Finding cooldowns and ETA grace, work segments crossing shifts, elapsed waiting
time in the score, ETA error measurement.

Two requirements also conflict directly. `SyntheticSource` must model degradation
over hours or days, while the demo the advisor takes to the plant must show a
result within minutes.

If each site reads the system clock itself, a compressed run gives a Finding a
simulated detection time while its cooldown is compared against real time - so
the cooldown either never expires or expires immediately, depending which way the
run was compressed. And ETA error cannot be measured at all, because predicted
and actual times sit on different axes.

## Decision

- One `Clock` port, injected everywhere time is read, with two implementations:
  a system clock and a simulated one.
- **Every business-meaningful timestamp the system writes comes from the Clock.**
  No database `now()` defaults.
- No direct calls to the operating system clock in domain code, enforced by a
  gate in CI in the same way as the LLM import rule.
- Store UTC, timezone-aware, everywhere; convert to local time only for display.
- **Keep the two time axes apart:** a Signal's timestamp is *source* time, from
  the plant or the generator. The Clock supplies *decision* time only. They are
  not the same thing and will not agree once a live source is connected.

## Reasons

1. The conflicting requirements above have one resolution: **make time something
   the system is given rather than something it reads from its environment.**
2. **The cost now is one parameter; the cost in week 7 is finding every site that
   reads a clock in a running system** - and week 7 is when the scheduler is
   being built.
3. **It makes tests possible that otherwise could not be written.** A job
   crossing a shift, a cooldown expiring, an ETA lapsing all require real time to
   pass. With an injectable clock they run in CI in milliseconds, which turns the
   invariants promised by two other ADRs into things that are actually checked
   rather than things that pass because nobody checks them.
4. **It is a precondition of the scheduler-weights loop, alongside dispatch
   purity.** Replaying past events under different weights means setting the
   clock to the past.
5. **The demo needs no special mode.** Compression is a different implementation
   of the same port; every line of logic stays identical to production, which is
   what ADR-024 requires when it forbids a demo mode that behaves differently.

## Consequences

- New invariant: no domain module reads the operating system clock directly.
- Clock skew needs a policy once a live source is connected - signals timestamped
  ahead of or behind our clock. Not needed yet, but separating the two axes now
  means it can be added without rework.
- The simulated clock must advance by events rather than by a multiplier on real
  time, or hundreds of scenarios in CI would consume the real duration they
  simulate.

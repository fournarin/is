# ADR-023: `Finding` has a lifecycle and a suppression window

## Context

"Risk of alarm flood" was listed as a drawback of threshold rules from the start,
and no document then addressed it. Meanwhile `Finding` was designed as a stateless
event: the rule fires, a record appears.

Left alone: one overheating motor raises a Finding on every reading, becomes a
hundred work orders within an hour, `load_ratio` passes 100%, the gate holds back
everything, and the technician sees a queue full of noise. **The system destroys
itself in its first hour on real data.**

## Decision

1. `Finding` carries a `status`: open / acknowledged / resolved / expired /
   superseded.
2. **The suppression key is (`machine_id`, `rule_id`).** While an open or
   acknowledged Finding exists for that pair, a repeat firing updates
   `occurrence_count` and `last_seen_at` rather than creating a record.
3. After `resolved`, a cooldown must pass before a new one can be raised,
   stopping a sensor oscillating across the threshold from producing an endless
   stream.
4. **A machine under repair suppresses Findings from the same rule** - but,
5. **a rule of higher severity always passes, with no suppression.** If an
   interlock fails while the motor is being repaired, that must fire immediately.
6. A predicted Finding whose ETA plus grace passes without event becomes
   `expired`.
7. A detected Finding arriving while a predicted one is open for the same
   (`machine_id`, `component`) supersedes it, so two work orders are not issued.

## Reasons

- **Points 4 and 5 together are the heart of it.** Blanket suppression during
  repair is how people get killed: a technician climbs inside a machine and the
  safety signal is swallowed because "this machine is being repaired". Suppression
  is therefore tied to the rule, not to the machine.
- Point 7 prevents duplicates and is also **the data collection point for the ETA
  accuracy loop**: the moment a prediction is superseded is the moment its error
  becomes known.

## Consequences

- `occurrence_count` is valuable in itself: a rule that fired a thousand times
  before anyone looked is a rule whose threshold is too sensitive.
- The technician's screen must show "seen N times since ..." rather than
  presenting it as a single event.
- Cooldown and ETA grace values live in configuration, never in code.

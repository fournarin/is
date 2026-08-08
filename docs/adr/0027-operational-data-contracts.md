# ADR-027: Operational data contracts - Station, Technician, Shift, PMTask

## Context

The project brief locks four data contracts, and all four describe *work*. None
describes *resources and places*, which is everything layer 3 - the core of this
project - needs. Several places referred to data with no contract behind it:

- The dispatch signature takes technicians, which was never defined.
- ADR-011 needs shift capacity, with no statement of what a shift is or in what
  unit it is measured.
- ADR-021 computes downtime per station and buffer, but a Signal and a Finding
  carry only a machine id - **no map from machine to station existed anywhere**.
- ADR-010 refers to a PM task reference with no PMTask contract.
- Skill matching compares a playbook's required skill against a technician's
  skills; drawn from two different lists, they fail to match in silence.

## Decision

Add four contracts, divided by how often they change: **structural changes belong
in configuration, daily changes belong in the database.**

```
configuration (in the same file that declares rules and component labels)
  Line     : line_id, takt_seconds
  Station  : station_id, line_id, seq, buffer_units,
             bottleneck_multiplier, machine_ids[]
  Skill    : the list of skill labels
  ShiftDef : shift_id, start, end

database
  Technician      : user, skills[], active
  ShiftAssignment : shift_id, date, technician, available_minutes
  PMTask          : pm_task_ref, machine_id, symptom_code, interval,
                    last_done_at, due_at
```

And settle two things that were ambiguous:

1. **`load_ratio` is person-minutes on both sides.** Capacity is the sum of
   available minutes across the shift's assignments; pending work is the sum of
   estimated minutes multiplied by required technicians.
2. **PM work uses a `symptom_code` with a `PM-` prefix**, not a second lookup
   path.

## Reasons

1. **Point 2 matters more than it looks.** ADR-010 left behind the consequence
   that "layer 2 must find a playbook for PM work too", which sounds like a second
   retrieval path. Giving a PM task a `PM-xxx` symptom code means the playbook
   table is keyed by (`symptom_code`, `machine_model`) exactly as before and
   **layer 2 never learns the word PM at all**. One path, one set of logic, one
   set of tests.
2. **Station is configuration and does not contradict ADR-016.** That ADR refused
   part entities because a parts taxonomy has no owner. The station layout has a
   clear one in production engineering, already exists on the plant's drawings,
   and changes when the line is rearranged - a yearly event, not a daily one.
3. **Skill is a configuration label for every reason ADR-016 gave.** Validated at
   boot; a label outside the list stops the boot. This is the only thing standing
   between us and skill matching that fails invisibly - work still gets assigned,
   just to the wrong people, with nothing to show for it.
4. **Shift definition is separate from shift assignment** because "the morning
   shift runs 06:00 to 14:00" changes once a year while "who is on it today"
   changes daily. Combined, the stable half would be dragged into the database
   with the volatile one.
5. **It makes the data request to the plant concrete.** "Technician data" is too
   broad to answer; these four contracts can be asked for directly. And if the
   answer does not come, seeded values work immediately, because the most
   important part is configuration rather than a table.

## Consequences

- The brief's "lock these four contracts" becomes four describing work plus four
  describing resources.
- Two new invariants, both validated at boot: **a skill label referenced by a
  playbook or a technician must exist in the list**, and **every machine a rule
  can name must appear in the topology**. The second matters because a Finding on
  a machine with no station cannot have its downtime cost computed, and depending
  on how the scheduler is written that is either a zero score or a crash - both
  wrong.
- The dispatch signature does not change: topology arrives through configuration,
  which is already an argument. The function stays pure.
- No part entity is added. ADR-016 remains in force.

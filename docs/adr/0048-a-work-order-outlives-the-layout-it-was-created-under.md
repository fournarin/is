# ADR-048: A work order outlives the layout it was created under

## Context

ADR-027 keeps the plant's physical layout in `plant.yaml` and out of the
database, on the argument that the layout changes when the line is rearranged
while old records must keep meaning what they meant. ADR-041 copies
`machine_id` onto the work order so the scheduler needs no lookup to know what
the job is about.

Both are right, and together they guarantee drift: an order written in March for
`MC-012` is still open in June, when `MC-012` has been moved to another line,
replaced by a different model, or taken out of the file entirely.

`Config.station_of` says in its own docstring that "validation guarantees the
lookup cannot miss". That is true of a machine id that came *from* configuration
and false of one that came from a work order, and layer 3 does the second
without noticing:

```
dispatch([Queued(ref="WO-X", order=order(machine_id="MC-999"), ...)], ...)
-> KeyError 'MC-999'
```

The round returns nothing. Not "that one order is a problem" - nothing. Every
other machine on the line, all of them still in the layout and some of them
stopped, goes unscheduled because one order names a machine that has moved. And
it is silent in the worst way: a scheduling round that produces no tickets looks
exactly like a shift with no work.

## Decision

**The order is scheduled. Its downtime term is zero, and both the ticket and the
round say why.**

### 1. Zero, and entered into the round rather than left out

ADR-045 §1 normalises the downtime term by dividing by the largest value in the
same round. An order left out of that list would change every other order's
term, so an unknown machine enters it as a zero and is ranked with everything
else.

### 2. That zero is marked, because an honest zero looks identical

A repair shorter than the station's buffer also scores zero on downtime - the
line has enough queued ahead of it not to notice. That is a fact about the
plant. An unknown machine scoring zero is the absence of a fact. `Terms` carries
`downtime_is_unknown` so a reader can tell a line that will not feel this from a
line we cannot speak for.

### 3. The ticket carries the caveat, and the round carries the count

The ticket names the machine and says the cost of leaving it down was not
counted, because that is where somebody is standing when they decide whether to
believe the ranking (ADR-005). The round's summary counts them, so the
supervisor's one sentence reports that the layout file has drifted - every
round, until somebody edits it.

## Reasons

**Withholding the order was the obvious alternative and is worse.** It makes the
configuration error loud, which is the right instinct, and it does it by parking
real work on a real machine until somebody edits a YAML file. The machine did
not stop being broken because the layout file is stale, and a technician who
learns that the system silently swallows jobs stops using the system. Principle
5 in `CLAUDE.md` is "when the evidence is thin, say so" - not "refuse the work".
Section 3 above buys the loudness without paying for it in work nobody does.

**Ranking it low is honest rather than a compromise.** The system cannot claim a
line cost it cannot compute. An order that scores zero on one of five terms is
still ranked by severity, waiting time, skill and ETA, so an urgent job on a
machine missing from the file is still urgent - it simply is not credited with
stopping a line nobody can confirm it stops.

**Nothing is invented.** No default station, no assumed buffer, no "probably a
bottleneck". Each would be a number with no source, which this project treats as
the same defect as an unapproved playbook.

## Consequences

- An order for an unknown machine ranks lower than the same order on a known
  bottleneck, and the ticket says why. This is visible to the technician rather
  than only to whoever reads the code.
- The drift is reported in every round's summary until the layout is corrected.
  There is no new status, no new column, and nothing to clear afterwards: if the
  machine reappears in `plant.yaml`, the next round prices it normally.
- `station_of` still raises `KeyError` for its other callers. Layer 2 and the API
  reach it too, and whether they should share this treatment is a question about
  those paths rather than about this one - to be answered where they are, not
  here.
- The same shape will be needed by anything else that prices a work order
  against the layout, the simulator's cost function included. It reads the
  layout for machines it generated itself, so it cannot drift today.

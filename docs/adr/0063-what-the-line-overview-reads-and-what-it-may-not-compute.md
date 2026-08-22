# ADR-063: What the line overview reads, and what it may not compute

## Context

ADR-050 settled that the gate's report is computed when asked rather than
stored, and ADR-060 did the same job for the authoring queue. Slice 9.4 adds the
third read path - `GET /overview/line`, the data behind the screen the project
is demonstrated from - and it raises three questions neither record answers,
because neither had to draw a line.

**What one station shows when several things are wrong with it.** A station
holds more than one machine, a machine holds more than one rule, and ADR-023 §7
has a prediction and the detection that supersedes it live at the same time on
purpose. The screen has one marker per station. Something has to choose.

**Where the shift's figures come from.** The band shows a load ratio, a
capacity, a technician count and how much work is open. Every one of those is
something a round already computed, and every one of them could be recomputed
here from the same tables - producing a second implementation of the gate's
arithmetic that would look plausible while disagreeing with the scheduler.

**What "the buffer between two stations" is on the response.** ADR-021 put a
`buffer_units` on each station and priced downtime with it. The overview draws
the line as boxes and edges, and an edge has to get its length from somewhere.

## Decision

### 1. One state per station, and a crossing that has happened outranks one that is expected

Three states and no fourth: `normal`, `predicted`, `over_threshold`. Gradations
between them - "degraded", "warning" - are a scale a reader has to interpret,
and two readers standing at the same screen would interpret it differently.

The marker is chosen in this order:

1. any live **detected** Finding on any machine at the station wins, because it
   is already costing production while the other is a forecast;
2. among several detected, the highest severity, then the one that has been over
   longest - severity is what the load gate admits on (ADR-011) and at equal
   severity the older fault is the one nobody has reached;
3. otherwise the **soonest** predicted crossing - not the most severe one. A
   critical crossing in nine hours and a medium one in two are decided in the
   other order, and the second is what the shift in front of somebody has to
   absorb;
4. otherwise `normal`.

Every key ends with the machine and the rule, so the same data always draws the
same screen (invariant 10's habit, applied to a read path).

**The station also reports how many live Findings it has.** One of three shown
without saying so reads as though there were one, which is the silent-cap
failure ADR-045 names one screen up.

### 2. The ETA and its interval are paired by the response model, not by the handler

`StationView` refuses to be constructed as `predicted` without both, and refuses
to carry either when it is not. ADR-020 and ADR-043 §3 both forbid dropping the
interval; putting the check in the handler would leave the next assembler of
that model - a fixture, a test, the screen in slice 10.5 - free to build the
tidier, dishonest version. The same validator refuses `over_threshold_minutes`
on a station that is not over its threshold.

### 3. The shift band is the round's own numbers, and `Round` grows two counts to make that possible

`dispatch.domain.Round` gains `technicians_on_shift` and `open_orders`. Both are
counts of what the round was already handed - `len(assignments)` and
`len(queue)` - and neither changes any decision the round makes. `open_orders`
counts the whole open queue, taken work included, which is why it is not
`len(placed) + len(unassigned) + len(held)`.

They live on the round rather than being fetched here because the alternative is
a second roster query and a second pass over the same orders: a copy of the
gate's arithmetic, in the place a shift lead reads it. ADR-050 rejected a stored
report for exactly that reason, and a recomputed one is the same object with a
shorter life.

`held` is returned as a **count**, not as the rows. The rows are
`/dispatch/round`'s answer and the screen asks that endpoint when the shift lead
opens the panel; two endpoints serving the same list is how they come to differ.

The whole response is stamped with the round's own moment rather than a second
clock read, so the stations and the band cannot describe two instants.

### 4. The edge is the station's own buffer, in units and in minutes

`Station.buffer_units` is what stands between that station and the next, and it
is what the overview draws the edge from. It is returned in units - what
`plant.yaml` holds and what an engineer argues about - and in minutes at the
line's takt, through `Station.buffer_minutes`, because minutes are the only form
comparable with a repair time (ADR-021's formula).

**A station is a bottleneck when its `bottleneck_multiplier` is above 1.0.** It
is the only signal the configuration carries, and the multiplier is returned
beside the flag so a reader can see by how much rather than take the word for
it.

### 5. A machine with a live Finding and no station is named, not dropped

As `/overview/gaps` already does it (ADR-048 §3). Its fault cannot be drawn
anywhere, and a line that quietly omitted it would read as quieter than it is.

## Reasons

**The choosing rule is the part that would have been invented.** Every other
figure on this screen is a row that exists; "which of these four faults is the
one on the marker" is a judgement, and a judgement made inside a handler with no
record is one nobody can argue with later. It is written here so that the first
technician who says "that is not the one I would have shown" has something to
argue with.

**Pairing the ETA in the model is the cheapest place to make ADR-020 true.**
The interval is the one thing on this screen an ordinary maintenance board does
not have, and it is also the first thing anybody tidying a layout would drop.

**Two counts on `Round` are a smaller price than a second summation.** The rule
`dispatch()` may not read a table (invariant 10) is untouched: both counts are
computed from arguments it was already given.

## Consequences

- Slice 10.5 draws edges to scale from `buffer_units` or `buffer_minutes` and
  needs no fourth endpoint to do it; the held work it names comes from
  `/dispatch/round`, and the "no answer yet" panel from `/overview/gaps`.
- **A station with two faults shows one.** The count says there are two and the
  ticket queue lists them; a reader who wants all of them is on the wrong
  screen. If that turns out to be wrong in front of a real shift lead, it is a
  new record and not an edit to this one.
- `/overview/line` is readable by engineers and supervisors, the two roles that
  share the screen (ADR-024). A technician's view of the same fault is their own
  ticket, which is ADR-061.
- The response says nothing about *why* a station is ranked where it is in the
  queue. That is `priority_reason` on the order, and duplicating it here would
  be the second answer to a question ADR-041 kept to one field.

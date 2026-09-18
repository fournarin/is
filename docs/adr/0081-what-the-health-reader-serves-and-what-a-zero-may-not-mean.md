# ADR-081: What the health reader serves, and what a zero from an empty table may not mean

Wires [ADR-072](0072-machine-health-is-read-not-a-source-of-work.md) and
[ADR-076](0076-what-machine-health-is-computed-from-and-what-it-may-not-be-ranked-by.md)
to a reader and a screen, under the rule
[ADR-063](0063-what-the-line-overview-reads-and-what-it-may-not-compute.md) set
for everything else on that screen.

## Context

`assess()` has existed since slice 15.1 and nobody can see it. Nothing in
`src/pdm/api/` or `web/app/` imports `pdm.health` at all, so the advisor's answer
to "where should I start" is a pure function with a measurement behind it and no
way into the room.

Wiring it up is mostly mechanical - load, call, sort, serialise. Three things in
it are not, and all three are about what the reading is allowed to claim.

**There is no `pm_task` table.** `PMTask` is a contract with no store behind it;
`migrations/versions/0006_work_orders.py` mentions `pm_task_ref` only as a
nullable column. Slice 16.1 builds the table, and until it does, a reader can
only hand `assess()` an empty sequence of tasks. `HistoryContribution.pm_overdue`
is `int = 0`, so every machine on the screen would read **"0 overdue PM tasks"**
- which is not what is known. What is known is that nothing was asked.

This is the failure the same file already refuses one field higher up:
`failures_per_100_days` is `None` rather than `0.0` when there is no span,
because "this machine does not fail" is a claim and "nothing has been observed"
is the truth. The PM figures reach the screen with the claim and not the truth.

**The rates are only as good as the span behind them**, and ADR-076 §4 already
requires the span be carried beside them. On a stack seeded yesterday
`observed_from` is yesterday, so one closed failure is "200 failures per 100
days" - a figure that is arithmetically correct, alarming, and meaningless. In a
document that rule is satisfied by the field existing. On a screen it is
satisfied only if somebody reading the number cannot avoid reading the span.

**And `AGE_AGAINST_ITS_CLASS_IS_ABSENT` is on every reading**, identical each
time. Four machines means four copies of the same paragraph, which is how a
caveat becomes wallpaper.

## Decision

### 1. `GET /overview/health` serves two orderings, and there is no third list

`by_history` and `by_now` are returned as two arrays of the same readings, in
the order the two functions give. No merged list, no sort of one by the other,
no score, and no field that could become one. ADR-072 §2 is the record this
endpoint exists to obey, and the response model is where obeying it is visible:
adding a blended figure means adding a field, which means editing this file.

Engineer and supervisor, the same pair as `/overview/line` and `/overview/gaps`
(ADR-024). It is the supervisor's question, and the engineer is on the list for
the reason they are on the others: they are asked why it says what it says.

### 2. The reader names what it could not load, and a zero from an empty table is not a fact

The response carries `absent`: sentences about what this reading cannot say.
Two go in it today.

The first is the age caveat the domain already writes, lifted from the readings,
de-duplicated, and carried **once per response rather than once per machine**.
Every row would otherwise carry the same paragraph, and a caveat repeated four
times is one nobody finishes reading. The domain keeps it per reading, because a
reading handed to something that is not this screen must arrive with it.

The second is new and belongs to the reader rather than to the domain:

> preventive maintenance standing: nothing in this system stores PM tasks yet,
> so no reading here can say whether a machine's PM is overdue. The counts below
> are what was asked for, which is nothing (slice 16.1, ADR-072)

**`pm_overdue` and `pm_completed` are still served**, because they are what
`assess()` returned and the reader does not edit its answer. What changes is
that they arrive next to a sentence saying the question was never put.

Two alternatives were refused:

- **Let the zero speak.** It is the shortest path and the one principle 5 exists
  to prevent: "0 overdue" is a claim about a plant, drawn from an empty table,
  shown to somebody deciding what to look at.
- **Make `pm_overdue` an `int | None` in the domain.** Honest, and it changes
  the shape of the published measurement in `docs/results/health.md` and the
  fixtures that produced it, for a distinction the reader can make on its own
  from what it was able to load. When slice 16.1 lands, the reader passes real
  tasks and deletes a sentence; the domain does not move either way.

### 3. The span travels with every rate, on the wire and on the screen

`observed_from`, `observed_to` and `observed_days` are on the response as well
as on each reading, and the screen may not show a rate without showing the span
it was counted over. A rate with no span is the one figure on this screen that
can be read as alarming when it is empty.

**No threshold decides when to say it.** A first draft had the reader flag a
span shorter than a fortnight, and a fortnight is a number with nothing behind
it - the kind `docs/decisions-to-defend.md` says has to stop and wait for a
person. The span is instead named on the panel itself, always, so there is no
case in which a rate appears without it and no constant that can be wrong.

The one distinction that is not arbitrary is already in the domain: a machine
with no span to divide by gets `failures_per_100_days = None` rather than 0.0,
and the screen renders that as "nothing observed" rather than as a number.

### 4. Machines the layout does not know are reported, not dropped

`assess()` is asked about the machines in `plant.yaml`, so a closed order or an
open Finding naming a machine the layout forgot contributes to nothing. The
response carries those machine ids in `unplaced_machines`, exactly as
`/overview/line` does, for ADR-048's reason: the machine did not stop existing
because the file is stale, and a reading that silently omitted it would hide the
drift rather than report it.

### 5. Nothing is computed in the reader or on the screen

The endpoint loads, calls `assess()`, sorts with `by_history` and `by_now`, and
serialises. The screen renders. Every figure on it is a field, and the reason
sentence beside each row is the one the domain wrote - not one assembled in
TypeScript from the fields beside it, which would be a second voice explaining
the same number (ADR-063, invariant 10).

## Consequences

- **A second reader will have to change when slice 16.1 lands.** The PM sentence
  comes out and real tasks go in. That is the intended shape: the absence is
  written in one place, and the slice that ends it deletes it there.
- `work.repo` grows `closed_orders`, which returns orders and not
  `ClosedRepair` - `work/` may not import `health/` (ADR-072 §4), so the API
  builds the reduction. That is the same composition the rest of the API does
  and it keeps the ban structural.
- **The screen has a section that will look empty on a fresh stack**, because a
  stack seeded this morning has no closed orders and every machine reads "nothing
  observed". That is the correct reading and the screen says it in those words.
  It also means the most useful demo of this panel is one run against a database
  with history in it, which `fixtures/history` can generate and
  `scripts/seed_demo.py` deliberately does not.
- Nothing here can create work, feed the score, or predict. `.importlinter`
  already refuses all three at the import level, and this record adds no path
  around them: the endpoint imports `pdm.health` and `pdm.work.repo` separately
  and hands one's output to the other.

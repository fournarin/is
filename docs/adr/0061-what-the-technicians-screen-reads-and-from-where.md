# ADR-061: What the technician's screen reads, and from where

Revisits
[ADR-041](0041-a-work-order-carries-what-the-scheduler-needs-to-schedule-it.md),
which froze onto the work order everything the scheduler needs, and
[ADR-030](0030-package-layout-io-boundary-and-self-contained-work-orders.md),
whose import rule is the thing that makes that freezing load-bearing.

## Context

Slice 10.3 puts one work order in front of the person who has to do it, and two
questions came up that neither record answers on its own.

**The first is where "seen 34 times since 08:12" comes from.** ADR-041 copies
`machine_id`, `severity`, `finding_kind` and `eta` onto the order at creation
precisely so that layer 3 never reads a Finding, and `.importlinter` enforces
that with a rule naming `pdm.dispatch`. But the count of how often a rule has
fired is the one figure on the screen that has to be *current*: ADR-023 raises
`occurrence_count` on the existing record rather than opening a second one, and
a screen quoting the value frozen at creation would say "seen once" about a
motor that has been shouting all morning.

**The second is what time a timestamp is spelled in.** Every timestamp in this
system is UTC. Every timestamp a person reads is plant-local. Nothing had said
who converts, and the easy answer - the device - is wrong in a way that only
shows up later.

## Decision

### 1. The API may read a Finding for display; layer 3 may not read one at all

`pdm.api.dispatch` reads through `finding_ref` to serve `occurrence_count`,
`detected_at` and `last_seen_at` on the ticket. The rule in `.importlinter`
names `pdm.dispatch`, and it stays exactly as narrow as it is.

Work with no Finding - scheduled and manual, most of the backlog (ADR-010) -
serves `recurrence: null` rather than a count of one.

### 2. Everything else on the ticket comes from the order's own copy

The steps come from `playbook_snapshot`, the ETA and its interval from the
fields ADR-041 froze there. The screen never reads the playbook table.

### 3. A prediction's interval is not optional at this seam either

`eta_confidence_minutes` is serialised whenever `finding_kind` is predicted. The
contract already enforces the pair on the `Finding` (ADR-020); the ticket view
enforces it again, and a test asserts it.

### 4. Plant-local time comes from the configuration, through the round

`RoundView` carries `timezone`, read from `config/plant.yaml`. The web layer
formats with it and never with the device's own zone.

## Reasons

1. **The invariant is about scheduling, not about reading.** What ADR-030
   forbids is layer 3 *deciding* from a Finding - because a scheduler that
   reaches into the trigger layer cannot be replayed, cannot be tested without
   one, and re-ranks itself when a rule fires again. None of that is true of an
   endpoint assembling a screen. Widening the import rule to cover
   `pdm.api.dispatch` would ban a read that harms nothing; narrowing the
   principle to "nobody may ever read a Finding" would ban the one figure ADR-023
   exists to produce.

   The two halves are then visibly different on the response: `recurrence` is
   live, everything beside it is a snapshot, and the test that matters asserts
   both at once - the count moves, the severity and the ETA do not.

2. **"Seen once" and "there is nothing to count" are different sentences.** A
   screen that prints the first when it means the second is telling a technician
   something false about a machine, in the one place where being trusted is the
   whole product. Hence `null`, not a default.

3. **The device's timezone is a fact about the phone, not about the plant.** A
   technician standing on the line has both, so the mistake is invisible where it
   is made and appears where it costs most: a shift lead reading the same screen
   from a laptop set to UTC, or an engineer reviewing a shift from home, seeing
   "08:12" for something that happened at three in the afternoon. The plant has
   one clock, it is in `plant.yaml`, and it already governs the shift boundaries
   the round is computed against (ADR-045 §7).

   It rides on the round rather than on every ticket because the round is
   already the plant-facing view - it carries `shift_id` and a plant-local
   `on_date` - and a zone repeated on every ticket is a zone that can disagree
   with itself.

## Consequences

- **`pdm.api` is now the only place that reads across all four of work,
  dispatch, playbooks and triggers.** That is what a composition layer is for,
  and it is the reason none of the four import each other.
- **A ticket for scheduled or manual work has no recurrence block**, so the
  screen shows no "seen N times" line at all rather than an empty one.
- **A screen that wants a wall-clock time must read the round**, even when it
  otherwise only needs one ticket. That is a small cost and it keeps the zone
  in one place; if a screen ever needs the time without the round, the answer is
  to serve the plant's configuration, not to fall back to the device.
- The import rule is untouched, and this record is what to point at when
  somebody reads `pdm.api.dispatch` importing `pdm.triggers` and reaches for
  `git blame`.

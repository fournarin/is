# ADR-083: The PM schedule becomes a source of work, and what a schedule nobody has records for costs

Slice 16.1, from #90. Builds the second of the three sources of work `CLAUDE.md`
names (ADR-010) and closes the apology ADR-081 wrote into the health screen: the
reader has been reporting `pm_overdue = 0` for every machine, from a table that
did not exist.

## Context

`WorkOrders.from_pm_task()` has existed since slice 3.1 and was called only by
tests. There was no `pm_task` table, no PM task in `config/`, and nothing in
`worker-runtime` that looked for one. So the quiet-shift half of ADR-011 - the
behaviour the advisor described most concretely, "ถ้างานเบาก็เลือก priority รองให้
ไปทำได้" - was switching over an empty queue: the gate released low-priority work
and there was none.

The health screen made the gap visible in the other direction. `pm_overdue` is
an `int` with a default of 0, so every machine read as having nothing overdue.
ADR-081 §2 refused to let that zero speak and wrote a sentence beside it saying
nothing had been asked. This slice is what that sentence was waiting for.

## Decision

### 1. The definition is configuration; the state is a table

`plant.yaml` gains `pm_tasks`: a ref, a machine, a `PM-` symptom code and an
interval in hours. `pm_task` holds `last_done_at` and `registered_at` and
nothing else that configuration already says. A scan mirrors the configuration
into the table on every run, overwriting definitions and never touching
`last_done_at`; a task removed from `plant.yaml` is deleted, and the orders it
produced stay where they are.

**Why configuration.** An interval is a constant, and every constant in this
project needs a manual, a measurement or a recorded decision behind it. Put in a
table, it arrives by an `INSERT` nobody reviewed. Put in `plant.yaml`, it sits
under the comment that says which manual page it came from, beside the takt time
and the buffer map, in the file an operator is told to edit.

**Why a table as well.** "When was this last done" is something that happened.
It has to survive a config edit, and the health reader has to be able to ask for
it without loading the plant's file.

**`due_at` is not stored.** It is `last_done_at + interval`, or `registered_at`
when nothing has ever been recorded. #90 asked for the next occurrence to fall
out of the interval rather than out of a second column, because two columns that
must agree are two columns that will not.

### 2. One interval, from the one manual that states one

`fixtures/corpus/pages.py`, the R-2000iC maintenance manual, page 5: "Replace the
toothed belt at 8000 operating hours." The three R-2000iC machines in
`plant.yaml` get that task. The M-710iC gets none, because its manual states no
interval and an interval nobody wrote down is what this project refuses to
invent.

**8000 *operating* hours is read as 8000 hours of calendar time.** Calendar
hours are never fewer than operating hours, so the task falls due no later than
the manual asks, and being early is the safe direction for a belt.

**The assumption underneath that is worth stating, because nobody meets it in
the code.** A machine stopped for a week - broken, or idle on a quiet line -
still accrues calendar hours while its belt turns not at all. After a long
outage the task falls due earlier than the manual means, and the ticket is work
that may not be needed yet. The honest fix is an operating-hours counter, which
needs a signal nobody has agreed to send. Until then a technician can close the
order `no_problem_found`, which is recorded and does not advance the clock (§5),
and the interval stays as conservative as the manual's.

### 3. A scan on the round's cadence, on a chain of its own

`JobKind.PM_SCAN`, a handler in `worker-runtime` beside observe and dispatch,
booking its successor in its own transaction (ADR-044 §1). Its period is
`dispatch.round_seconds`, which is not a new constant: a ticket issued between
two rounds waits for the next round before anybody is sent, so scanning more
often buys nothing and scanning less often makes a task's first ticket later
than its interval says.

**A chain of its own rather than a step inside the dispatch round.** A scan that
fails inside the round's transaction rolls the round back, and one unpriceable
PM task would stop the plant being scheduled at all. The trigger loop and the
dispatch round are separate for the same reason.

**Issued at the due moment, with no lead window.** A window is a constant, and
this slice has no source for one. The due time has a source: the task's own
interval.

### 4. A task nobody has recorded is due from the day it was registered

**On a plant's first day, that means the whole schedule is due at once.** Nobody
knows when any of it was last done, and pretending otherwise would be inventing
dates. Three things carry the cost:

- **The load gate bounds it.** A scheduled order is `low` severity, and
  `dispatch/domain.py` withholds scheduled work unless the shift is light and
  keeps it under `light_below` even then. The tickets queue; they do not crowd
  out condition work.
- **Every one of them says so.** The reason reads "never recorded as done, so it
  has been due since it was registered", not a date nobody has.
- **The health reading says so too.** An overdue count whose lateness is
  measured from a registration is described that way, so "overdue by 3 days" is
  never read as "the plant is 3 days late".

The remedy for a real installation is importing last-done dates from the plant's
own records, which are in the CMMS ADR-070 found. That is not built, and it is
its own issue.

**The demo does not open on that screen**, and the dates that prevent it are
invented in `scripts/seed_demo_roster.py`, which is where invented facts go
(ADR-078 §1). `seed_demo.py`, the script an operator reruns on the plant's own
machine, writes no PM state at all.

### 5. One live order per task, and only `fixed` moves the clock

A partial unique index on `work_order (pm_task_ref)` over the five statuses a
shift has not finished - queued, proposed, assigned, in progress, handed over -
so a second live order cannot be written by the scan, a script or two workers at
once. **Skip, do not stack**: stacking is how a neglected machine pushes
`load_ratio` past the gate and holds back condition work, which is ADR-023's
argument arriving at the other origin. Skipping is not silent, because the task
stays overdue and the health screen counts it every day it stays that way.

**"Live" includes `proposed`.** A proposal a supervisor rejects returns to
`queued` (ADR-071), so at no point in that cycle is the task eligible again.

**Closing an order with outcome `fixed` sets `last_done_at` to the closing
moment, in the transaction that closed it.** The next occurrence follows from
the interval. `not_fixed`, `temporary_fix` and `no_problem_found` do not: the
first two are a job that did not happen, and the third says the technician found
nothing to do rather than that the procedure was carried out. The cost is a
ticket reappearing at the next scan, which is the right direction - the work is
still owed - and the new ticket's reason says when the task was last actually
done.

### 6. The health reader reads the table, and a zero still says which zero it is

`GET /overview/health` passes real tasks to `assess()`. The sentence ADR-081
wrote now has two forms: nothing registered anywhere, or nothing registered for
these machines. The second names them, because a machine with no PM task reading
"0 overdue" is the same empty-set claim at a smaller scale.

## What this does not do

- **`dispatch()` does not change, and neither does the simulator.** Layer 3
  receives a scheduled order through `open_orders` like any other and reads no
  `pm_task` row: everything it needs was copied onto the order when it was
  issued (ADR-041), which is what keeps invariant 10 true. No file under
  `dispatch/`, `sim/`, `baselines/` or `scripts/compare_policies.py` is touched
  by this slice, so `docs/results/reproducibility.md` still describes this tree:
  the 1,439 of 1,440 rows it reports were produced by code this slice leaves
  alone.
- **The simulator therefore models no PM work.** The comparison's quiet shifts
  absorb what the scenarios generate, which is condition work. A simulator that
  modelled the schedule would change every published figure, and that is a
  measurement decision rather than a slice.
- **No operating-hours counter**, so §2's assumption stands.
- **No lead window**, so a task's first ticket is issued at the due moment.
- **No import of last-done dates**, so a real installation starts with its whole
  schedule overdue (§4).
- **No screen for managing tasks.** `plant.yaml` is the interface, and an
  operator editing it is the path this slice supports.
- **No foreign key** from `work_order.pm_task_ref` to `pm_task`. An order
  outlives the schedule that produced it, as it outlives the layout it was
  created under (ADR-048).
- **PM tasks are not sent anywhere new.** They leave through the same adapter as
  every other ticket (ADR-012), and the confirmation gate applies to them
  unchanged (ADR-071).

## Consequences

- The third arrow in `CLAUDE.md`'s diagram is a live path. A quiet shift has
  lower-priority work to release for the first time outside a test.
- `pm_overdue` on the health screen is a reading rather than a default.
- **Every installation starts with every task overdue** until somebody records
  otherwise, and the system says that in two places rather than hiding it.
- A `needs_review` playbook for a PM symptom is served with its warning like any
  other (ADR-018); none exists in the corpus, so today every PM order is priced
  from `fallback_minutes` and carries `estimate_is_fallback`.
- The demo shows one overdue task and two mid-interval, from dates that do not
  exist, in the script that says so.

# ADR-041: A work order carries what the scheduler needs to schedule it

## Context

Layer 4 turns three sources of work into work orders. Before writing it, the
contract was read against what layer 3 will do with the result, and the same gap
ADR-030 found in a different place is here again.

**`load_ratio` is defined as `Σ (estimated_minutes × required_technicians) /
capacity`** (`design.md` 13.2), and it is the first thing the load gate computes.
**`dispatch()` must be a pure function of its inputs and must not touch the
database** (invariant 10). Its inputs are the work orders, the technicians and
shifts loaded before the call, and `config` (`design.md` 13.4).

Neither `estimated_minutes` nor `required_skill` is on `WorkOrder`. Both live on
the playbook, which the order references by id. So as the contract stands, layer
3 cannot compute the load gate at all without reading the playbook table -
inside a function that is required not to read anything.

This is the ADR-030 situation exactly: a rule about what may be imported, a
formula that needs a value on the other side of it, and a contract with nothing
in the middle. `design.md` 3.1 even describes the answer in its own diagram -
*"bind playbook + estimated_minutes + required_skill"* at creation - and the
field list in `CLAUDE.md` never grew the last two.

There is a second, smaller gap. `CLAUDE.md` requires the order's reason to read
differently for a detected and a predicted Finding - *"over threshold for 20
minutes"* against *"expected to reach threshold in about 6 hours, give or take
2"* - and the only text field on the order is `priority_reason`, which layer 3
overwrites with the ranking's explanation on the first tick.

## Decision

### 1. Four scheduling facts are copied onto the order when it is created

`estimated_minutes`, `required_skill`, `required_technicians`, and
`estimate_is_fallback`.

Copied, like `machine_id` and `severity` before them (ADR-030), and deliberately
a snapshot: an order priced at forty-five minutes stays priced at forty-five
minutes when the playbook is re-approved at sixty, because the shift was planned
on the first number.

### 2. `required_skill` is optional on the order, and `estimated_minutes` is not

An order with no playbook still has to be schedulable - that is the whole of
`design.md` 3.2, and the long-tail work that would otherwise vanish from the
system is the work the advisor asked to be released on a quiet shift.

- **The duration falls back** to `policy.yaml`'s `fallback_minutes[model][severity]`,
  and `estimate_is_fallback` says so, so nothing downstream mistakes it for a
  figure that came from a manual.
- **The skill does not fall back.** There is no honest default: guessing
  `robot_mechanical` for an electrical fault sends the wrong person, and a
  guess is worse than an absence because the absence is visible. `None` means
  "any technician", the ranking's skill term scores zero, and the screen says
  there are no prepared steps.

### 3. `reason` is why this job exists; `priority_reason` is why it is ranked here

Two fields, written by two layers, at two times.

`reason` is written at creation from the evidence and never changed. For a
detected Finding it says what crossed which threshold and for how long; for a
predicted one it says what is expected and when, **with the interval**, because
"in about 6 hours" and "in about 6 hours, give or take 2" are different
instructions to a person and the second one is the truth (`ui.md` 2.2).

`priority_reason` stays layer 3's, written on the tick that ranked it.

### 4. The snapshot is immutable in the database, not only in the code

A trigger that rejects any `UPDATE` changing `playbook_snapshot`,
`snapshot_approved_by` or `snapshot_approved_at`.

The contracts are frozen models, which stops the application editing them and
stops nothing else: a migration, a repair script or a future `repo.py` writing
`UPDATE work_order SET ...` all reach the row. `playbook_snapshot` is the only
evidence of what the system instructed on a job that has been closed for a year
(ADR-018), and invariant 2 asks for a database constraint rather than a
convention for that reason.

### 5. A PM order and a manual order are built by the same path

`PMTask.symptom_code` already carries the `PM-` prefix so layer 2 serves it
through the ordinary lookup (`design.md` 13.3). Layer 4 does the same: one
function, three origins, differing only in which reference is set and what the
reason says.

## Reasons

**The copy is what keeps layer 3 pure and layer 1 invisible to it.** It is the
same argument ADR-030 made, and the same answer: copy what is needed to where it
is needed, rather than letting the reader follow a reference back into a layer it
must not import.

**A fallback that is not labelled is worse than no fallback.** The estimate feeds
`load_ratio`, which decides how much work a shift is given. A coarse guess is
acceptable input; a coarse guess indistinguishable from a manual's figure means
nobody can ever tell how much of the schedule rests on guesses.

**Two reasons because two questions get asked.** A technician looks at a job and
asks why it exists; a supervisor looks at the queue and asks why that one is
first. One field answers whichever question was asked last.

## Consequences

- **`WorkOrder` grows four fields and one text field**, and `CLAUDE.md`'s
  contract list has to grow with it, since that file is the one loaded every
  session.
- **`estimated_minutes` is now on both the playbook and the order**, which the
  note at the end of `CLAUDE.md`'s contract section warns about for a different
  pair. It is the same relationship as `playbook_snapshot`: the playbook holds
  what is current, the order holds what was true when it was issued, and the
  order's copy is what the schedule was built on.
- **The immutability trigger applies to every writer, including migrations.**
  Changing a snapshot in future requires dropping the trigger, which is a visible
  act in a reviewed file rather than an `UPDATE` nobody notices.
- **Nothing here creates a work order from a Finding yet**, because layer 1 does
  not exist. The path is built and tested against Findings constructed in the
  tests, which is what `Finding` being a contract is for (`design.md` 3.3).

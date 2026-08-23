# Predictive maintenance with automatic work-order dispatch

## What this is

An Individual Study project: one student, one term, one person building it. The
problem comes from a vehicle assembly plant moving towards full automation, with
some lines already automated.

**The design rationale lives in [`docs/adr/`](docs/adr/README.md)** - 72 decision
records, append-only. Start with
[003](docs/adr/0003-no-llm-generated-repair-text-at-runtime.md),
[020](docs/adr/0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)
and [011](docs/adr/0011-load-ratio-switches-dispatch-behaviour.md), which carry
most of the system's shape.

Working notes - the plan, the schedule, the risk register, the conversation log
with the advisor - are kept in Thai in `docs-md/`, which is outside version
control on purpose. They are not needed to work on the code.

## The one goal everything is measured against

> By the end of term there must be a system a technician can open and actually
> work from, **even if sensor data from the plant never arrives.**

Anything that does not serve that sentence is future work. Two things follow, and
neither is allowed to become a fallback:

- **"A technician" has to be a real person.** Find one to try the system. This is
  ours to push for and does not depend on data arriving.
- **The written report is what is graded.** Weeks 13-14 are reserved for it in
  every case.

## Four layers

```
Three sources of work
 ├── machine signals (SignalSource) → layer 1 · Trigger    [works on synthetic data]
 │      detect:  rules and thresholds     → Finding (detected)
 │      predict: trend → time to threshold → Finding (predicted + ETA)
 ├── the PM schedule → lower-priority work (origin = scheduled)
 └── a technician or supervisor reporting it (origin = manual)
                    │
                    ▼
layer 2 · Content — assemble the ticket with steps from a playbook
        │                    ▲
        │                    └── playbook store (drafted from manuals with RAG)
        ▼
layer 3 · Dispatch — queue by priority against the shift's load
        │                    ▲
        │                    └── technician data (skills, shifts, open work)
        │      a round proposes; the shift lead confirms (ADR-071)
        ▼
layer 4 · Destination — where the ticket appears
        │      an existing CMMS, our own system, or a chat client
        ▼
     technician — accept, close, propose corrections → back into the playbook store
```

**Layers 2 and 3 must never block on layer 1.** Every layer is separately
buildable.

**Nothing reaches a technician that a person has not released.** A round writes
`proposed`; the shift lead confirms it into `assigned`, rejects it back to the
queue with a reason, or it expires back on its own. `dispatch.confirmation` in
`policy.yaml` switches this off once there is evidence to justify it, and the
evidence is the proposal record itself
([ADR-071](docs/adr/0071-a-round-proposes-and-a-person-decides.md)).

**Layer 1 is not waiting for real data.** The advisor opened with "monitor
**and predict**", so both have to be delivered. `SyntheticSource` models
degradation while knowing the true failure time, which gives prediction a
measurable ground truth without the plant
([ADR-020](docs/adr/0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)).

**Layer 4 carries the most risk**, because it is the only layer whose completion
depends on somebody outside this project. The advisor confirmed on 2026-08-23
that the plant already runs a work-order system, and asked for integration with
it *or at least somewhere the ticket is displayed*. So our own screens are the
floor that gets finished, the CMMS is the destination that gets prepared, and
tickets leave through a swappable adapter either way
([ADR-012](docs/adr/0012-tickets-leave-through-an-adapter.md),
[ADR-070](docs/adr/0070-the-plant-has-a-cmms-and-what-that-changes.md)).

## Principles that are not negotiable

1. **Runtime is deterministic.** No LLM writes repair instructions while a
   technician is waiting. A wrong torque value or lockout order is a risk to a
   person. The LLM works at build time, drafting for review
   ([ADR-003](docs/adr/0003-no-llm-generated-repair-text-at-runtime.md)).
2. **Every playbook is traceable.** Source document and page per step, plus
   revision, approver and approval time. Nothing reaches a technician unapproved,
   and a closed work order must be able to prove what it instructed, through its
   `playbook_snapshot`.
3. **Every ticket explains itself.** Why this job, why now. A system that cannot
   answer that gets overruled and then abandoned
   ([ADR-005](docs/adr/0005-every-ticket-carries-its-reason.md)).
4. **Nothing blocks on plant data.** Every part must be testable on synthetic
   data.
5. **When the evidence is thin, say so.** "Not found - see manual page X or ask
   an engineer" beats a guess.

## Data contracts

Eight in total, and **they have to be settled before anything else is written**,
because everything connects through them.

- **Four describing work** - below, because they are touched almost every time
  code is written: `Signal` → `Finding` → `Playbook` → `WorkOrder`
- **Four describing resources and places** - `Line`/`Station`, `Skill`,
  `Technician`/`Shift`, `PMTask`
  ([ADR-027](docs/adr/0027-operational-data-contracts.md)). Layer 3 uses all
  four; read that record before touching `dispatch/` or anything to do with load.

Two more things are not contracts but must exist before the first line of code:
the `Clock` port
([ADR-028](docs/adr/0028-clock-is-the-single-time-port.md)) and the import rules
with their CI gates
([ADR-030](docs/adr/0030-package-layout-io-boundary-and-self-contained-work-orders.md)).

### Signal
```
timestamp, machine_id, metric_name, value, unit
```
The same shape whether it came from the synthetic generator, a replay file or a
live OPC UA connection. `timestamp` is **source** time, not the clock the system
makes decisions on.

### Finding
```
machine_id, component, symptom_code, severity, evidence, detected_at,
kind, eta, eta_confidence,
rule_id, status, occurrence_count, last_seen_at, superseded_by
```
`evidence` records what triggered the alert - which value, how far past the
threshold, for how long - so it can be explained to a technician.

`status` is open / acknowledged / resolved / expired / superseded.

**A rule firing repeatedly updates the existing record; it does not create a new
one.** The suppression key is (`machine_id`, `rule_id`) while an open or
acknowledged record exists. A repeat firing raises `occurrence_count` and moves
`last_seen_at`.

Without this, one overheating motor raises a Finding on every reading, becomes a
hundred work orders, `load_ratio` passes 100%, and the gate holds back
everything - the system destroys itself in its first hour on real data
([ADR-023](docs/adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md)).

`kind` is **detected** (already past the threshold) or **predicted** (the trend
says it will be). A predicted Finding always carries `eta` and `eta_confidence`,
and the work order's reason must read differently in the two cases - "over
threshold for 20 minutes" against "expected to reach threshold in about 6 hours,
give or take 2" - because a technician decides differently. Predicted work is the
clearest example of what a quiet shift should absorb
([ADR-020](docs/adr/0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)).

`component` is **never inferred**. Each rule declares which component it watches;
one signal tag maps to one component. A rule that cannot say uses `unknown`, and
layer 2 then serves a fault-finding playbook rather than a repair one - which is
the honest answer to "which part"
([ADR-009](docs/adr/0009-component-comes-from-the-rule-not-from-inference.md)).

### Playbook
```
symptom_code, machine_model, steps[], tools[], parts[],
estimated_minutes, required_skill, required_technicians,
source_doc, page, revision, approved_by, approved_at, approver_role, status
```
```
steps[] each = { text, source_doc, page, confidence }
```
`status` is draft / approved / needs_review.

**One row per (`symptom_code`, `machine_model`).** No version chain, no
supersedes. Approval overwrites and increments `revision`. History lives in the
work order's `playbook_snapshot`
([ADR-018](docs/adr/0018-drop-the-version-chain-move-history-to-the-work-order.md)).

**Every step carries its own source**, not just the page as a whole. Authoring is
tuned for recall
([ADR-015](docs/adr/0015-recall-at-authoring-precision-at-runtime.md)), which
raises the chance of a draft mixing steps from two documents. At page level a
mixed playbook looks ordinary; at step level it reports itself.

When an operator replaces a manual, every playbook derived from it becomes
`needs_review` and is still served with a warning until re-approved.

`required_technicians` defaults to 1. A two-person job consumes twice the shift's
capacity; omitting it makes the load calculation read low and the gate release
more work than there are people for
([ADR-025](docs/adr/0025-work-orders-support-handover-and-multi-person-jobs.md)).

`approver_role` records the role held **at the moment of approval**, not the
person's current role. Roles change; the evidence must not
([ADR-024](docs/adr/0024-roles-and-approval-authority.md)).

### WorkOrder
```
origin, finding_ref?, pm_task_ref?, playbook_ref, playbook_snapshot, playbook_warning?,
machine_id, severity, finding_kind?, eta?, eta_confidence?,
estimated_minutes, required_skill?, required_technicians, estimate_is_fallback,
reason, priority_score, priority_reason, status,
assignees[], work_segments[], handover_note,
actual_minutes, blocked_minutes, blocked_reason, outcome, technician_feedback
```
```
assignees[]     = [{ user, role: primary | helper }]
work_segments[] = [{ user, started_at, ended_at }]
```
**The second line is the facts the scheduler needs, held by the order itself.**
The work module copies them on creation, and **dispatch never reads a Finding.**
Without this, dispatch cannot compute the station-level downtime term (which
needs `machine_id`) or the urgency term (which needs `eta`) without breaking its
own rule against importing the trigger layer. Same pattern as
`playbook_snapshot`: copy what is needed to where it is needed
([ADR-030](docs/adr/0030-package-layout-io-boundary-and-self-contained-work-orders.md)).

`severity` lives on the order rather than the Finding, because scheduled and
manual work have no Finding attached. On the other side, the load gate that
admits "high severity only" could not judge those two kinds of work at all.

**The third line is the same argument about the playbook.** `load_ratio` is the
sum of `estimated_minutes` x `required_technicians` over the shift's capacity,
and `dispatch()` may not read a table to find either (invariant 10), so both are
copied onto the order when it is created - a snapshot, so an order priced at
forty-five minutes stays priced at forty-five when the playbook is re-approved
at sixty. A job with no playbook takes its duration from `fallback_minutes` in
`policy.yaml` and says so through `estimate_is_fallback`; its `required_skill`
stays empty, because guessing one sends the wrong person and a guess is worse
than an absence
([ADR-041](docs/adr/0041-a-work-order-carries-what-the-scheduler-needs-to-schedule-it.md)).

`playbook_warning` is set when the playbook the order was built from was awaiting
review at that moment. ADR-018 serves such a playbook anyway, on the argument
that a technician with an out-of-date procedure is better off than one with
none - which holds only while they can tell which they have, and the ticket is
where somebody is standing at a machine.

`reason` is why the job exists and is written once, at creation - "over
threshold for 20 minutes", or "expected to reach threshold in about 6 hours,
give or take 2". `priority_reason` is why it is ranked where it is and belongs
to layer 3. Two questions get asked, by two people, and one field would answer
whichever was asked last (ADR-005, ADR-041).

`finding_ref` is for **tracing back**, not for the scheduler to fetch data. The
technician's screen showing "seen N times" reads through it, because the values
copied onto the order are a snapshot and are deliberately fixed.

`actual_minutes` is the **sum of the work segments, not close time minus start
time**, because a job can cross shifts, be set down and resumed, or involve
several people. `blocked_minutes` - waiting for parts, waiting for a line stop -
is subtracted before anything feeds back into estimates, or they inflate every
cycle
([ADR-025](docs/adr/0025-work-orders-support-handover-and-multi-person-jobs.md)).

`playbook_snapshot` is a frozen copy of the steps, their per-step provenance and
the approval, taken **when the order was issued**, and never editable.

**This is what makes dropping the version chain safe.** A closed work order must
prove what the system instructed. With history in the playbook table, overwriting
would leave old orders pointing at steps that are not what the technician did.
Moved to where it is actually needed, the playbook table can be overwritten
freely.

`origin` is condition (from a Finding) / scheduled (PM) / manual (reported).
`finding_ref` is therefore optional, because most lower-priority work - the work
the advisor asked to be released on a quiet shift - has no Finding
([ADR-010](docs/adr/0010-work-orders-have-an-origin.md)).

**Note:** `estimated_minutes` on the playbook and `actual_minutes` on the order
are separate by design. The first is what the scheduler computes with; the second
is reality, fed back to make the first more accurate. That is a feedback loop
requiring no machine learning at all.

## Technology

Reasoning in [ADR-008](docs/adr/0008-technology-stack.md). **No new dependency
without an ADR.**

- **Backend:** Python, FastAPI, PostgreSQL
- **Retrieval:** Qdrant (dense), PostgreSQL full-text (sparse), reciprocal rank
  fusion, cross-encoder reranking
- **Job queue:** a table in PostgreSQL (`FOR UPDATE SKIP LOCKED`, heartbeat,
  reaper). No Redis - a job and its result commit in one transaction, so there
  can be no playbook without a job or job without a playbook
  ([ADR-017](docs/adr/0017-postgres-is-the-job-queue.md))
- **Database access:** psycopg 3 with plain SQL, no ORM. Alembic versions the
  migrations and nothing more
  ([ADR-031](docs/adr/0031-plain-sql-against-postgres-no-orm.md))
- **Optimisation:** OR-Tools (CP-SAT)
- **Simulation:** SimPy or a discrete-event simulator written here
- **Frontend:** Next.js
- **Deployment:** Docker, on-premise only (plant documents are under NDA and must
  not go to the cloud). Seven containers, of which `api`, `worker-runtime` and
  `worker-authoring` come from one image, and `llm-server` sits on a network the
  API cannot reach
  ([ADR-026](docs/adr/0026-split-the-worker-into-two-roles.md),
  [ADR-029](docs/adr/0029-where-the-models-run.md))

## Background this builds on

The author has previously built and delivered an on-premise RAG system to a
factory, answering engineers' questions in Thai and English from robot manuals,
I/O mappings and scanned electrical drawings, running on edge hardware inside the
plant network. What carries over:

- Cross-lingual hybrid retrieval - questions in Thai, documents in English
- An entailment gate, self-verification and extractive fallback against
  fabrication
- Vision-language ingestion reading scanned drawings as device and connection
  tables
- **The experience of a predictive maintenance feature being cut for want of
  sensor data and failure labels** - the lesson that shaped this project's whole
  structure, and the reason
  [ADR-020](docs/adr/0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)
  exists

## Working language

- **Reply in Thai.** Keep technical terms in English.
- **All code, comments, commit messages and pull requests are in English.** The
  repository is the artefact that gets handed over; its history is part of what
  is delivered.
- Propose a plan before any substantial piece of work. Do not start editing
  files first.
- When an architectural decision is made, record it as a **new** record in
  `docs/adr/`. Never edit an existing one. Changing your mind means writing a new
  record that references the old.

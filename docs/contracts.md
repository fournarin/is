# Data contracts

Moved out of `CLAUDE.md` unchanged on 2026-09-27 (ADR-090), so that the file an
agent reads every session stays short. The four resource contracts are
[ADR-027](adr/0027-operational-data-contracts.md).


Eight in total, and **they have to be settled before anything else is written**,
because everything connects through them.

- **Four describing work** - below, because they are touched almost every time
  code is written: `Signal` → `Finding` → `Playbook` → `WorkOrder`
- **Four describing resources and places** - `Line`/`Station`, `Skill`,
  `Technician`/`Shift`, `PMTask`
  ([ADR-027](adr/0027-operational-data-contracts.md)). Layer 3 uses all
  four; read that record before touching `dispatch/` or anything to do with load.

Two more things are not contracts but must exist before the first line of code:
the `Clock` port
([ADR-028](adr/0028-clock-is-the-single-time-port.md)) and the import rules
with their CI gates
([ADR-030](adr/0030-package-layout-io-boundary-and-self-contained-work-orders.md)).

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
([ADR-023](adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md)).

`kind` is **detected** (already past the threshold) or **predicted** (the trend
says it will be). A predicted Finding always carries `eta` and `eta_confidence`,
and the work order's reason must read differently in the two cases - "over
threshold for 20 minutes" against "expected to reach threshold in about 6 hours,
give or take 2" - because a technician decides differently. Predicted work is the
clearest example of what a quiet shift should absorb
([ADR-020](adr/0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)).

`component` is **never inferred**. Each rule declares which component it watches;
one signal tag maps to one component. A rule that cannot say uses `unknown`, and
layer 2 then serves a fault-finding playbook rather than a repair one - which is
the honest answer to "which part"
([ADR-009](adr/0009-component-comes-from-the-rule-not-from-inference.md)).

### Playbook
```
symptom_code, machine_model, steps[], tools[], parts[],
estimated_minutes, required_skill, required_technicians,
source_doc, page, revision, approved_by, approved_at, approver_role, status
```
```
steps[] each = { text, text_th?, source_doc, page, confidence }
```
`status` is draft / approved / needs_review.

**One row per (`symptom_code`, `machine_model`).** No version chain, no
supersedes. Approval overwrites and increments `revision`. History lives in the
work order's `playbook_snapshot`
([ADR-018](adr/0018-drop-the-version-chain-move-history-to-the-work-order.md)).

`text_th` is the approving engineer's Thai for the step, with every figure
checked against `text` ([ADR-095](adr/0095-a-step-carries-the-approvers-thai.md)).

**Every step carries its own source**, not just the page as a whole. Authoring is
tuned for recall
([ADR-015](adr/0015-recall-at-authoring-precision-at-runtime.md)), which
raises the chance of a draft mixing steps from two documents. At page level a
mixed playbook looks ordinary; at step level it reports itself.

When an operator replaces a manual, every playbook derived from it becomes
`needs_review` and is still served with a warning until re-approved.

`required_technicians` defaults to 1. A two-person job consumes twice the shift's
capacity; omitting it makes the load calculation read low and the gate release
more work than there are people for
([ADR-025](adr/0025-work-orders-support-handover-and-multi-person-jobs.md)).

`approver_role` records the role held **at the moment of approval**, not the
person's current role. Roles change; the evidence must not
([ADR-024](adr/0024-roles-and-approval-authority.md)).

### WorkOrder
```
origin, finding_ref?, pm_task_ref?, playbook_ref, playbook_snapshot, playbook_warning?,
machine_id, severity, finding_kind?, eta?, eta_confidence?,
estimated_minutes, required_skill?, required_technicians, estimate_is_fallback,
reason, priority_score, priority_reason, status,
assignees[], work_segments[], handover_note,
actual_minutes, blocked_minutes, blocked_reason, outcome, technician_feedback,
reported_by?        (a manual order only, ADR-122)
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
([ADR-030](adr/0030-package-layout-io-boundary-and-self-contained-work-orders.md)).

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
([ADR-041](adr/0041-a-work-order-carries-what-the-scheduler-needs-to-schedule-it.md)).

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
([ADR-025](adr/0025-work-orders-support-handover-and-multi-person-jobs.md)).

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
([ADR-010](adr/0010-work-orders-have-an-origin.md)).

**Note:** `estimated_minutes` on the playbook and `actual_minutes` on the order
are separate by design. The first is what the scheduler computes with; the second
is reality, fed back to make the first more accurate. That is a feedback loop
requiring no machine learning at all.


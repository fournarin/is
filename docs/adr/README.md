# Architecture decision records

Seventy-seven decisions, in the order they were made. Each records the context that
forced it, the decision, the reasoning, and what followed. Read in order, they
are the design rationale for the system; read individually, each answers "why is
this part shaped this way".

**These are append-only.** An ADR is never edited after the fact. Changing your
mind means writing a new one that references the old, so the record shows what
was believed at the time rather than only what is believed now. Several later
entries replace parts of earlier ones, and both are kept.

| # | Decision | Superseded in part by |
|---|---|---|
| [001](0001-three-layers-buildable-in-parallel.md) | Three layers that can be built in parallel | 010, 012 |
| [002](0002-signalsource-interface-with-three-implementations.md) | `SignalSource` is an interface with three implementations | |
| [003](0003-no-llm-generated-repair-text-at-runtime.md) | **The LLM does not write repair instructions at runtime** | |
| [004](0004-rule-based-detection-before-machine-learning.md) | Start with rules, not machine learning | 020 |
| [005](0005-every-ticket-carries-its-reason.md) | Every ticket must carry a reason for its priority | |
| [006](0006-estimated-and-actual-minutes-are-separate.md) | Estimated and actual duration are separate fields | 025 |
| [007](0007-phase-one-targets-a-demo-the-advisor-can-negotiate-with.md) | Phase 1 aims at a demo the advisor can negotiate with | |
| [008](0008-technology-stack.md) | Technology stack, and the boundary around Redis | 017, 035 |
| [009](0009-component-comes-from-the-rule-not-from-inference.md) | Component comes from the rule, never from inference | 016 |
| [010](0010-work-orders-have-an-origin.md) | Work does not only come from a Finding | |
| [011](0011-load-ratio-switches-dispatch-behaviour.md) | Dispatch switches behaviour on load, not on score alone | 059, 071 |
| [012](0012-tickets-leave-through-an-adapter.md) | Tickets leave through an adapter interface | 070 |
| [013](0013-playbooks-are-immutable-versions.md) | A playbook version cannot be edited in place | 018 |
| [014](0014-report-and-technician-trial-are-reserved-unconditionally.md) | Reserve time for the report and the technician trial | |
| [015](0015-recall-at-authoring-precision-at-runtime.md) | Recall at authoring, precision at runtime | |
| [016](0016-component-is-a-config-label-not-a-database-entity.md) | Component is a configuration label, not an entity | |
| [017](0017-postgres-is-the-job-queue.md) | PostgreSQL is the job queue; no Redis | |
| [018](0018-drop-the-version-chain-move-history-to-the-work-order.md) | Drop the version chain; history moves to the work order | |
| [019](0019-content-addressed-document-storage-served-through-the-api.md) | Content-addressed storage, served through the API | |
| [020](0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md) | **Prediction by trend extrapolation, measured on synthetic data** | |
| [021](0021-downtime-cost-at-station-level-with-buffers.md) | Downtime cost per station and buffer, not per line | |
| [022](0022-every-improvement-loop-proposes-rather-than-changes.md) | Every improvement loop proposes; it does not change | |
| [023](0023-findings-have-a-lifecycle-and-a-suppression-window.md) | Findings have a lifecycle and a suppression window | |
| [024](0024-roles-and-approval-authority.md) | Roles and approval authority | |
| [025](0025-work-orders-support-handover-and-multi-person-jobs.md) | Shift handover and multi-person jobs | 056 |
| [026](0026-split-the-worker-into-two-roles.md) | Split the worker into runtime and authoring | |
| [027](0027-operational-data-contracts.md) | Operational contracts: station, technician, shift, PM task | |
| [028](0028-clock-is-the-single-time-port.md) | `Clock` is the single time port | |
| [029](0029-where-the-models-run.md) | Where the models run, and ADR-003 at the network layer | |
| [030](0030-package-layout-io-boundary-and-self-contained-work-orders.md) | Package layout, the I/O boundary, self-contained work orders | |
| [031](0031-plain-sql-against-postgres-no-orm.md) | Plain SQL against PostgreSQL, no ORM | |
| [032](0032-what-the-synthetic-source-guarantees.md) | What `SyntheticSource` guarantees, and what it cannot | |
| [033](0033-a-synthetic-manual-corpus-that-carries-its-own-answer-key.md) | A synthetic manual corpus, carrying its own answer key | |
| [034](0034-pdf-text-with-page-provenance-and-what-happens-when-there-is-none.md) | PDF text with page provenance, and pages that yield none | |
| [035](0035-embedding-in-process-vectors-in-qdrant-and-the-fusion-between.md) | Embedding in process, vectors in Qdrant, fusion on ranks | |
| [036](0036-sessions-in-the-database-behind-an-identity-adapter.md) | Sessions in the database, behind an identity adapter | |
| [037](0037-drafting-selects-spans-and-a-draft-is-withheld-whole.md) | Drafting selects spans; a failed draft is withheld whole | |
| [038](0038-the-review-queue-is-a-table-and-the-served-table-holds-no-drafts.md) | The review queue is a table; the served table holds no drafts | |
| [039](0039-what-a-worker-does-between-claiming-a-job-and-finishing-it.md) | What a worker does between claiming a job and finishing it | 040 |
| [040](0040-what-happens-when-somebody-asks-twice.md) | Asking twice, and a worker with no handlers | |
| [041](0041-a-work-order-carries-what-the-scheduler-needs-to-schedule-it.md) | A work order carries what the scheduler needs | |
| [042](0042-what-the-rule-engine-remembers-and-what-it-is-told.md) | What the rule engine remembers, and what it is told | |
| [043](0043-how-a-trend-becomes-a-prediction-and-what-its-interval-means.md) | How a trend becomes a prediction, and what its interval means | |
| [044](0044-the-trigger-loop-what-ticks-it-and-what-feeds-it.md) | The trigger loop: what ticks it, what feeds it, what it cancels | |
| [045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md) | The load gate, the score, and what a round may move | 049 |
| [046](0046-what-the-simulator-models-and-what-it-assumes.md) | What the simulator models, reads from config, and invents | 047 |
| [047](0047-a-policy-may-not-spend-minutes-the-shift-does-not-have.md) | A policy may not spend minutes the shift does not have | |
| [048](0048-a-work-order-outlives-the-layout-it-was-created-under.md) | A work order outlives the layout it was created under | |
| [049](0049-three-things-adr-045-left-ambiguous.md) | Three things ADR-045 left ambiguous | |
| [050](0050-the-gates-report-is-computed-when-asked.md) | The gate's report is computed when asked, not stored | |
| [051](0051-baselines-are-a-module-of-their-own.md) | The baselines are a module of their own | |
| [052](0052-what-review-was-protecting-and-what-it-was-not.md) | What review was protecting, and what it was not | |
| [053](0053-what-the-comparison-demonstrated-and-what-it-did-not.md) | What the comparison demonstrated, and what it did not | |
| [054](0054-what-cp-sat-optimises-and-what-it-may-not-touch.md) | What CP-SAT optimises, and what it may not touch | |
| [055](0055-the-counterfactual-is-a-re-solve-and-what-it-must-not-cancel.md) | The counterfactual is a re-solve, and what it must not cancel | |
| [056](0056-handing-over-ends-the-assignment.md) | Handing over ends the assignment | |
| [058](0058-what-the-web-layer-may-not-contain-and-how-it-reaches-the-api.md) | What the web layer may not contain, and how it reaches the API | |
| [059](0059-an-override-is-recorded-and-only-one-of-them-changes-a-round.md) | An override is recorded, and only one of the two changes a round | |
| [060](0060-how-the-authoring-queue-is-ordered.md) | How the authoring queue is ordered, and what counts as a gap | |
| [061](0061-what-the-technicians-screen-reads-and-from-where.md) | What the technician's screen reads, and from where | |
| [062](0062-what-the-offline-queue-promises-and-what-it-does-not.md) | What the offline queue promises, and what it does not | |
| [063](0063-what-the-line-overview-reads-and-what-it-may-not-compute.md) | What the line overview reads, and what it may not compute | |
| [064](0064-what-a-reviewer-may-change-and-what-the-review-screen-records.md) | What a reviewer may change, and what the review screen records | |
| [065](0065-how-this-web-layer-submits-things.md) | How this web layer submits things | |
| [066](0066-what-the-finished-jobs-may-change-and-what-stops-them.md) | What the finished jobs may change, and what stops them | |
| [067](0067-the-rehearsal-runs-inside-the-stack-it-rehearses.md) | The rehearsal runs inside the stack it rehearses | |
| [068](0068-a-ticket-that-was-dispatched-and-a-ticket-that-arrived.md) | A ticket that was dispatched and a ticket that arrived are two facts | 071 |
| [069](0069-the-destination-is-a-name-in-policy-and-a-path-in-the-environment.md) | The destination is a name in policy and a path in the environment | |
| [070](0070-the-plant-has-a-cmms-and-what-that-changes.md) | The plant has a CMMS, and our own system is the floor rather than the plan | |
| [071](0071-a-round-proposes-and-a-person-decides.md) | **A round proposes, and a person decides** | |
| [072](0072-machine-health-is-read-not-a-source-of-work.md) | Machine health is something read, and never a source of work | |
| [073](0073-what-a-false-alarm-may-propose-about-a-threshold.md) | What a false alarm may propose about a threshold, and what it may not | |
| [074](0074-the-cmms-contract-is-ours-and-what-the-third-destination-may-promise.md) | The CMMS contract is ours, and what the third destination may promise | |
| [075](0075-what-the-confirmation-record-may-be-read-to-say.md) | What the confirmation record may be read to say, and what it may not | |
| [076](0076-what-machine-health-is-computed-from-and-what-it-may-not-be-ranked-by.md) | What machine health is computed from, and what it may not be ranked by | |
| [077](0077-who-may-report-a-fault-and-what-a-second-report-means.md) | Who may report a fault, at what severity, and what a second report means | |

## Where to start

Three decisions carry most of the system's shape, and the rest follow from them:

- **[003](0003-no-llm-generated-repair-text-at-runtime.md)** - the LLM works
  before the job, not during it. This is the most expensive constraint in the
  design and the one everything else bends around. It is enforced twice, by an
  import rule and by a network boundary
  ([029](0029-where-the-models-run.md)).
- **[020](0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)** -
  how the system predicts without failure labels, and how that prediction is
  measured before any real data arrives.
- **[011](0011-load-ratio-switches-dispatch-behaviour.md)** - why scheduling has
  a gate and a score rather than one formula, which is what lets it explain
  itself in a sentence.

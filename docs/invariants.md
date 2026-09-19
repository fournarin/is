# The fifteen invariants

Fifteen properties that hold everywhere in this system, numbered. The decision
records cite them by number - `invariant 10` appears forty-one times in
`docs/adr/` and in the source - and `.github/workflows/ci.yml` names four of them
in the titles of the steps that enforce them.

**This page exists because the numbers were in the repository and the list was
not.** It lived in the Thai working notes, which `.gitignore` excludes on
purpose, so every citation in eighty decision records resolved to a file the
reader does not have. The numbering is the same; nothing here is renumbered.

## Why these and not others

Twenty-five decision records promise things that **fail silently** if they stop
being true. No error, no log entry, just behaviour drifting until one day the
principle is gone and nothing ever said so. A promise with no test is a promise
that dissolves within two months.

So each of these has something mechanical behind it. The **Enforced by** column
says what, and it is the part worth checking against the code rather than
trusting this page for.

## The list

| # | Invariant | From | Enforced by |
|---|---|---|---|
| 1 | No runtime module imports `llm/` | [ADR-003](adr/0003-no-llm-generated-repair-text-at-runtime.md) | `.importlinter`: *llm/ is importable from authoring/ only* |
| 2 | `playbook_snapshot` cannot be changed after it is written | [ADR-018](adr/0018-drop-the-version-chain-move-history-to-the-work-order.md) | a database trigger, `work_order_snapshot_is_frozen`, in `migrations/versions/0006_work_orders.py` |
| 3 | A draft is never served at runtime, not in any case, including when there is nothing else to give the technician | [ADR-013](adr/0013-playbooks-are-immutable-versions.md), [ADR-038](adr/0038-the-review-queue-is-a-table-and-the-served-table-holds-no-drafts.md) | `playbooks/repo.py` refuses to write a non-approved row at all, so the served table holds no draft to serve |
| 4 | Every step of an approved playbook carries `source_doc` and `page` | [ADR-015](adr/0015-recall-at-authoring-precision-at-runtime.md) | a validator in `playbooks/domain.py`, run wherever a playbook is approved from |
| 5 | The figures in a draft are a subset of the figures in the evidence it cites | lesson 3.1 | a gate in `authoring/drafting.py`; a step that fails it is withheld as `figure_not_in_evidence` |
| 6 | Only an engineer may approve, **checked at the endpoint** rather than by hiding a button | [ADR-024](adr/0024-roles-and-approval-authority.md) | `api/playbooks.py`, with the service refusing as well; tested by calling the endpoint as another role and requiring 403 |
| 7 | A rule naming a `component` label its machine model does not declare stops the configuration loading | [ADR-016](adr/0016-component-is-a-config-label-not-a-database-entity.md) | validation at boot, `platform/config/loader.py` |
| 8 | One rule firing repeatedly does not create a second Finding: one live record per (machine, rule), updated | [ADR-023](adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md) | `triggers/domain.py`; tested by firing a hundred times and requiring one record |
| 9 | A rule of **higher** severity is not suppressed while a repair is open | [ADR-023](adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md) | suppression is keyed by rule rather than by machine, so a different rule was never suppressed; `tests/triggers/test_rule_evaluation.py::TestSuppressionDuringRepair` |
| 10 | `dispatch()` returns the same answer for the same input and touches no database | design note 7 | `.importlinter`: *domain.py must not reach the database or a repo*; `contracts/` is frozen; `now` is an argument |
| 11 | No improvement loop may propose that a safety-linked threshold be loosened, however many false alarms it counted | [ADR-022](adr/0022-every-improvement-loop-proposes-rather-than-changes.md), [ADR-073](adr/0073-what-a-false-alarm-may-propose-about-a-threshold.md) | `work/thresholds.py` refuses and names `SAFETY_CRITICAL`; the flag is `safety_critical` in `rules.yaml` |
| 12 | `worker-runtime` cannot pick up an authoring job at all | [ADR-026](adr/0026-split-the-worker-into-two-roles.md) | a `job_class` filter in the claim query, `platform/jobs/repo.py`, rather than a convention |
| 13 | Every skill label a playbook or technician names is in the vocabulary, and every `machine_id` a rule names is in the topology | [ADR-027](adr/0027-operational-data-contracts.md) | validation at boot, `platform/config/loader.py` |
| 14 | No domain module reads the operating system clock | [ADR-028](adr/0028-clock-is-the-single-time-port.md) | `scripts/check_no_wall_clock.py` in CI |
| 15 | `api` cannot reach `llm-server` | [ADR-029](adr/0029-where-the-models-run.md) | `scripts/check_llm_isolation.py` reads the compose networks; the split itself is the enforcement |

## Four notes that are part of the design

**1 and 10 pay for themselves more than the rest.** Invariant 1 turns the most
expensive principle in the system into something that cannot be violated
structurally, rather than an agreement people keep. Invariant 10 is a
precondition for measuring anything at all: the simulator, the policy comparison
in `results/`, and replaying real decisions against alternative weights each need
`dispatch()` to answer the same way twice.

**15 is 1 at another layer.** Invariant 1 stops a runtime module reaching the
model through an import. Invariant 15 stops it reaching the model over HTTP,
which an import linter cannot see. ADR-003 is true only when both hold, and
either alone is a rule with a hole in it.

**14 is a precondition for 10.** A `dispatch()` that reads the system clock
inside itself answers differently on every run, however identical its inputs.

**Boot validation is one gate for two invariants.** 7 and 13 are both refusals at
configuration load, which is why CI names them together in a single step.

## Where a claim here should be checked

This page is a description of the system, and a description can go stale while
the thing it describes moves. Two habits keep it honest:

- **The Enforced by column is the part to verify.** Every entry names a file, a
  contract or a test. If one of them no longer says what this table says, the
  table is what is wrong.
- **A new invariant gets a number here and a record of its own.** The numbers are
  cited across eighty decision records and in CI step titles, so they are an
  interface rather than a list, and renumbering one would silently change what
  forty-one citations mean.

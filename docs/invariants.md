# The fifteen invariants

Fifteen properties that hold everywhere in this system, numbered. The decision
records cite them by number - `invariant 10` appears on 38 lines of `docs/adr/`
and `src/` - and `.github/workflows/ci.yml` names five of them (1, 7, 13, 14 and
15) in the titles of four steps.

**This page exists because the numbers were in the repository and the list was
not.** It lived in the Thai working notes, which `.gitignore` excludes on
purpose, so every citation in eighty decision records resolved to a file the
reader does not have. The numbering is the same; nothing here is renumbered.

## Why these and not others

Twenty-five decision records promise things that **fail silently** if they stop
being true. No error, no log entry, just behaviour drifting until one day the
principle is gone and nothing ever said so. A promise with no test is a promise
that dissolves within two months.

So each of these was meant to have something mechanical behind it. For two of
them that was not true when this page was written, and
[ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md)
supplied the missing mechanisms; one invariant still holds only because nothing
runs the code it constrains, and one is narrower than it used to read. See
[Known gaps](#known-gaps). The **Enforced by** column says what the code
actually does, and it is the part worth checking against the code rather than
trusting this page for.

## The list

| # | Invariant | From | Enforced by |
|---|---|---|---|
| 1 | No runtime module imports `llm/` | [ADR-003](adr/0003-no-llm-generated-repair-text-at-runtime.md) | `.importlinter`: *llm/ is importable from authoring/ only* |
| 2 | `playbook_snapshot` cannot be changed after it is written | [ADR-018](adr/0018-drop-the-version-chain-move-history-to-the-work-order.md) | a database trigger, `work_order_snapshot_is_frozen`, in `migrations/versions/0006_work_orders.py` |
| 3 | A draft is never served at runtime, not in any case, including when there is nothing else to give the technician | [ADR-013](adr/0013-playbooks-are-immutable-versions.md), [ADR-038](adr/0038-the-review-queue-is-a-table-and-the-served-table-holds-no-drafts.md) | `playbooks/repo.py::save_approved` refuses to write a non-approved row, and `CHECK (status IN ('approved', 'needs_review'))` on the table (`migrations/versions/0005_playbooks_and_the_review_queue.py`) refuses one whoever writes it, so the served table holds no draft to serve |
| 4 | Every step of an approved playbook carries `source_doc` and `page` | [ADR-015](adr/0015-recall-at-authoring-precision-at-runtime.md) | `PlaybookStep.source_doc` is `AttributedDocument`, which refuses an empty or whitespace-only value on every path including a draft (`contracts/work.py`, [ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md) §1); `page` is `Field(ge=1)`; and `Playbook._approved_playbooks_are_fully_attributed` checks that an approved playbook has steps, an approver, a time and an engineer's role. Migration 0014 stops an upgrade that would meet a stored step written before the rule (§2). Broken on purpose in `tests/contracts/test_work_contracts.py` and `tests/test_every_stored_step_names_its_document.py` |
| 5 | The figures in a draft are a subset of the figures in the evidence it cites | [lesson 3.1](from-the-working-notes.md) | `_check` in `authoring/drafting.py`; a step that fails it is recorded as `figure_not_in_evidence` and the **whole draft** is withheld, not only that step (ADR-037 section 4) |
| 6 | Only an engineer may approve, **checked at the endpoint** rather than by hiding a button | [ADR-024](adr/0024-roles-and-approval-authority.md) | `api/playbooks.py`, with the service refusing as well; tested by calling the endpoint as another role and requiring 403 |
| 7 | A rule naming a `component` label its machine model does not declare stops the configuration loading | [ADR-016](adr/0016-component-is-a-config-label-not-a-database-entity.md) | validation at boot, `platform/config/loader.py` |
| 8 | One rule firing repeatedly does not create a second Finding: one live record per (machine, rule), updated | [ADR-023](adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md) | `triggers/domain.py`, and a partial unique index, `one_live_finding_per_machine_and_rule` in `migrations/versions/0007_findings.py`, that refuses a second live Finding whoever writes it; tested by firing a hundred times and requiring one record |
| 9 | A rule of **higher** severity is not suppressed while a repair is open | [ADR-023](adr/0023-findings-have-a-lifecycle-and-a-suppression-window.md) | suppression is keyed by rule rather than by machine, so a different rule was never suppressed; `tests/triggers/test_rule_evaluation.py::TestSuppressionDuringRepair` |
| 10 | `dispatch()` - the runtime round, and **not** `schedule()`, the CP-SAT planner beside it - returns the same answer for the same input and touches no database | design note 7 | `.importlinter`: *domain.py must not reach the database or a repo*; `contracts/` is frozen; `now` is an argument. The planner's budget is wall-clock seconds and is outside the invariant, stated rather than fixed ([ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md) §6); see [Known gaps](#known-gaps) |
| 11 | No improvement loop may propose that a safety-linked threshold be loosened, however many false alarms it counted | [ADR-022](adr/0022-every-improvement-loop-proposes-rather-than-changes.md), [ADR-073](adr/0073-what-a-false-alarm-may-propose-about-a-threshold.md) | `work/thresholds.py::propose` refuses a rule marked safety-critical and names `SAFETY_CRITICAL`, tested at the function. **Nothing outside `tests/` calls `propose` yet**, so no code carries `safety_critical` from `rules.yaml` to it. See [Known gaps](#known-gaps) |
| 12 | `worker-runtime` cannot pick up an authoring job at all | [ADR-026](adr/0026-split-the-worker-into-two-roles.md) | a `job_class` filter in the claim query, `platform/jobs/repo.py`, rather than a convention |
| 13 | Every skill label a playbook or technician names is in the vocabulary, and every machine a rule can fire on is in the topology | [ADR-027](adr/0027-operational-data-contracts.md) | **Three mechanisms, none of them at boot** ([ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md) §§3-4). A playbook's skill is checked when it is drafted (`authoring/drafting.py`) and when it is approved (`playbooks/service.py`, which stands down when no vocabulary is configured). A technician's skills are checked where a technician is written: `dispatch/repo.py::add_technician` takes the vocabulary and raises `SkillNotInTheVocabulary`, broken on purpose in `tests/dispatch/test_a_technician_holds_a_skill_the_plant_declares.py`. The machine half is held by the shape of `plant.yaml` - a machine is declared inside a station and nowhere else - together with the loader refusing a rule whose model no machine uses; the boot check that could never fire is gone, and two tests in `tests/platform/test_config.py` stand in its place |
| 14 | No module outside `platform/clock.py` reads the operating system clock | [ADR-028](adr/0028-clock-is-the-single-time-port.md) | `scripts/check_no_wall_clock.py` in CI, which parses each module and resolves what `time` and `datetime` are bound to, so an aliased import is caught as well as a plain one ([ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md) §5). One test per form in `tests/test_the_wall_clock_check.py` |
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

**CI named 7 and 13 in one step, and the step held only 7.** Invariant 7 is a
refusal at configuration load. Invariant 13 was listed beside it on the
understanding that it was one too, and it is not. ADR-084 §§3-4 decided that it
should not become one - playbooks and technicians live in the database, and the
machine half is held by the shape of `plant.yaml` rather than by a check - so
the step title was corrected rather than the step. It now names invariant 7
alone, and invariant 13's three mechanisms are in the row above.

## Known gaps

**The first version of this page claimed that every Enforced by entry had been
checked against the code, and for rows 4 and 13 that was not true.** They named
mechanisms that do not enforce what the invariant says. The gaps were found on
19 September 2026, by opening the line each entry points to rather than only
confirming the named file exists. That happened before the page was first
pushed, but the finding went only into the description of #104, and #104
merged with the page unchanged. So for a while `main` carried the false rows.
The rows above now describe the code as it is. **Rows 4 and 13 were fixed in the
code by [#105](https://github.com/fournarin/is/issues/105), with
[ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md),
and each is now broken on purpose by a test.** The gaps they left are gone from
this list; what remains below is what is still true.

- **Invariant 11 holds because nothing runs the loop it constrains.** The
  refusal is real and tested. But neither improvement loop has a runtime path:
  `worker-runtime` registers only the dispatch and observe handlers, and no
  code outside `tests/` calls `propose()` in `work/estimates.py` or
  `work/thresholds.py`. When the caller is written, it has to pass
  `rule.safety_critical`. Until then, `scripts/check_config_is_read.py` counts
  `safety_critical` as read only because a parameter in `work/thresholds.py`
  has the same name, a limitation its docstring now states. The loops are
  [#107](https://github.com/fournarin/is/issues/107), and the gate is
  [#108](https://github.com/fournarin/is/issues/108).
- **Invariant 10 covers `dispatch()`, not `schedule()`.** The runtime round
  calls `dispatch()` only. The CP-SAT planner in `dispatch/solver.py`, which the
  explainer and `scripts/compare_policies.py` call, is outside the invariant.
  Its time budget is wall-clock seconds, which is why one row of the comparison
  changed between machines
  ([reproducibility](results/reproducibility.md), entry 28 of
  [decisions-to-defend](decisions-to-defend.md)). The first note above holds for
  the simulator's use of `dispatch()`, but it does not make the comparison
  byte-reproducible on its own.

## Where a claim here should be checked

This page is a description of the system, and a description can go stale while
the thing it describes moves. Two habits keep it honest:

- **The Enforced by column is the part to verify.** Every entry names a file, a
  contract or a test. If one of them no longer says what this table says, the
  table is what is wrong. **Reading is weaker evidence than breaking.** Of the
  fifteen, only invariant 4 was checked on 2026-09-19 by running something; the
  rest were read. ADR-084 added a test that breaks the rule on purpose for
  invariants 4, 13 and 14, so three rows now claim more than a reader's belief.
  [#108](https://github.com/fournarin/is/issues/108) asks for the other twelve.
- **A new invariant gets a number here and a record of its own.** The numbers are
  cited across eighty decision records and in CI step titles, so they are an
  interface rather than a list, and renumbering one would silently change what
  every citation of it means.

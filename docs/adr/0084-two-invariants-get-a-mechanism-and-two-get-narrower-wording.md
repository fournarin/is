# ADR-084: Two invariants get a mechanism, and two get wording that matches what holds them

Slice 19.2, from #105. Revisits [ADR-015](0015-recall-at-authoring-precision-at-runtime.md)
(invariant 4), [ADR-027](0027-operational-data-contracts.md) (invariant 13),
[ADR-028](0028-clock-is-the-single-time-port.md) (invariant 14) and
[ADR-045](0045-the-load-gate-the-score-and-what-a-round-is-allowed-to-move.md)
(invariant 10). It
changes none of their decisions. It supplies the enforcement two of them were
recorded as already having, and narrows two claims to what is actually true.

## Context

`docs/invariants.md` was written to bring the fifteen invariants into the
repository, because more than eighty decision records cite them by number and
the list itself lived in Thai working notes that `.gitignore` excludes. Its
first version said every **Enforced by** entry had been checked against the
code. On 2026-09-19 each entry was opened at the line it points to, and for two
rows the check had confirmed only that the named file existed:

- **Invariant 4** - *every step of an approved playbook carries `source_doc` and
  `page`*. `page` was enforced by `Field(ge=1)`. `source_doc` was a bare
  `NewType` over `str`, so `PlaybookStep(text=..., source_doc="", page=1, ...)`
  constructed without error, and so did an approved `Playbook` holding it.
- **Invariant 13** - *every skill label a playbook or technician names is in the
  vocabulary, and every machine a rule names is in the topology*. The page cited
  boot validation for both halves. A playbook's skill is checked at approval and
  at drafting, not at boot. A technician's skills were checked nowhere. The
  boot check for machines filled `station_of` and `machine_models` in the same
  loop from the same key, so its condition could never be true.

The same read found two claims that are not false but are wider than their
mechanism: invariant 14's gate is a regular expression that answers for five
spellings of a clock read, and invariant 10 covers `dispatch()` and not the
CP-SAT planner beside it.

[ADR-085](0085-what-the-unattended-loop-may-merge-and-a-check-that-can-stop-it.md)
§2 is why this is a record and not an edit: the correction to the page
([#106](https://github.com/fournarin/is/issues/106)) said what the code does,
and this one changes what the code does.

## Decision

### 1. Invariant 4 is enforced on the field, not on approval

`PlaybookStep.source_doc` and `Playbook.source_doc` become
`AttributedDocument`, a `DocumentId` with an `AfterValidator` that refuses an
empty or whitespace-only value.

**On the field rather than in `Playbook`'s approval validator**, so it holds on
every path into a playbook including a draft. A draft step with no source is
also wrong, and the drafter is the only thing that can still fix it: provenance
comes from the page the step was quoted from, and `playbooks/domain.py::apply_edits`
carries `source_doc`, `page` and `confidence` across a review unchanged
(ADR-064). By the time a reviewer sees an unattributed step, its source is not
theirs to supply - they would be inventing one, which is the failure ADR-015
exists to prevent, wearing the reviewer's authority.

**Rejected: a check at approval only.** It would make an approved playbook
sound and leave the review queue holding drafts nobody can complete, and the
review screen's own "cites another document" flag reads the same field.

### 2. Existing rows are proved rather than rewritten or excused

Steps are read back through `PlaybookStep.model_validate` in two places:
`work/repo.py::_to_order` for a `playbook_snapshot`, and `playbooks/repo.py` for
a served playbook. A stricter contract meeting a row written under the older one
would stop that work order loading at all.

Migration 0014 creates nothing and changes nothing. It runs two queries - over
`work_order.playbook_snapshot` and `playbook.steps` - and raises, naming the
rows, if any step cites no document. On a database this repository seeded, both
come back empty, and the upgrade is a no-op.

**Rejected: rewriting the offending rows.** Invariant 2 makes a snapshot
unchangeable, and for a reason: it is the only evidence of what a technician was
instructed to do. A migration that repaired one would be editing that evidence
at three in the morning on somebody's plant database.

**Rejected: a lenient read path.** "Accept a legacy row and say so" puts the
exception in the one place it is hardest to see and keeps it there for ever.
Stopping the upgrade asks a person once, at the moment the rule changes, which
is when the question is cheap.

The queries are module constants so that
`tests/test_every_stored_step_names_its_document.py` can run them against rows
written to fail them. What could be wrong about them is `jsonb` semantics -
`->>` on a missing key is NULL, and `NULL = ''` is not true - which is a
mistake only a real PostgreSQL can catch (ADR-031).

### 3. A technician's skills are checked where a technician is written

`dispatch/repo.py::add_technician` takes `known_skills` and raises
`SkillNotInTheVocabulary` for any label `plant.yaml` does not declare.

**`known_skills` has no default.** A default of `()` would make the check
skippable by forgetting, which is how it came to be missing. The one caller,
`scripts/seed_demo_roster.py`, passes `config.skills`.

**At the write, because that is where a vocabulary is in reach.** `contracts/`
cannot read configuration - invariant 10 keeps it frozen and free of I/O - and
by the time `dispatch()` runs, a wrong label is already in the table and looks
exactly like a technician who cannot do the work. That is the silent failure:
`can_perform` never matches, the person is passed over by every round, and
nothing anywhere says why. Nobody reports being quietly left off the roster.

**An empty vocabulary refuses every label**, deliberately unlike
`PlaybookStore`, whose check begins `if self.skills and ...` and stands down
when no vocabulary is configured. The two are not inconsistent by accident:
`PlaybookStore` is constructed with a vocabulary by `api/app.py` and without one
in tests that are about approval rather than about skills, while
`add_technician` has one caller which already refuses to write a roster for a
plant that declares no skills. A technician holding no labels at all is still
written: an apprentice is a person the roster carries, not a vocabulary error.

**Where the playbook half runs, and why it is not moved to boot.** Playbooks
live in the database, so "at boot" would mean scanning the table on startup and
refusing to start over a row somebody approved months ago, possibly under a
vocabulary since edited. The check stays at the two moments a skill is chosen -
drafting (`authoring/drafting.py::_skill_from`) and approval
(`playbooks/service.py`) - and `docs/invariants.md` now says so rather than
saying "at boot".

### 4. The machine check is deleted, because no check there can fire

The loader's *"can raise Findings but sits at no station"* check is removed.

**What it was meant to catch** is a machine a rule can fire on whose downtime
cost the w2 term cannot compute, for want of a station. **Why nothing can catch
it there**: `station_of` and `machine_models` are filled in the same loop from
the same key, so a machine in one is in the other, and the property is not a
cross-file consistency question at all. It is held by the shape of `plant.yaml`,
where a machine is declared inside a station and cannot be declared anywhere
else. The half that *can* go wrong - a rule naming a model no machine uses - is
refused a few lines above and always was.

**Rejected: a replacement that can fire.** There is no loadable configuration
that violates the property, so any replacement would be a second line that reads
like enforcement and enforces nothing. Two tests in
`tests/platform/test_config.py` take its place: one that a machine declared
outside a station is refused, and one that every machine in the shipped layout
resolves to its station.

### 5. Invariant 14's gate reads the syntax tree

`scripts/check_no_wall_clock.py` is rewritten to parse each module, resolve what
`time` and `datetime` are bound to, and flag calls that resolve to a clock read.
It answers for `datetime.today()`, `time.time_ns()`, `time.monotonic_ns()` and
`from datetime import datetime as dt` followed by `dt.now()` - none of which the
regular expression matched, and none of which appear in `src/` today.

**Rejected: a wider regular expression.** It closes the four known holes and not
the class of hole. An aliased import cannot be matched by text at all without
re-implementing name resolution badly.

A module that will not parse is reported rather than skipped: a gate that goes
quiet on a file it cannot read passes for the wrong reason, which is the defect
this whole record is about. The escape hatch is unchanged, except that on a call
spread over several lines the comment may sit on any of them.

### 6. Invariant 10 is narrowed to say `dispatch()`, not the planner

The invariant's wording now states that it covers the runtime round's
`dispatch()` and not `schedule()`, the CP-SAT planner in `dispatch/solver.py`
that the explainer and `scripts/compare_policies.py` call.

**Why narrowed rather than fixed.** The fix is known and named in entry 28 of
`docs/decisions-to-defend.md`: `max_deterministic_time` bounds search work
rather than seconds. Adopting it needs a budget in deterministic units, and this
project's rule is that every constant has a manual, a measurement or a recorded
decision behind it. Converting 5.0 seconds into that unit is a measurement
nobody has made, and making one is a slice of its own - it re-runs the 1,440-row
sweep in `docs/results/` and may move the one figure that already moves.

A wording that overstates is worse than a narrow one: a reader who believes the
comparison is reproducible because invariant 10 says so has no reason to read
`docs/results/reproducibility.md`, which says the opposite about one cell.

## Consequences

- An unattributed step is refused everywhere, and `alembic upgrade head` on an
  existing database will stop rather than proceed if one is stored. That is a
  deployment step that can fail, on purpose.
- Anything that writes technicians must now hold the vocabulary. There is one
  such caller today; an API for roster administration (entry 29) inherits the
  requirement rather than rediscovering it.
- The CI step titled *"configuration must be loadable (invariants 7 and 13)"*
  now names invariant 7 only. Invariant 13 is not a boot check and this record
  decides it should not become one.
- `docs/invariants.md` rows 4, 10, 13 and 14 name the mechanism as it now is,
  and three of the five entries under **Known gaps** are gone. The two that
  remain are invariant 11 (#107) and the planner's wall-clock budget (entry 28).
- Invariant 4 is now proved by a test that breaks it on purpose, as are 13's
  technician half and 14's gate. That is three of the fifteen rows
  [#108](https://github.com/fournarin/is/issues/108) asks for, done where the
  fix was.

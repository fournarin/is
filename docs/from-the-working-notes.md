# From the working notes

Three sections of the Thai working notes that the code depends on, translated
and brought into the repository with their original numbers. The notes live in
`docs-md/`, which `.gitignore` excludes on purpose. That is fine for the plan
and the conversation with the advisor. It is not fine for a section that
`config/` gives as the provenance of a constant, or that the invariants page
gives as the source of a rule, because a reader with only this checkout cannot
open either.

**The numbering is the original's.** A citation of `design.md 6.2` anywhere in
the repository, including in records that cannot be edited, means the section
below with that number. Every other `docs-md/` citation still points outside,
and should be read as provenance rather than a link, as `CLAUDE.md` says.

Why these three and not the rest: on 2026-09-19 `design.md` was cited on 121
lines across 70 files. §6.2 (24 lines) is the stated provenance of
`round_seconds: 300` in `config/policy.yaml`, which broke the project's own rule
that every constant has a source in the repository. §13.2 (17 lines) defines
the unit of the load gate at the centre of ADR-011. Lesson 3.1 is the **From**
of invariant 5 in [`invariants.md`](invariants.md). Each was a link from inside
the repository to somewhere a cold clone cannot follow.

These are translations of the text as it stood on 2026-09-19. If the original
changes, this page does not change with it. It records what the repository
was built against.

---

## design.md 6.2: The scheduler works in rounds, not on every event

Rounds of roughly five minutes, and **a job a technician has accepted is not
moved** unless something above the severity threshold arrives.

**Why:** if the queue is re-optimised every time a new Finding arrives, a
technician's queue shifts all the time. A technician who sees the order of
their jobs change while walking to a machine will stop trusting the system
within a week. Stability is worth more than a marginally more optimal answer.
This is ADR-005 in practice.

*Where it is cited:* `dispatch.round_seconds` in `config/policy.yaml`, whose
provenance note names this section; `dispatch/domain.py`, `dispatch/repo.py`,
`work/service.py`, the simulator and the `dispatch.round_seconds` schema;
ADR-042, ADR-045, ADR-049, ADR-054 and ADR-071; `decisions-to-defend.md`
entries 4 and 15.

---

## design.md 13.2: The unit of `load_ratio` is person-minutes, above and below the line

```text
capacity  = Σ available_minutes of the ShiftAssignments in the shift
open work = Σ (estimated_minutes × required_technicians)      ← ADR-025
```

ADR-025 already says that without multiplying by `required_technicians` the
figure reads low, but it never stated the unit of the denominator. If the two
sides are not in the same unit, the load gate is wrong all the time and nothing
reports it.

*Where it is cited:* `dispatch/domain.py`, `contracts/work.py`,
`contracts/resources.py`, `work/repo.py`, the simulator,
`migrations/versions/0006_work_orders.py` and
`0008_technicians_and_shift_assignments.py`, and ADR-045 and ADR-050.

---

## lessons_carried.md 3.1: Numeric grounding

The figures in an answer must be **a subset of the figures in the source
context**. If the model produces a figure that is not in the document, reject
that answer.

It is the mechanism closest to the fear behind ADR-003: a wrong torque value is
a risk to a person, and it is the kind of safeguard that is hard to think of
without having met the problem for real.

**In this project:** used as a gate at authoring time, before a draft enters
the review queue.

*Where it is cited:* invariant 5, enforced by `_check` in
`authoring/drafting.py`, whose docstring defines the gate by way of ADR-037
section 2.

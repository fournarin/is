# Decisions to defend

Every choice in this repository that somebody will have to justify - in the
report, or standing in front of it. Four lines each: what was decided, why, what
changes if it is wrong, and where to look.

**This file is the review** (ADR-052). An agent may merge a `human-review` slice
once its decisions are here; two things still stop and wait for a person, both
listed at the bottom.

Newest last. If you have ten minutes before writing a chapter, read this file.

---

## 1. The skill-match term asks the shift, not the clock

**Decided.** `_skill_match` is 1 when anybody rostered and active holds the
skill, whether or not they have a minute left. ADR-045 §1's table says "free"
and the code does not implement that word.

**Why.** Availability is already answered twice - `_assign` will not place work
on somebody without the minutes, and the round reports it as `unassigned`. A
score that moved with people's free minutes would also re-rank the queue every
time somebody finished a job, under a technician already walking to a machine.

**If it is wrong.** Work whose only qualified technician is booked solid ranks
higher than it should, so it sits at the top of a list nobody can act on. The
fix is a new term rather than a change to this one.

**Look at.** [ADR-049 §1](adr/0049-three-things-adr-045-left-ambiguous.md),
`dispatch/domain.py::_skill_match`.

---

## 2. A ticket for a machine the layout forgot is still scheduled

**Decided.** A work order naming a machine no longer in `plant.yaml` is
scheduled with a downtime term of zero, and both the ticket and the round say
so. It is not withheld.

**Why.** Withholding makes the configuration error loud by leaving a real fault
on a real machine until somebody edits a YAML file. The machine did not stop
being broken because the file is stale. The round's summary carries the count
instead, so the drift stays visible without work being parked.

**If it is wrong.** A stale layout produces work that is systematically
under-ranked and nothing forces anybody to fix the file. The counter-argument -
refuse the work, make somebody fix config - is in the record.

**Look at.**
[ADR-048](adr/0048-a-work-order-outlives-the-layout-it-was-created-under.md),
`dispatch/domain.py::_downtime_or_unknown`.

---

## 3. The gate's report is computed when asked, not stored

**Decided.** "What is being held" is answered by re-running `dispatch()` on the
current queue. No table of past rounds.

**Why.** One implementation produces both the decision and the explanation, so
they cannot drift; nothing accumulates, so no retention policy is needed; and
the question is about the queue in front of somebody now.

**If it is wrong.** There is no answer to "why was this held at 14:05", and
there will not be one until rounds are recorded. If that turns out to be the
question people actually ask, this is the record to overturn.

**Look at.** [ADR-050](adr/0050-the-gates-report-is-computed-when-asked.md),
`api/dispatch.py`.

---

## 4. A dispatch round runs every five minutes

**Decided.** `dispatch.round_seconds: 300` in `policy.yaml`.

**Why.** design.md 6.2 sets the cadence and the simulator's scenarios already
run at it, so slice 7.3 measures the clock the plant would use. The trade is
stated in the file: longer and a critical fault waits for the next round,
shorter and the queue re-ranks often enough that technicians stop reading it.

**If it is wrong.** Every response-time figure in the report moves. Nothing
else does - the number is read from config in one place.

**Look at.** `config/policy.yaml`, the `dispatch:` block.

---

## 5. The baselines are a module of their own

**Decided.** `pdm/baselines/` rather than `pdm/sim/baselines.py`, with an import
rule forbidding them from seeing `pdm.dispatch` or a database.

**Why.** The simulator is the measuring instrument; a baseline is a subject of
the measurement. One subject inside the instrument while the other two are
outside it is an asymmetry that has to be explained every time somebody asks
why `dispatch()` is not in there too.

**If it is wrong.** Nothing breaks; it is a naming and layout choice. The cost
already paid is a row in design.md §2's module table, **which still needs adding
by hand** - `docs-md/` is outside this checkout on purpose.

**Look at.** [ADR-051](adr/0051-baselines-are-a-module-of-their-own.md).

---

## 6. The priority matrix takes its table from the caller

**Decided.** `PriorityMatrix(importance_of=...)`, defaulting to every machine
equally important. No line-importance figure in `plant.yaml`.

**Why.** The matrix is the plant's own document - a laminated sheet on an office
wall - not a fact about the plant. A number for it in configuration would look
measured.

**If it is wrong.** The whole 3B column of the comparison changes, because with
one line the default collapses the matrix to severity ordering. If the plant
supplies a real sheet, the baseline should use it and the table should be
rerun.

**Look at.** `baselines/policies.py::PriorityMatrix`, `docs/results/`.

---

## 7. The comparison says the gate does not win on production lost

**Decided.** Nothing. The result is reported as it came out, and
`docs/results/README.md` offers two explanations without choosing between them.

**Why.** 3C reaches a machine in about half the time first-come-first-served
takes, and first-come-first-served still loses about one percent less
production, consistently across six buffer settings and three arrival rates. The
issue forbids tuning the weights to fix it, and `policy.yaml` says they are
starting values.

**If it is wrong.** The two candidate explanations point in different
directions. If it is the second one - the gate holding medium-severity work
while a technician is free, because `load_ratio` counts everything open as
committed rather than everything in flight - **that is a finding about ADR-011
and it changes the design, not the table.** It is the first thing to check.

**Look at.** `docs/results/README.md`, `docs/results/comparison.csv`,
`dispatch/domain.py::committed`.

---

## 8. The dispatch adapter takes one placement per technician per round

**Decided.** In the comparison harness, each technician's highest-ranked
placement starts and the rest wait for the next round.

**Why.** `dispatch()` answers "who is this job assigned to", and a person with
eight hours left can be assigned four two-hour jobs - a queue in front of a
person, which is correct. The simulator asks who *starts now*, and nobody starts
two machines at once.

**If it is wrong.** It would systematically disadvantage 3C in the comparison,
which is the number this project is judged on. The five-minute cadence is what
makes the delay small; a longer cadence would make this choice matter more.

**Look at.** `scripts/compare_policies.py::GateAndScore._starting_now`.

---

# What still stops and waits for a person

Two things, per [ADR-052](adr/0052-what-review-was-protecting-and-what-it-was-not.md).
A slice hitting either is labelled `blocked`, with the question in the issue.

1. **A number standing in for a measurement**, where no manual, no measurement
   made here, and no recorded decision supports it. Writing it down does not
   make it defensible; somebody has to decide whether the project will publish a
   result that rests on it.
2. **A safety-linked threshold.** ADR-022 forbids any loop from proposing one be
   loosened, and an agent proposing it in a slice is the same act under a
   different name.

Currently open: none.

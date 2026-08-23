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

## 9. A reviewer's edit is not put through the figure gate

**Decided.** "Edit and approve" lets an engineer reword a drafted step, and the
figure check of ADR-037 §2 - every number in a step must appear in the chunk it
cites - is not re-run over what they wrote. Their citation, step count and
ordering are fixed; only the words are theirs.

**Why.** The gate exists to stop a model quoting a torque the page does not
carry. The engineer is the authority ADR-003 put in the model's way, and
refusing their correction on the strength of the model's check makes the
reviewer the least-trusted party in the system. What replaces it is
attribution: the diff is stored on the proposal, the approval names the person
and the role held at that moment, and the work order snapshots the lot.

**If it is wrong.** An engineer can approve a figure no manual states, and the
system will serve it with a provenance that says a person wrote it rather than
that the manual did. The fix is a check at the edit, not a rollback: the
distinction is already recorded per step.

**Look at.** [ADR-064 §2](adr/0064-what-a-reviewer-may-change-and-what-the-review-screen-records.md),
`src/pdm/playbooks/domain.py::apply_edits`, `tests/playbooks/test_what_a_reviewer_may_change.py`.

---

## 10. Review time is the last sitting, not the whole span

**Decided.** `review_seconds` is measured from the most recent open of a
proposal's detail to the decision, both from the Clock. Reopening resets the
start. Null when the detail was never opened.

**Why.** The report quotes minutes-per-proposal, and a proposal opened on Monday
and decided on Thursday is not a three-day review - it is a two-minute one after
a gap. Measuring first-open-to-decision would put days in the same column as
minutes and make the median meaningless. A timer in the browser was the other
option and is worse twice over: the number would be the screen's word for it,
and a visible clock pressures somebody reading safety-critical text.

**If it is wrong.** The figure under-reports: a reviewer who leaves the detail
open, reads the manual for ten minutes and comes back is measured from the last
load. It is a floor on how long review took, and it should be reported as one.

**Look at.** [ADR-064 §4](adr/0064-what-a-reviewer-may-change-and-what-the-review-screen-records.md),
`src/pdm/playbooks/repo.py::decide`,
`tests/api/test_the_review_screen.py::TestTheTimeIsRecordedAndNeverShown`.

---

## 11. The duration loop declines the exception ADR-022 gave it

**Decided.** Loop 1 proposes a new `estimated_minutes` and writes nothing, even
though ADR-022 explicitly allows this one loop to adjust itself within plus or
minus twenty percent per cycle. The bound is kept as a cap on the proposal.

**Why.** ADR-022's argument is about safety and the accountability argument
points the other way: the estimate is what `load_ratio` is computed from,
`load_ratio` decides which work the gate releases, and the release decision is
the one the advisor asked for by name. A figure that moves on its own is one
nobody can explain in the week somebody asks why the shift filled up - and
applying the proposal is the cheap half anyway.

**If it is wrong.** Estimates stay stale until a screen exists to approve the
proposals, so the loop is a mechanism rather than a loop that turns, and the
report has to say so. Reversing it is one `UPDATE` behind an approval.

**Look at.** [ADR-066 §1](adr/0066-what-the-finished-jobs-may-change-and-what-stops-them.md),
`src/pdm/work/estimates.py::propose`,
`tests/work/test_what_the_finished_jobs_say.py::TestNothingHereWrites`.

---

## 12. Five closed jobs is the floor, and it is an argument rather than a measurement

**Decided.** `estimates.min_observations` is 5 in `policy.yaml`, with ADR-066 as
its provenance. Below it the loop proposes nothing.

**Why.** Five is the smallest count that leaves two observations either side of
the median, so one unusual morning cannot be the middle. There is no manual and
no measurement of this plant to appeal to; the alternative was to invent a
number quietly, which this project treats as the same defect as an unapproved
playbook.

**If it is wrong.** Too low and one bad week reprices a symptom; too high and
the loop never says anything at all for the long-tail work that closes twice a
year. The failure is silent in both directions, which is why it is here.

**Look at.** [ADR-066 §4](adr/0066-what-the-finished-jobs-may-change-and-what-stops-them.md),
`config/policy.yaml::estimates`,
`tests/work/test_what_the_finished_jobs_say.py::TestWhatIsNotEvidence`.

---

## 13. A refused ticket is retried for ever, with no attempt cap

**Decided.** Delivery to layer 4 is at-least-once with the state stored in
`ticket_delivery`. A destination that refuses a ticket leaves the order placed
and the row outstanding, `attempts` climbs, and nothing ever gives up on it.

**Why.** A cap means choosing how many failures are acceptable before a machine
goes unattended, and there is no number that answers that. The alternative -
fire-and-forget - makes an undeliverable ticket indistinguishable from a
delivered one, and the person who finds out is the technician who was never sent
the job.

**If it is wrong.** A destination that is misconfigured rather than merely down
produces a row that retries every round for ever, and nothing on any screen says
so yet. The failure is quiet in the wrong direction: the system looks busy and a
ticket is going nowhere. The fix is a panel on the overview (ADR-063), not a cap.

**Look at.** [ADR-068 §4](adr/0068-a-ticket-that-was-dispatched-and-a-ticket-that-arrived.md),
`src/pdm/sinks/service.py`,
`tests/sinks/test_a_destination_that_says_no.py::TestARefusedTicketComesBackNextRound`.

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

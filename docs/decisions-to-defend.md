# Decisions to defend

Every choice in this repository that somebody will have to justify - in the
report, or standing in front of it. Four lines each: what was decided, why, what
changes if it is wrong, and where to look.

**This file is the review** (ADR-052). A `human-review` pull request has its
decisions written here before a person merges it. The unattended loop does not
merge `human-review` work itself (ADR-085, which narrows ADR-052), and two
things stop a slice entirely. Both are listed at the bottom.

Newest last. If you have ten minutes before writing a chapter, read this file.

The last section is different: six questions with no answer yet, kept here for
the same reason as the rest. **The numbers jump at that boundary**, because they
run in the order entries were written and the two sections have filled up at
different times: decisions run 1 to 26 and then 33 to 40, and the open questions
are 27 to 32. A number is never reused, because entries are cited by it.

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

**Why.** design.md 6.2 ([in the repository](from-the-working-notes.md)) sets
the cadence and the simulator's scenarios already run at it, so slice 7.3
measures the clock the plant would use. The trade is
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

## 14. The destination is configuration; where it writes is not

**Decided.** `policy.yaml` names the destination and holds no path. Where the
`file` sink writes comes from `TICKET_DIR` in the environment, with no default,
and `file` configured without it is a startup failure.

**Why.** Which destination a site sends tickets to is a decision about how that
plant works and belongs beside the load thresholds an operator reads. A host
path is a fact about the machine the container runs on. Keeping them apart is
what lets `policy.yaml` stay free of paths, and it is why the same config file
can be read on a laptop and in the plant.

**If it is wrong.** It is two places to look instead of one, and somebody
configuring `file` for the first time meets an error rather than a working
default. That is the intended trade - a guessed directory is a worker that
starts healthy and writes tickets where nobody looks - but it is a real cost to
whoever installs this, and the error message is the whole mitigation.

**Look at.** [ADR-069 §1](adr/0069-the-destination-is-a-name-in-policy-and-a-path-in-the-environment.md),
`config/policy.yaml::sinks`, `src/pdm/sinks/registry.py`,
`tests/sinks/test_a_second_destination.py::TestAnUnknownDestinationStopsTheProcess`.

## 15. The technician's screen was reading an opinion, not a fact

**Decided.** `GET /work-orders/mine` reads the orders a person actually holds.
The screen used to filter `round.placed` from `/dispatch/round`, which computes
what a round *would* decide - and `dispatch()` places only work that is still
`queued`, so a job left that list at the instant a round wrote it.

**Why.** Work somebody has to act on must be read from what was written down. A
recomputed round is the right answer to "what is the gate holding" (ADR-050) and
the wrong one to "what is mine", and the two agreed only while no round had
committed.

**If it is wrong.** The ranking a technician sees is now a snapshot, frozen at
placement, so a shift that changes underneath them does not re-order their
queue. That is design.md 6.2 and it is deliberate, but it means a job whose
urgency has moved keeps the rank it was given - the next round cannot fix it,
because a round does not touch work somebody holds (ADR-045 §4).

**Look at.** [ADR-071 §7](adr/0071-a-round-proposes-and-a-person-decides.md),
`src/pdm/work/repo.py::assigned_to`,
`tests/dispatch/test_the_confirmation_gate.py::TestTheJobStaysOnTheScreenAfterARound`.
The defect survived three screen checks because `scripts/rehearse.py` stops
`worker-runtime` while they run.

## 16. A supervisor confirms every placement, and the switch off it has no threshold

**Decided.** `dispatch.confirmation: supervisor` is the shipped default. A round
writes `proposed`, a shift lead confirms or rejects with a reason, and an
unanswered proposal returns to the queue after `proposal_expires_minutes`.
`automatic` is the other supported mode and writes `assigned` as before.

**Why.** The advisor was asked on 2026-08-23 who presses the button and answered
that a person should at first, with automatic approval as something to consider
later "once there is a record to judge it by". The record is
`dispatch_proposal`: what the scheduler said, what the shift lead said, how long
they took, and how much nobody answered.

**If it is wrong.** The confirmation step is a person in the path of every
ticket, and a shift lead who does not reach the screen is a queue that stops
moving - the expiry sweep bounds the damage but does not remove it. The
mitigation is that the mode is one line of configuration and the code path is
shared, so a plant that finds it intolerable changes a word.

**No threshold is written down for when to switch**, and that is the decision
rather than an omission: a number deciding when a plant may stop reviewing its
own work orders is not one this project may invent before it has measured
anything.

**Look at.** [ADR-071](adr/0071-a-round-proposes-and-a-person-decides.md),
`config/policy.yaml::dispatch`, `src/pdm/dispatch/service.py::Confirmations`,
`tests/dispatch/test_the_confirmation_gate.py`.

## 17. A rejected proposal is proposed again, on purpose

**Decided.** Rejecting returns the order to `queued` immediately. Nothing is
suppressed, no cooling window is applied, and the next round may propose the
same pairing to the same person.

**Why.** "Not this person, not now" is a fact about a world that changes every
five minutes. If the round proposes it again, nothing has changed and the answer
is still the right one; a second rejection with a second reason is evidence
about the score that Loop 6 can replay. Any cooling window would be a constant
with no measurement behind it, which `policy.yaml` refuses everywhere else.

**If it is wrong.** A shift lead can be asked the same question repeatedly on a
shift where the world genuinely is not moving, which is annoying in exactly the
place annoyance costs most. The signal is visible in the record - repeated
rejections of one pairing - and the fix would be a scoring change rather than a
suppression rule.

**Look at.** [ADR-071 §4](adr/0071-a-round-proposes-and-a-person-decides.md),
`tests/dispatch/test_the_confirmation_gate.py::TestRejecting::test_the_next_round_proposes_it_again_and_that_is_the_decision`.

## 18. The CMMS question is closed, and our own system is what gets finished

**Decided.** The plant has a work-order system. The intended destination is
therefore that system; our own screens are the guaranteed floor, and a CMMS
adapter is written against a contract we define and test against a fake.

**Why.** The advisor's answer carried a fallback clause - integrate, *or at
least have somewhere this ticket is displayed* - and the second half is a
requirement this project can meet with no access to anybody's system. Writing an
adapter against a guess at somebody's SAP PM interface would produce code that
looks finished and cannot be discovered to be wrong until the slice that would
have built the real one is gone.

**If it is wrong.** If access is granted early and easily, a term was spent
building screens the plant would not have needed. That is the trade taken
deliberately: the screens are also what the technician trial (ADR-014) runs on,
and they are the only part of layer 4 whose completion does not depend on
somebody outside this project.

**Look at.** [ADR-070](adr/0070-the-plant-has-a-cmms-and-what-that-changes.md),
[ADR-012](adr/0012-tickets-leave-through-an-adapter.md), `src/pdm/sinks/`.

## 19. Machine health is two orderings, never one number

**Decided.** A health reading reports its two contributions as two - what the
history says and what is open now - and never blends them into a single score.
Two orderings come out rather than one ranking, and no fourth origin is created:
health is read and is not a source of work.

**Why.** A blended number is the one a screen would sort by and nobody could
take apart. The two halves answer different questions on different evidence, and
a machine that is quiet now with a bad year reads differently from one that is
loud today, which is exactly the distinction a blend destroys. `.importlinter`
holds both prohibitions structurally: health cannot reach `work/`, and the score
cannot read health.

**If it is wrong.** This is the piece most likely to be redirected once the
advisor sees a screen of it, and ADR-072 says so in as many words. A supervisor
may want one number and may be right to. The cost of changing is low - the two
readings are computed separately and a blend would be a third thing built on
top - and the cost of having blended first is that nobody could have found this
out.

**One figure to quote and one to withhold.** Over 40 draws the two degraded
machines take the top two places 39 times, and the two planted to be ignored
finish last. Say also what it does not measure: a history generator writes
closed work orders and not signals, so there are no open Findings to rank and
none were invented.

**Look at.** [ADR-072](adr/0072-machine-health-is-read-not-a-source-of-work.md),
[ADR-076](adr/0076-what-machine-health-is-computed-from-and-what-it-may-not-be-ranked-by.md),
`docs/results/health.md`, `.importlinter`.

---

## 20. A false alarm may argue for a narrower threshold and never a looser one

**Decided.** Loop 2 proposes tightening a threshold when the evidence supports
it, capped at 10%, and refuses outright on a rule flagged `safety_critical`
however many false alarms it counted. Six refusals are named rather than
returned as one failure.

**Why.** ADR-022 gives every loop the same shape - propose, never change - and
one prohibition. A loop that could argue for loosening a safety-linked rule
would be arguing from the cheapest possible evidence: the alarms that did not
matter. The ones that would have mattered leave no row.

**If it is wrong.** A rule that genuinely over-fires on a safety-linked
component keeps over-firing, and the alarm fatigue that follows is a real cost
paid to avoid a worse one. The escape is a person changing the threshold with a
record, which is the path ADR-022 leaves open on purpose.

**The one-sidedness is carried on every proposal** rather than left to a
reviewer to remember: the evidence for narrowing is always the alarms that were
wrong, and never the faults that were caught.

**Look at.** [ADR-073](adr/0073-what-a-false-alarm-may-propose-about-a-threshold.md),
[ADR-022](adr/0022-every-improvement-loop-proposes-rather-than-changes.md),
`src/pdm/work/thresholds.py`, `config/rules.yaml`.

---

## 21. The CMMS contract is ours, written down, and not guessed from a product

**Decided.** `CmmsSink` posts to a contract this project declares - a JSON
ticket, a bearer token, an idempotency key that is the work order's own
reference - and expects an identifier back. A 2xx naming no identifier is a
refusal, not a delivery.

**Why.** Nobody has seen the plant's system. An adapter written against a guess
at somebody's SAP PM interface is code that looks finished and cannot be
discovered to be wrong until the slice that would have built the real one is
gone. A contract that says it is ours can be handed to whoever owns that system
as a question.

**If it is wrong.** The plant's system accepts something else and the adapter is
rewritten, which is one file and the thing ADR-012's port exists for. What does
not have to be rewritten is everything that produced the ticket.

**The timeout is derived rather than chosen** - from the batch size and the
round length - and a test holds the derivation, so the number cannot drift away
from its reason.

**Look at.** [ADR-074](adr/0074-the-cmms-contract-is-ours-and-what-the-third-destination-may-promise.md),
[ADR-068](adr/0068-a-ticket-that-was-dispatched-and-a-ticket-that-arrived.md),
`src/pdm/sinks/cmms.py`.

---

## 22. The confirmation record says how often two parties agreed, and can never say who was right

**Decided.** `GET /dispatch/confirmations` reports agreement, expiry, decision
time, and every rejection and expiry in full, per shift and per band. It reports
no threshold and makes no recommendation, and both limits are carried on every
response rather than left in a document.

**Why.** Nothing in this system records what a confirmed placement went on to
cost. A supervisor who confirms everything to clear a screen is indistinguishable
in these rows from one who read each proposal, so a high agreement rate is as
consistent with a scheduler nobody is checking as with one that works.

**If it is wrong.** Somebody quotes the agreement rate as evidence the scheduler
is good. That is the misreading the endpoint is shaped to prevent, and the
defence is that the limitation travels with the number.

**There are no figures yet**, and that is the current state of the answer rather
than a gap in the report. `docs/trial-protocol.md` is how to produce them.

**Look at.** [ADR-075](adr/0075-what-the-confirmation-record-may-be-read-to-say.md),
[ADR-071](adr/0071-a-round-proposes-and-a-person-decides.md),
`docs/results/confirmations.md`.

---

## 23. An operator may report a fault, and may not call it critical

**Decided.** All four roles may report. The severity offered is low, medium or
high; `critical` is not on the form. A second report on a machine with work
already open is turned back naming that ticket, with one tap to say it is a
different fault.

**Why.** The person standing next to a machine when it starts making a noise is
as likely to be an operator as a technician, and requiring them to find somebody
else is how a fault gets reported by radio and the system never learns of it.
`high` already clears the load gate on a heavy shift, so the level above it is
reserved for a rule that measured something rather than for a person who is
alarmed. The duplicate refusal is what stops four people seeing one stopped line
from producing four tickets.

**If it is wrong.** A genuine emergency is reported one level lower than it
deserves. The mitigation is that it still clears the gate, and that a person
confirms every placement anyway.

**The refusal lives in the service rather than the endpoint**, which is why
several fixtures now say out loud that their several jobs on one machine are
separate faults.

**Look at.** [ADR-077](adr/0077-who-may-report-a-fault-and-what-a-second-report-means.md),
[ADR-024](adr/0024-roles-and-approval-authority.md).

---

## 24. The demo roster invents people, in a script the plant does not run

**Decided.** `seed_demo.py` creates accounts and manuals and no technicians.
Inventing a roster is a second script, `seed_demo_roster.py`, kept separate.

**Why.** An account is administration and a manual declares itself invented on
every page. A technician row is a **person**: the load gate computes capacity
from it, the score ranks against it, a delivery is addressed to it, and a real
technician can end up seeing a job handed over by somebody who does not exist.
It is also the one table the plant will certainly replace. Putting invented
people in the operator's own script would seed the table that looks most
authoritative with the rows least able to declare themselves.

**If it is wrong.** Somebody runs the roster script on a plant machine and the
system places real work on invented people. The separation is what makes that a
deliberate act rather than a side effect.

**Look at.** [ADR-078](adr/0078-a-demo-roster-is-a-separate-script.md),
`scripts/seed_demo.py`, `scripts/seed_demo_roster.py`.

---

## 25. The embedding model ships inside the image, and the image is larger for it

**Decided.** The model is downloaded at build time into the path the code names
in `FASTEMBED_CACHE_PATH`, and `OnnxEmbedder` reads that variable explicitly
rather than leaving the library to find its own. Proven with
`docker run --network none`.

**Why.** The alternative was a volume filled by a documented step, and a volume
is only as good as the person who remembered. The failure when nobody did is the
one that motivated the record: on a plant machine with no route to the internet,
the library tries to fetch a model it does not have and fails at the first
document, with a TLS error in a worker's log that says nothing about a model.

**If it is wrong.** The image is about two gigabytes larger than it would be,
and every future model compounds that. A cross-encoder would add as much again,
which is a live question rather than a hypothetical.

**Look at.** [ADR-079](adr/0079-the-embedding-model-ships-inside-the-image.md),
`Dockerfile`, `src/pdm/retrieval/embedding.py`,
`tests/test_the_model_ships_in_the_image.py`.

---

## 26. Asking twice for a draft answers with the draft already waiting

**Decided.** `request_draft` checks for a proposal already awaiting a decision
on the pair and returns it rather than queueing another. 202 with
`awaiting_review`, not 409.

**Why.** A conflict would teach people to press again to find out. The answer is
the same shape either way and says which of three things happened: queued now,
queued already, or waiting for you in review. The screen also hides the button,
and the two are not redundant - hiding it stops a person pressing something with
no effect, and the check at the endpoint makes the rule true for callers who
never saw a screen.

**If it is wrong.** Somebody who wants a genuinely fresh draft has to decide the
waiting one first. Sending it back already enqueues a redraft, so the path
exists.

**This is the second time the same argument had to be made** about a rule that
looked enforced because a screen enforced it.

**Look at.** [ADR-080](adr/0080-a-draft-already-waiting-for-review-answers-the-second-ask.md),
[ADR-040](adr/0040-what-happens-when-somebody-asks-twice.md).

---

---

## 33. Operating hours are read as calendar hours, and a plant starts wholly overdue

**Decided.** The one PM interval this project has a source for is the R-2000iC
manual's "replace the toothed belt at 8000 operating hours", and `plant.yaml`
schedules it as 8000 hours of calendar time. A task nobody has recorded as done
is due from the day it was registered, so an installation starts with its whole
schedule overdue.

**Why.** Calendar hours are never fewer than operating hours, so the task falls
due no later than the manual asks, and early is the safe direction for a belt.
Counting real operating hours needs a signal nobody has agreed to send. The
alternative to "due from registration" is inventing a last-done date, which is
the one thing a maintenance system may not do about maintenance.

**If it is wrong.** A machine that spends a week stopped still accrues calendar
hours, so after a long outage the belt task falls due before the manual means
it. The ticket is then work that may not be needed, and a technician closing it
`no_problem_found` does not advance the clock, so it returns at the next scan.
On day one, a plant sees its entire schedule as overdue at once; the load gate
holds that work for a quiet shift, so it queues rather than crowding anything
out, but it is the wrong first impression and the fix is importing the plant's
own dates ([#118](https://github.com/fournarin/is/issues/118)).

**Look at.** [ADR-083 §2 and §4](adr/0083-the-pm-schedule-becomes-a-source-of-work.md),
`config/plant.yaml`, `src/pdm/work/domain.py::due_pm_tasks`,
`tests/work/test_the_pm_schedule.py`.

---

## 34. Only `fixed` means a PM task was done

**Decided.** Closing a scheduled order `fixed` sets `last_done_at` and the next
occurrence falls out of the interval. `not_fixed`, `temporary_fix` and
`no_problem_found` leave the task due, so the next scan issues it again.

**Why.** Advancing the interval on a job that did not happen hides it for the
length of the interval - 333 days, for the belt. `no_problem_found` is the
subtle one: on a condition order it is the false-alarm signal Loop 2 needs
(ADR-073), and on a PM order it says the technician found nothing to do, which
is not the same as the procedure having been carried out.

**If it is wrong.** A technician who closes a PM order `no_problem_found`
because the belt genuinely did not need changing gets the same ticket again at
the next scan, and the only way to stop it is to close one `fixed`. The
counter-argument is that an inspection is itself the maintenance, in which case
`no_problem_found` should advance the clock; that is a decision about what a PM
task means, and it wants an engineer rather than a default.

**Look at.** [ADR-083 §5](adr/0083-the-pm-schedule-becomes-a-source-of-work.md),
`src/pdm/work/domain.py::pm_task_was_done`, `src/pdm/work/service.py::close`.

---
---

## 35. The rehearsal ran with an older image, and what that does and does not reach

**Decided.** The staleness is recorded rather than quietly fixed, and the claims
made while it was true were checked one at a time. One needed qualifying, and it
was written the day before the bug was found, in this repository's own log.

**What was actually stale.** `docker compose up --build` rebuilds the services
it starts - `api`, `web`, both workers and `migrate` - on every rehearsal. The
`rehearsal` service is behind a profile, so it is not one of them, and compose
builds it only when its image is missing. So **the system under test was current
on every run; the container the checks and the seeds run in was not.** The
screen checks live in the mounted checkout and are current too. What was three
weeks old was the `pdm` package they import: the seeding, the config loading,
the repositories they write rows with.

**How far back.** `rehearsal` has been behind a profile since it was created
(`41265c2`, 23 August, #78). The first rehearsal built its image, and nothing
rebuilt it afterwards. The runs recorded in `docs/loop-log.md` are 23 August,
where the image was minutes old, 26 August, where it was three days old and the
slice was about the script's own counting, and then none until 19 September -
the routine was off from 24 August to 18 September, and the container images on
this machine were still three weeks old when they were looked at on 19
September, which is the same thing said twice.

**The claim that needed qualifying is from 19 September, in this log.** Two
rehearsals that day reported 7 of 7 checks passing, and one of them was `--fresh`.
Both ran with the three-week-old harness. The screens and the API they exercised
were built that day and the result about them stands; the seeding and the
configuration loading inside those runs were not current, which is exactly what
broke on 20 September the moment `plant.yaml` gained a key. So "7 of 7" that day
meant less than it sounded: it covered the stack and not the path that sets the
stack up.

**The claim that did not need qualifying is slice 15.2's**, on 18 September:
"verified against a running API and web server rather than only in tests", and
the same sentence in #103's commit message. That verification did not go through
the rehearsal. No `up --build` had run on this machine since late August, so the
containers held an API with no `/overview/health` in it at all - a check
asserting on that panel could not have passed against them. It passed against an
API and a web server started from the checkout by hand, on their own ports.

**If it is wrong.** If a rehearsal did run between 29 August and 19 September
without leaving a line in the log, then a 7-of-7 from it covered less than it
said, in the same way the 19 September runs did. The log is the only record
either way, and the image dates that would have settled it are gone: the image
was replaced by the fix.

**Look at.** [ADR-067](adr/0067-the-rehearsal-runs-inside-the-stack-it-rehearses.md),
`scripts/rehearse.py`, `tests/test_the_rehearsal_builds_what_it_runs.py`,
`docs/loop-log.md` for 2026-09-19 and 2026-09-20.

---

## 40. An upgrade may now stop, a roster write may now be refused, and one invariant was made smaller instead of made true

**Decided.** Four things, in
[ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md),
which is the code fix entry 31 said was coming.

1. **`source_doc` is refused when empty, on the field.** A step cites a page of
   a document or it does not construct - in a draft as much as in an approval.
   Existing rows are proved rather than excused: migration 0014 reads
   `work_order.playbook_snapshot` and `playbook.steps` and **stops the upgrade**,
   naming the rows, if any step has no source. It rewrites nothing, because
   invariant 2 makes a snapshot unchangeable.
2. **`add_technician` takes the vocabulary and refuses a label outside it**, with
   no default, so a caller cannot skip the check by forgetting.
3. **The loader's machine check is deleted rather than replaced.** It could
   never fire; what holds the property is that `plant.yaml` declares a machine
   inside a station and nowhere else. Two tests replace it.
4. **Invariant 10's wording now says `dispatch()` and not `schedule()`.**

**Why.** Three of these make a claim true that was being made anyway. The fourth
does the opposite, and it is the one to defend: the planner's wall-clock budget
is a known defect with a known fix (entry 28), and taking the fix needs a budget
in deterministic units that nobody has measured. Between a page that overstates
and a page that says where the guarantee ends, the second is what lets a reader
trust the rest of it - and `docs/results/reproducibility.md` already says which
cell moves.

**If it is wrong.** The stopping upgrade is the sharpest edge: a plant that has
a bad row cannot deploy until somebody decides what that row should be. That is
intended - the alternative is a work order that silently fails to load a year
later - but it is a deployment step that can fail, and nobody has seen it fail
because no such row exists in any database this project has built. The refused
roster write can reject data that loads today; only `seed_demo_roster.py` writes
technicians, and it draws from the same vocabulary. Narrowing invariant 10 is a
decision to publish a comparison that is reproducible in 1,439 of 1,440 cells
and to say so, rather than to make it 1,440 this term.

**Look at.** [ADR-084](adr/0084-two-invariants-get-a-mechanism-and-two-get-narrower-wording.md),
`migrations/versions/0014_every_stored_step_names_its_document.py`,
`src/pdm/contracts/work.py`, `src/pdm/dispatch/repo.py::add_technician`,
`scripts/check_no_wall_clock.py`, [`invariants.md`](invariants.md).


# Not decided, and still going to be asked about

The six below are not choices this project made and defends. They are places
where an examiner's question has no answer yet, found by a read of the whole
repository on 2026-09-18 and a check of that read on 2026-09-19. They are here
because arriving at a viva having already named them is a different position
from being shown them.

---

## 27. A safety setting is configured, validated, and read by nothing

**Decided.** Nothing, yet - and that is why it is here. `policy.yaml` sets
`safety_min_score: 0.75` on the runtime retrieval profile under a comment saying
safety questions use a stricter bar. `retrieval/service.py` builds both profiles
passing `min_score` alone. Nothing reads the field.

**Why it survived.** Deleting a safety-labelled setting quietly is the wrong way
to close a design question, and the question is real: nothing in this system
decides what makes a question safety-related, so the key describes an intention
that was never designed rather than a behaviour that was lost.

**If it is wrong.** An operator reading `policy.yaml` concludes the system holds
a higher bar before answering a safety question. It does not. That is the worst
kind of configuration entry - not unused, but actively misleading about a safety
property.

**A gate now names it.** `scripts/check_config_is_read.py` fails the build on any
schema field nothing reads, with this one as a listed exception whose reason is
beside it. Either build it or delete it; the exceptions list is a debt with a
name on it, not permission.

**Look at.** `config/policy.yaml`, `src/pdm/retrieval/service.py`,
`scripts/check_config_is_read.py`.

---

## 28. The solver's budget is wall-clock seconds, so one published figure is machine-dependent

**Decided.** `solver_seconds: 5.0`, applied as `max_time_in_seconds`. CP-SAT's
parallel portfolio is turned off and the seed fixed, with a comment explaining
that several workers would make the solution depend on how loaded the machine
was, "which would make every figure in docs/results/ unreproducible, and
quietly". The line above has the same property and was not guarded.

**Why it matters.** Re-run on another machine, 1,439 of 1,440 rows come back byte
for byte. The one that moves is CP-SAT's mean response, because 2 of 15 solver
calls in that cell stop at the ceiling rather than proving optimality, and a
faster machine searches further in the same five seconds. Units lost does not
move at any budget - response time is not in the objective, so among plans
losing the same production it is a free variable.

**If it is wrong.** A reader who re-runs the sweep gets a different number in one
column and has reason to doubt the rest. The reported response figure for that
policy is a property of which equally-optimal plan came back, not of the policy.

**The fix is known and not taken here.** `max_deterministic_time` bounds search
work rather than seconds and is in the pinned library version. It does not buy
optimality - the same two solves stay unproved at every budget tried - it makes
the arbitrariness the same everywhere, which is what reproducibility needs and
all it needs. Whether to adopt it, and at what budget, is a decision with a
record still to write.

**Look at.** `docs/results/reproducibility.md`,
`src/pdm/dispatch/solver.py`,
[ADR-054](adr/0054-what-cp-sat-optimises-and-what-it-may-not-touch.md).

---

## 29. Account administration exists in code and cannot be reached

**Decided.** Nothing, yet. `platform/auth/repo.py` has `set_password`,
`set_role` and `deactivate`, written, documented and correct-looking.

`set_role` and `deactivate` have no caller anywhere and no test. `set_password`
has exactly one caller and it is not a person changing a password: `LocalAccounts.authenticate`
re-hashes on a successful login when the stored scrypt parameters are out of
date, which is a good piece of work and is the only reason that function runs.
**So the capability to set a password exists, is exercised, and is still not
reachable by anybody who wants to change one.**

**Why it matters.** ADR-036 argues for sessions in the database using the case
of "an engineer whose approval rights were withdrawn this morning" - a role that
keeps working until somebody logs out. The function that implements the
withdrawal is unreachable. On a real installation the account list is whatever
the seed script made it: a password cannot be changed by the person who owns it,
a role cannot be changed at all, and access cannot be withdrawn except by hand in
the database.

**If it is wrong.** It is not wrong yet, because nobody has installed this
anywhere real. It becomes wrong on the first installation that outlives one
person's employment.

**Defensible for a trial and not for a plant**, and `docs/install.md` says so in
those words rather than leaving it to be found.

**Look at.** `src/pdm/platform/auth/repo.py`,
[ADR-036](adr/0036-sessions-in-the-database-behind-an-identity-adapter.md),
[ADR-024](adr/0024-roles-and-approval-authority.md).

---

## 30. ADR-028 says every stored time is timezone-aware, and no contract checks

**Decided.** Nothing. ADR-028's decision includes "Store UTC, timezone-aware,
everywhere; convert to local time only for display", and `Signal.timestamp` is a
plain `datetime`, which pydantic accepts naive. So does every other datetime
field in `contracts/`.

**Why it matters.** Mixing a naive datetime with an aware one raises
`TypeError`, and `handlers.py` runs a whole trigger tick in one transaction, so
one naive timestamp would roll back every Finding the batch raised - the same
shape as the `nan` reading fixed in `triggers/trend.py`, arriving through a
different field of the same contract.

**Why it is not urgent.** The rule holds everywhere in practice and was measured
rather than assumed: every datetime column in `migrations/` is `timestamptz`,
`Scenario` refuses a naive `starts_at` by name, and of thirty naive `datetime(...)`
constructions in the repository, twenty-five are in one test file that is
deliberately testing naive handling and the rest are deliberate in the same way.
**Nothing has drifted. Nothing is checking that it has not.**

**What the answer looks like, and why it is not taken here.** `AwareDatetime` on
the contract fields would enforce it in one place. That rejects inputs the system
currently accepts, which is a change to a contract rather than a bug fix, and
ADR-027 makes the contracts deliberately expensive to change. It needs a record.

**Look at.** [ADR-028](adr/0028-clock-is-the-single-time-port.md),
`src/pdm/contracts/work.py`, `src/pdm/signals/domain.py`.

---

## 31. Two invariants were cited as enforced, and the mechanism was not there

**Decided.** The text is corrected first and the code is fixed separately. Rows
4 and 13 of `docs/invariants.md` now say what the code does, and the page has a
**Known gaps** section listing these two and three smaller ones. The code change
is [#105](https://github.com/fournarin/is/issues/105): its own pull request,
with ADR-084, labelled `human-review`.

**How it was found.** `docs/invariants.md` was written to bring the fifteen
invariants into the repository, and its first version said every **Enforced
by** entry had been checked against the code. For two rows that check had only
confirmed that the named file existed, not that it did what the row said. On
2026-09-19, before the page was pushed, each entry was read at the line it
points to. What that found went into the description of #104 rather than into
the page, and #104 merged with the page unchanged. The correction reached `main`
in a pull request of its own, after the false rows had already landed there.
The findings were:

- **Invariant 4.** The validator is in `contracts/work.py`, not
  `playbooks/domain.py`, and it never looks at `source_doc`. An approved
  playbook whose step cites `""` constructs without error.
- **Invariant 13.** The boot check for machines fills both of its dictionaries
  in the same loop, so it can never fire. The skill half is not checked at boot
  at all, and a technician's skills are not checked anywhere.

Both invariants are cited in more than eighty records, and 13 appears in the
title of a CI step. The same day found the same kind of mistake elsewhere:
the `ruff` result for this batch was reported green from a branch that did not
contain the file that failed. Both were a check that ran against something
other than what was then claimed.

**Why the text first.** The page was what was false, and it was about to be
published. The code fix is several decisions, not one edit, and none of them
belongs in a documentation pull request:

- A stricter `PlaybookStep` meets old `playbook_snapshot` rows, which invariant
  2 makes unchangeable.
- Checking technicians' skills can refuse data that loads today.
- Deleting the machine check needs somebody to say what it was meant to catch.

Correcting the page without saying so would have been quicker, and it would
have removed the only record that the page had been wrong. A record of when a
claim was false is a better answer to "how do you know what this repository
says is true" than a page that has always been right.

**If it is wrong.** Until #105 lands, invariant 4 holds only because nothing
produces an empty source, and the technician half of invariant 13 does not hold
at all. A reader who trusts the CI step "configuration must be loadable
(invariants 7 and 13)" believes it checks more than it does.

**Answered.** ADR-084 and entry 40. Both invariants now have a mechanism, both
are broken on purpose by a test, and the CI step names invariant 7 alone. What
is written above stays as it was: it is the record of a period when the page was
wrong, which is the point of it.

**Look at.** [`invariants.md`, Known gaps](invariants.md#known-gaps),
`src/pdm/contracts/work.py`, `src/pdm/platform/config/loader.py`,
`src/pdm/dispatch/repo.py::add_technician`.

---

## 32. The improvement loops were delivered as mechanisms, and the loop around them was never opened

**Decided.** Nothing yet, and that is why this is here. Loop 1 (durations,
ADR-066) and Loop 2 (thresholds, ADR-073) were built, tested and merged as slices
11.1 and 11.2 on 22 and 23 August. Neither has a caller outside `tests/`.
`worker-runtime` registers two handlers, dispatch and observe
(`src/pdm/workers/runtime/__main__.py:204`), and no screen shows a proposal.
The path they need is [#107](https://github.com/fournarin/is/issues/107).

**Why it was left that way, in the records' own words.** Leaving it was
deliberate: ADR-066 §6 says "This slice adds no endpoint, no screen and no
cadence, and until those exist the loop is a mechanism rather than a loop that
turns", and its consequences add "Nobody can yet act on it from a screen. That
is the next slice, not this one." ADR-073 repeats both, and calls the mechanism
"the cheap half".

**Why it stayed that way.** Leaving it was not decided; it happened. **The next
slice was named in two records and never opened as an issue.** The unattended
loop works only issues that exist; `.claude/autonomy.md` forbids it to invent
scope. The day after 11.2 merged it was switched off, and it stayed off for
twenty-three days. `docs/loop-log.md` records both slices as "left for a person
as the issue asks". That phrase is about the pull requests, which issues #60
and #75 asked to be left for a person to merge. It is not about the wiring, and
it should not be read as the reason the wiring was never done. Nothing in the
repository gives that reason.

**What the report may say.** That the loops' decision logic exists, is tested
against inputs written out by hand, and refuses to propose loosening a
safety-linked threshold. **Not** that the system learns from the jobs it closes.
It contains the arithmetic it would learn with, and nothing runs it.

**If it is wrong to leave it.** The claim that `estimated_minutes` and
`actual_minutes` are separate "so the first can be fed back from the second"
(ADR-006, `CLAUDE.md`) describes a loop that has never turned. Invariant 11
holds only because the loop it constrains never runs (entry 31, and
`invariants.md` Known gaps).

**The lesson that generalises.** A record that says "that is the next slice"
has made a promise. Once the slice it came from is merged, nothing keeps that
promise unless the next slice exists somewhere work is picked from.

**Look at.** [ADR-066](adr/0066-what-the-finished-jobs-may-change-and-what-stops-them.md),
[ADR-073](adr/0073-what-a-false-alarm-may-propose-about-a-threshold.md),
`src/pdm/workers/runtime/__main__.py`, `src/pdm/work/estimates.py`,
`src/pdm/work/thresholds.py`.

---

---

# What still stops and waits for a person

Two things stop a slice outright, per
[ADR-052](adr/0052-what-review-was-protecting-and-what-it-was-not.md). A slice
hitting either is labelled `blocked`, with the question in the issue.

1. **A number standing in for a measurement**, where no manual, no measurement
   made here, and no recorded decision supports it. Writing it down does not
   make it defensible; somebody has to decide whether the project will publish a
   result that rests on it.
2. **A safety-linked threshold.** ADR-022 forbids any loop from proposing one be
   loosened, and an agent proposing it in a slice is the same act under a
   different name.

Separately, [ADR-085](adr/0085-what-the-unattended-loop-may-merge-and-a-check-that-can-stop-it.md)
keeps the button with a person. The unattended loop builds nothing from an issue
labelled `human-review`, and merges no pull request labelled `human-review` or
touching `.claude/`, `.github/workflows/`, `migrations/` or
`docs/invariants.md`. Those wait for a person to merge them. They are not
`blocked`, because nothing in them is a question.

Currently open: none.

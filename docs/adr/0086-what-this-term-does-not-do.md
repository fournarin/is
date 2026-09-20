# ADR-086: What this term does not do, and why

Written on 2026-09-20, five weeks into the fourteen and **32 days before the
feature freeze `config/cadence.yaml` already names** (22 October), with 53 days
before the report is due. Twelve issues are open and there is not time for
twelve. This record is the scope decision, in the shape
[ADR-082](0082-the-data-is-not-coming-this-term-and-what-that-closes.md) used
for the data that is not coming: what closes, what stays true anyway, and what
would reopen each one.

It exists to be the answer to "why did you not do X" in a viva, given once,
rather than a shrug per question.

## Context

The backlog is not short of good work. It is short of weeks. What the term has
delivered so far is the four layers end to end on generated data, with the
schedule as a live source of work since #119, and a report whose figures all
come from scripts in the repository.

What is missing divides cleanly, and the division is the decision:

- **Work that makes an existing claim true.** The improvement loops decide and
  nothing runs them; two invariants are cited and not enforced; most invariants
  have no test that breaks them on purpose. Each of these is a sentence in the
  repository that is weaker than it reads.
- **Work that needs something this term does not have.** Loop 3 needs realised
  ETA errors from a plant. The reranker needs a model export that the
  environment could not reach and a licence that suits an on-premise delivery.
- **Work that is repair rather than result.** Pinning the model by hash, moving
  slice scope out of GitHub issue bodies, moving operational facts out of one
  machine's memory, and the survey of what the repository cites but does not
  hold.

## Decision

### Built this term, in this order

1. **[#107](https://github.com/fournarin/is/issues/107), the improvement loops get a runtime path.** Loop 1 proposes a
   duration from finished jobs (ADR-066) and Loop 2 proposes a threshold from
   false alarms and refuses a safety-linked one (ADR-073). Both are written and
   tested; neither is called by anything outside `tests/`. **This is the largest
   remaining gap in a predictive-maintenance project**, and it is the one that
   turns a limitation into a result: the README currently has to say the system
   does not learn from the jobs it closes. What is missing is a job kind, a
   handler and a screen an engineer can approve a proposal on.
2. **[#105](https://github.com/fournarin/is/issues/105), invariants 4 and 13 become enforced.** Small, and it closes a
   hole in the document that is the face of this project: `docs/invariants.md`
   claims a mechanism for each invariant and for two of them there is none.
3. **[#108](https://github.com/fournarin/is/issues/108), a test per invariant that breaks it on purpose** - as far as
   it gets. **Not all fifteen.** The ones cited most are 1, 10, 12, 14 and 15,
   and those come first. The page says which rows have such a test and which do
   not, so the answer to "how do you know" is a row rather than a belief.

### Closed for this term

**Loop 3, the advertised ETA interval ([#99](https://github.com/fournarin/is/issues/99)).** ADR-020 measures prediction
against a synthetic ground truth, and Loop 3 would close that loop by comparing
what was advertised with what happened. Doing that on synthetic data would be
measuring the generator against itself: the interval would tighten to fit a
degradation curve this project wrote. **It needs realised errors from a plant,
and ADR-082 records that the data is not coming this term.** The mechanism
stays unbuilt rather than built against the wrong evidence.

*What would reopen it:* one plant, one month of closed predicted work orders.

**The cross-encoder reranker ([#100](https://github.com/fournarin/is/issues/100)).** `docs/reranking-candidates.md` is
the survey and it decides nothing on purpose. Of six candidates in the chosen
library, one reads Thai and its licence forbids commercial use, which
disqualifies it from an image handed to a plant; the permissively licensed
alternative needs an ONNX export that the environment could not reach.
`docs/drafting-baseline.md` already records what the drafter gets wrong and
names the reranker as the fix, which is an honest statement of a gap and does
not become less honest by staying open.

*What would reopen it:* a working export, or a licence that changes.

**The last-done dates a PM schedule needs ([#118](https://github.com/fournarin/is/issues/118)).** Every task starts
overdue because nobody knows when it was last done (ADR-083 §4). The fix is the
plant's own records, which are in the CMMS ADR-070 found, and asking for them is
the same conversation as asking for sensor data.

*What would reopen it:* the maintenance history ADR-082 is waiting on.

### Done if the weeks allow, and recorded either way

[#114](https://github.com/fournarin/is/issues/114) (the embedding model is pinned by name, not by content),
[#115](https://github.com/fournarin/is/issues/115) (a slice's scope lives only in its issue body),
[#116](https://github.com/fournarin/is/issues/116) (operational facts live in one machine's memory),
[#117](https://github.com/fournarin/is/issues/117) (the survey of what this repository cites but does not hold),
[#111](https://github.com/fournarin/is/issues/111) (nothing checks the routine's prompt against its mirror) and
[#112](https://github.com/fournarin/is/issues/112) (a record can merge without its ledger entry).

None of these changes what the system does. Each is a way the project could
mislead a later reader, and each is already written down where that reader would
look. **If they are not done, the report says they are not done** and points at
the issue, which is the same standard the rest of this file holds.

### The backlog carries only what is being built

The three issues above carry `slice` and are numbered **19.1, 19.2 and 19.3** in
the order they are listed, because the loop takes the lowest slice number first
(`.claude/autonomy.md` step 3). #99 and #100 lost the label, so the loop cannot
pick up work this record has just declared closed. Each of the three says in its
own body that a person merges it: all three carry decisions somebody has to
defend, which is what the ledger and ADR-085 §6 are for.

That is the mechanism behind the decision rather than a note of intent. A scope
decision that lives only in a record is one the next unattended run does not
read.

## Reasons

**Thirty-two days is the real constraint, and it is already written down.**
`config/cadence.yaml` puts the freeze at 22 October because week 12 is the
freeze and weeks 13 and 14 are the report (ADR-014). Nothing in this record
changes that date; it decides what fits before it.

**The three that are built all convert a weaker sentence into a stronger one.**
The system already schedules, ranks, explains and dispatches. What it says about
itself is where the remaining risk is, and an examiner reads the saying.

**The two that close, close for the same reason as ADR-082.** Building Loop 3 on
synthetic error would produce a figure that looks like evidence and is not, and
this project has already refused that trade once, which is why ADR-020 exists.
The reranker is a delivery constraint rather than a task left undone, and
`docs/reranking-candidates.md` says so in a form somebody can act on later.

**Declaring the rest "if time allows" is not a way of avoiding the decision.**
Each has an issue with what to do written in it, so a later term - or a later
week - starts from a decision rather than from a rediscovery. That is the same
argument ADR-052 makes about the ledger.

## What this does not do

- **It does not change the freeze date or the report weeks.** ADR-014 reserved
  them unconditionally and nothing here touches that.
- **It does not close the technician trial.** `docs/trial-protocol.md` stands,
  with its criteria written before anybody arrives, and it remains the one piece
  of evidence this project cannot manufacture.
- **It does not decide what the report says about any of this.** It decides what
  gets built. The report must state each closed item as closed and why, and
  `docs/results/confirmations.md` already shows the shape: a file that says "not
  yet, on no evidence either way".
- **It does not re-plan the term.** `docs-md/plan.md` is outside this repository
  on purpose, and if the two disagree, this record is the one a reader of the
  repository can see.

## Consequences

- The backlog the unattended loop works from is three issues long, and when it
  empties the loop opens a `backlog empty` issue rather than inventing scope
  (`.claude/autonomy.md`).
- `README.md`'s "What this cannot do yet" is the list this record explains. When
  #107 lands, the bullet about not learning from closed jobs goes, and that is
  the only one of these that changes what the system does.
- If a week is lost, the order above is the order to cut from the bottom: #108
  first, then #105. #107 is the one worth protecting.
- If the maintenance history or the plant's PM records arrive before the freeze,
  #99 and #118 reopen together, and ADR-082's section on what that would change
  applies unchanged.

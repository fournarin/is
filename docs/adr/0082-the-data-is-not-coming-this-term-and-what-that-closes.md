# ADR-082: The data is not coming this term, and what that closes

Takes the decision [ADR-020](0020-predictions-from-trend-extrapolation-measured-on-synthetic-data.md)
reserved for week 9 and the one the plan reserved for week 6, five and no weeks
early respectively, because the advisor has answered the questions both were
waiting on.

## Context

ADR-020 ends with a consequence: "**The scope conversation with the advisor has
to happen in week 1**: the accuracy delivered this term is measured on simulated
data, not on Ford's machines." That conversation happened. Its record is the
proposal document the advisor answered in red ink, and the answers relevant here
are three:

Asked whether he agreed that this term delivers a mechanism ready for real data
plus an accuracy figure on simulated data:

> "OK ครับ เราทำบนฐานที่เรามีไปเลย" - fine, let us work on the basis we have.

Asked how far the conversation with the plant had got:

> "ผมคิดว่าน่าจะอีกไกลนะ" - I think it is still a long way off.

Asked whether the technician-side data existed anywhere - names, skills, shift
roster:

> "น่าจะขอข้อมูลส่วนนี้ได้ครับ" - that part can probably be asked for.

Those answers sat unread for close to a month. The document carries eight
answers; three were transcribed at the time and five were not, and two of the
five are the ones above. They were found on 18 September 2026 and are now in
`docs-md/professor_notes.md` in full.

Two things follow that this project had been treating as open. **Plant signal
data is not arriving this term** - not as a risk to mitigate but as a fact
stated by the person negotiating for it. And **the technician roster might
arrive**, but the asking belongs to the advisor, which means this project cannot
schedule it, chase it, or build a dependency on it.

Meanwhile the term is half gone. Week 1 began 7 August 2026; today is week 7 of
14, and weeks 4 through 6 produced nothing because the unattended loop had been
disabled since 24 August without anything saying so. Five weeks of technical
work remain before the week-12 feature freeze.

## Decision

**Take both decision points now, in the direction each already named.**

1. **Layer 1 ships measured on synthetic data.** The week-9 decision in the plan
   offered "deliver detection and prediction measured on synthetic and state the
   limitation in the report". That is taken. `docs/prediction-baseline.md` is
   this term's final answer on prediction accuracy, not a placeholder for a
   better one.

2. **The scheduler is evaluated on the simulator alone for the rest of the
   term.** The week-6 decision point - "if the technician data has not arrived,
   lock the scheduler's evaluation to the simulator, carry on, do not wait" - had
   its condition met on 17 September and nobody pressed it. It is pressed here.

**What is out of scope for this term**, and may not be started without a record
superseding this one:

- Building `ReplaySource` or `LiveSource` at all. ADR-002 named three
  implementations of the port and **one was built**: `SIGNAL_SOURCE=replay` and
  `=live` refuse at boot today, and that stays true this term.
- Tuning thresholds, rule parameters or `policy.yaml` weights against plant data.
- Any work whose only justification is that it will be useful when the data
  arrives.

**What stays, and is not weakened by this record:**

- The `SignalSource` port (ADR-002). The port is what makes a second
  implementation a small piece of work rather than a rewrite, and keeping it
  costs nothing. Closing the branch is not the same as removing the seam - but
  the seam is all there is, and this record is the one that says so out loud.
- `SyntheticSource` and everything ADR-032 guarantees about it.
- `SIGNAL_SOURCE=synthetic` in `.env.example`, which is now the only
  configuration this term has exercised, rather than one of several it could.

## Reasons

1. **This is the advisor's answer, not our estimate.** Every previous version of
   this decision rested on our own reading of "มีค่า real-time ครับ แต่ผมยังไม่ได้นะ"
   from the first round. "อีกไกล" is a direct answer to a direct question, and it
   is the difference between planning around a risk and planning around a fact.

2. **An open branch costs more than an absent one.** While "the data might
   arrive" stays live, every design choice pays a small tax in optionality, and
   every week somebody re-asks whether to start preparing. Writing the branch
   closed is what stops that recurring, which is the same argument
   [ADR-022](0022-every-improvement-loop-proposes-rather-than-changes.md) makes
   about proposals: a thing that is not decided gets decided repeatedly.

3. **Five weeks is not enough to hold anything warm.** What remains to be
   delivered - playbook coverage, a README and an installation guide the plant
   can follow, and a technician who has actually used the system
   ([ADR-014](0014-report-and-technician-trial-are-reserved-unconditionally.md)) -
   competes directly with any effort spent on a data path that will not be
   exercised. The trade is explicit rather than accidental.

4. **The report is graded, and the advisor wants a publication as well.** Asked
   whether this was a delivery to the plant or a paper, he answered "ทั้ง 2 ทางเลย" -
   both. A record of the date a limitation stopped being a risk and became a
   condition of the work is worth more to either reading than an unstated
   assumption would be.

## Consequences

- **`ReplaySource` and `LiveSource` were never built, and the report must say so
  in those words.** ADR-002's title says the interface has three implementations
  and the repository has one. A port with one implementation behind it is an
  honest thing to deliver; describing it as three is not, and a reader who takes
  the title at face value will believe this system has spoken to a plant.

  This correction has its own small history worth recording: the first draft of
  this record, and of `README.md`, both stated that `LiveSource` existed and had
  merely never been run. Neither author checked. It was found by fuzzing the
  prediction code and following the question "which sources can reach this",
  which is a reminder that a claim about what exists is as checkable as a number
  and was not checked.

- **Every claim about prediction is bounded by
  `docs/prediction-baseline.md`, per horizon.** The table there reports a mean
  error under three minutes inside three hours and about ten hours late at the
  twelve-hour horizon. A single headline figure across all horizons remains
  forbidden by ADR-020, and this record does not create an exception.

- **`mean_hours_between_failures` stays unmeasured**
  ([ADR-046](0046-what-the-simulator-models-and-what-it-assumes.md) §4), and with
  it the finding in `docs/results/diagnosis.md`: whether buffer-aware ranking
  pays for itself depends on a parameter nobody has measured. That stays a
  question for the plant rather than for another sweep, and this record makes it
  permanent for this term rather than pending. **The maintenance history the
  advisor said could probably be asked for is the only thing that would measure
  it** - which is why that request matters more than its size suggests, and why
  its absence is a stated limitation rather than a gap to fill with an
  assumption.

- **A roster that arrives is a bonus, not a plan.** If the technician data comes
  through while there is still time, it replaces what `scripts/seed_demo.py`
  deliberately does not invent
  ([ADR-078](0078-a-demo-roster-is-a-separate-script.md)), and the comparison in
  `docs/results/` can be re-run against it. Nothing in the remaining five weeks
  is scheduled on that happening.

- **Nothing here prevents the data arriving later.** It is precisely because
  ADR-002 held the seam that closing this branch costs a configuration line to
  reopen. That was the point of the seam, and this record is what it bought.

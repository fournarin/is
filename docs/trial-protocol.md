# Running the trial

[ADR-014](adr/0014-report-and-technician-trial-are-reserved-unconditionally.md)
reserves time for a real person to use this system, unconditionally and whatever
the data situation turns out to be.
[`results/confirmations.md`](results/confirmations.md) is the file that stays
empty until it happens. This page is how to run it.

**It needs no plant data and no plant access.** A supervisor pressing confirm or
reject on the demo world produces exactly the rows the confirmation record reads,
and a technician opening one job on a phone answers the question ADR-014 was
written about. Two people, forty minutes, one laptop.

## Before anybody arrives

Written down here rather than decided afterwards, because a criterion chosen
after seeing the result measures the chooser.

### What this trial is trying to find out

1. **Can a technician work from the ticket?** Not whether they like it. Whether
   they can tell what the job is, why it exists, and what to do, without being
   told by whoever is standing next to them.
2. **Does the shift lead agree with the scheduler, and when they do not, about
   what?** The disagreements are the finding. Agreement on its own is
   [consistent with a scheduler nobody is checking](results/confirmations.md).
3. **Does anything on these screens actively mislead?** A wrong answer delivered
   confidently is the failure mode this whole design bends around, and this is
   the first time somebody outside the project can catch one.

### What would count as a bad result, decided now

- The technician asks what a field means more than twice on one ticket.
- The technician cannot say why the job reached them without reading the code
  or being told.
- The shift lead confirms every proposal in under five seconds each. That is
  not agreement, it is a screen being cleared, and
  `results/confirmations.md` says in as many words that it cannot tell the two
  apart - so it has to be caught here, by watching, or not at all.
- Anybody treats a synthetic ticket as a real fault on a real machine.

**None of these is a reason to stop or to fix anything mid-trial.** They are
written down so the report can say whether they happened, and the fourth is
worth its own sentence: a generated ticket is indistinguishable from a real one
on screen, which is why `SIGNAL_SOURCE=synthetic` warns at boot and why the
first thing said in the room is the note below.

### Set the stack up the day before, not on the day

```
uv run python scripts/rehearse.py --fresh
```

It needs about ten gigabytes free and the first build on a cold machine is
nearer twenty minutes; `docs/install.md` has the rest where that page exists.
[`demo.md`](demo.md) is what to click and as whom; read it once beforehand so
the trial is not also the first time anybody has driven the screens.

Check before the room fills: at least one proposal is waiting for the shift
lead, and at least one work order carries steps with page numbers rather than a
fallback estimate. Without the first there is nothing to confirm; without the
second the technician sees the system at its weakest and the trial measures the
corpus instead of the design.

## What to say first

Once, at the start, in these words or close to them:

> Every machine and every fault you are about to see is generated. Nothing here
> came from a real plant. I am not testing you - I am testing whether the screen
> makes sense, and anything you find confusing is a defect in it rather than in
> you. Please think out loud, and please do not ask me what to do: if you are
> stuck, being stuck is the result.

Then stop talking. The strongest temptation in a trial like this is to rescue
the participant, and every rescue deletes a finding.

## Part one - the technician, about twenty minutes

Sign them in as `tech-1` and hand them the device. **A phone if there is one**:
the screen was built for somebody standing at a machine and without JavaScript,
and it has never been used on a phone by anybody who did not build it.

Ask for four things, in this order, and write down what happens rather than what
they conclude.

| # | Ask | What is being watched |
|---|---|---|
| 1 | "What is this job asking you to do?" | whether the steps read as instructions or as a document |
| 2 | "Why did this job come to you, and why now?" | [ADR-005](adr/0005-every-ticket-carries-its-reason.md)'s whole claim, in one question |
| 3 | "Would you trust these steps at a machine? What would you check first?" | whether the page citations do any work, or are ignored |
| 4 | "Close it as though you had done it." | two taps, and whether the two are findable |

Then one question that is not about the screen: **"what would stop you using
this on a Tuesday?"** It is the only question here whose answer this project
cannot get any other way.

## Part two - the shift lead, about fifteen minutes

Sign somebody else in as `sup-1` and open the overview. The top panel is the
proposals waiting.

Ask them to work through the queue as they would on a shift: confirm what they
agree with, reject what they do not, and say why out loud each time. **Do not
hurry them and do not fill silences.** Decision time is one of the four readings
the record produces, and a decision made because the room went quiet is not a
measurement.

The system records confirmations, rejections, expiries and timings by itself.
What it cannot see, and what the observer writes down:

- the words they used for each rejection, alongside the reason they selected;
- anything they looked for and did not find;
- whether they read the priority reason before deciding, or after, or not at
  all. **This is the single most valuable observation in the trial**, because it
  is what separates a confirmation step that is working from one that is a
  button.

Leave at least one proposal unanswered on purpose and let it expire. Expiry is
reported as loudly as rejection and nothing in the record has ever exercised it.

## Afterwards, the same day

```
GET /dispatch/confirmations?since=…&until=…
```

Bound it on the trial window, read it as a supervisor or an engineer, and write
the four readings into
[`results/confirmations.md`](results/confirmations.md) with the date, the number
of proposals, and who the two participants were by role rather than by name.

**Write the rejections and expiries out in full, row by row.** The counts are
the smaller half; what somebody disagreed about is the half a report can argue
from.

Add what the endpoint cannot produce: the four answers from part one, the
observation about the priority reason, and anything that met one of the bad
results written down above. A trial that met three of the four is a better
result than one that met none and was never going to.

## What this trial cannot establish

Kept here so the report does not have to discover it later.

- **One person is not a sample, and two are not two samples.** Everything it can
  produce is an existence proof - that a person could work from this ticket, or
  could not - and nothing about how often.
- **It says how often the two agreed, never whether either was right.** Nothing
  in this system records what a confirmed placement went on to cost
  ([results/confirmations.md](results/confirmations.md)).
- **A demo world is not a shift.** Nobody is tired, nothing else is broken, and
  the line is not stopped. The pressure that makes a shift lead press confirm
  without reading is exactly what a quiet room removes.
- **If the technician is not from the plant, they are not the user.** ADR-014
  asks for a real one and the plan's week-10 decision point allows a substitute
  rather than nobody. A substitute makes the finding weaker and does not make it
  worthless: somebody who has stood at a machine can still say whether a repair
  step reads like one.

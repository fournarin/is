# Should the plant stop reviewing its own work orders yet?

**There are no figures here yet, and that is the current state of the answer.**

The advisor was asked on 2026-08-23 who presses the button before a ticket
reaches a technician, and answered that a person should - **for now**, with
automatic approval as something to look at later, "once there is a record to
judge it by". ADR-071 built the record. ADR-075 built the reading. Nobody has
run a trial, so the record is empty, and the honest answer to the question in
the title is **not yet, on no evidence either way**.

This file is where the answer gets written down when there is one, so that the
written report can quote a measurement rather than an impression.

## What will be measured

Every proposal a round makes is one row in `dispatch_proposal`, carrying what
the scheduler decided, the round it was decided against, and how it ended. Four
readings come out of that (ADR-075):

| | what it answers |
|---|---|
| **confirmed / (confirmed + rejected)** | how often the shift lead agreed with the scheduler |
| **expired / (confirmed + rejected + expired)** | how much was never answered at all |
| **median, mean and longest decision time** | how long a decision took, over the proposals a person answered |
| **every rejection and every expiry, in full** | what the disagreement was actually about |

Each of the four is also produced per shift and per band, because "the shift
lead disagrees on heavy shifts" and "the shift lead disagrees" are different
findings and only the first can be acted on.

**Expiry is reported as loudly as rejection**, row by row rather than as a
count. A confirmation step nobody reaches is a queue with a person-shaped hole
in it, and ADR-071 §8 makes it as strong an argument for `automatic` as
agreement is.

## How to produce it

```
GET /dispatch/confirmations                       # the whole record
GET /dispatch/confirmations?since=…&until=…       # one shift, one week, one trial
```

Read by a supervisor or an engineer. Neither bound has a default: how much
history is enough to argue from is a judgement for the person arguing, not one
this project makes on their behalf. The window is bounded on when the question
was asked, so a proposal answered after the window closed still counts against
the shift it was asked about.

The rows come from ADR-014's technician trial, and from nothing else that
currently exists. **No plant data is required** - a supervisor pressing confirm
or reject on a demo world produces exactly the rows this reads (principle 4).

## What these figures will not be able to say

Two limits are structural rather than a matter of collecting more, and the
endpoint carries both on every response so that a number quoted out of this file
arrives with them attached:

1. **They say how often the two agreed, never whether either was right.**
   Nothing in this system records what a confirmed placement went on to cost. A
   supervisor who confirms everything to clear a screen is indistinguishable
   here from one who read each proposal, and a high agreement rate is as
   consistent with a scheduler nobody is checking as with one that is working.
2. **They are silent about the mode they would be used to argue for.** In
   `automatic` no proposal is written, so this record can describe the step but
   cannot say what would have happened without it.

## What this file will not contain

**A threshold, or a recommendation to turn the switch.** ADR-071 §8 refuses to
put a number in `policy.yaml` deciding when a plant may stop reviewing its own
work orders, and that refusal is the reason this measurement exists rather than
an obstacle to it: the figures belong to the advisor and the maintenance
department, with the evidence in front of them. This slice measures. It does not
decide, and neither does this file.

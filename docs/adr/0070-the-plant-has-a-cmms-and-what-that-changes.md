# ADR-070: The plant has a CMMS, and our own system is the floor rather than the plan

Answers the question
[ADR-012](0012-tickets-leave-through-an-adapter.md) refused to answer, and
narrows [ADR-069](0069-the-destination-is-a-name-in-policy-and-a-path-in-the-environment.md)'s
list of destinations to the one that matters.

## Context

ADR-012 is the only record in this repository whose decision was "do not decide
yet". It put layer 4 behind an interface because nobody knew whether the plant
already had a CMMS, on the argument that the answer changes the whole outbound
design and that waiting for it would cost a term.

On 2026-08-23 the advisor answered, in writing, three things at once:

  * the plant **has** a work-order system already;
  * the goal is to integrate with it, **or at least to have somewhere this
    ticket is displayed**;
  * how far the connection can actually go is not known, to him either.

ADR-012's premise is therefore closed, and closing it does not settle the
design - it replaces one unknown with a smaller and better-shaped one. The
question is no longer "is there a destination" but "how much of one is
reachable", and the two have different answers about what may be promised.

## Decision

### 1. The existing CMMS is the intended destination. Our own system is the floor

Not the first adapter because it was convenient, which is what `OwnSystemSink`
was in ADR-068. The advisor's fallback clause - *at least a place where this
ticket is displayed* - is a requirement, and it is one this project can meet on
its own with no access to anybody's system. It is therefore the thing that gets
finished, and the CMMS connection is the thing that gets **prepared**.

The order matters because it decides what happens if access never arrives. With
the floor built, the answer is a system a technician can work from - the
sentence the whole project is measured against. Without it, the answer is an
adapter pointing at nothing.

### 2. A CMMS adapter is written against a contract we define, and tested against a fake

`CmmsSink` joins the registry as `cmms`, an HTTP destination whose base address
and credential come from the environment, for the reason `TICKET_DIR` does
(ADR-069 §1): an endpoint is a deployment fact. What it sends is the `Ticket`
ADR-068 already defined, and what it expects back is an identifier.

The shape is **ours, and declared to be ours**. Writing an adapter against a
guess at somebody's SAP PM or Maximo interface would produce code that looks
finished, passes its tests, and is wrong in a way nobody can discover until the
day access is granted - which is worse than having no adapter, because it
consumes the slice that would otherwise have built the real one.

What it buys before then is real: it is the first destination outside this
process reachable only over a network, so it is the first one that can time out,
answer 500, or accept a ticket and lose it. ADR-068's `DeliveryFailed` path and
its at-least-once retry have until now been exercised only by a fake that was
asked to fail.

### 3. What may be claimed, and what may not

Until somebody with access confirms otherwise, the report and the demo say that
tickets leave through an adapter, that two destinations are implemented and a
third is prepared, and that integration with the plant's CMMS is **not
delivered**. A screenshot of our own screen is evidence of the floor, not of
the integration.

## Reasons

1. **The risk ADR-012 named has changed shape, not size.** It said the unknown
   was whether tickets should land somewhere else. The unknown now is how much
   of somebody else's system is reachable in a term, by one student, under an
   NDA - and that is not a question engineering can close by building harder.
   The defence is the same one ADR-012 chose and is now vindicated: keep the
   outbound layer cheap to change, and put nothing behind the interface that
   the scheduler can see.

2. **"At least a place it is displayed" is the requirement that was already
   met.** The web layer (ADR-058, ADR-061, ADR-065) shows a technician one job,
   its reason, its steps and its close path. That is the fallback clause,
   already built, and recognising it as the deliverable rather than as scaffold
   is the entire content of this record.

3. **A prepared adapter and a promised one are different artefacts.** The first
   is code with tests and a documented contract. The second is a sentence in a
   report. This project has one rule for that distinction everywhere else -
   evidence over intention - and layer 4 is not where to make an exception.

## Consequences

- ADR-012's "the answer changes the whole outbound design" turned out to be
  wrong in the useful direction: the answer arrived and the outbound design did
  not change at all. The port, the delivery record and the registry are what
  they were. That is what the interface was for, and it is worth saying in the
  report as a result rather than as a plan.
- `CLAUDE.md` describes layer 4 as carrying the most risk *because* the CMMS
  question is open. It is no longer open; the sentence to replace it with is
  that layer 4 carries the most risk because it is the only layer whose
  completion depends on somebody outside this project.
- The technician trial (ADR-014) gets more important, not less. If the plant's
  CMMS is where technicians already work, a screen of ours that nobody opens is
  the failure mode - and the only way to find that out is to put it in front of
  one.
- Nothing here changes what `policy.yaml` says today. `cmms` is added to the
  registry when the slice that builds it runs; a name in the config with no
  destination behind it is the failure ADR-069 §2 refuses.

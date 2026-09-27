# ADR-092: The owner tries it first, and the report says who tried it

Written on 2026-09-27, 25 days before the feature freeze.

## Context

[ADR-014](0014-report-and-technician-trial-are-reserved-unconditionally.md)
reserves time for a real technician to use the system, and
[`trial-protocol.md`](../trial-protocol.md) sets out how that trial runs.
Nobody outside the project has used the system yet. The plant is "still far
off" (ADR-082), and the advisor arranges any contact with it. No technician is
in reach on a date that leaves time to act on what they find.

The owner decided on 2026-09-27 that they will be the first person to use the
system, in place of waiting for a technician.

## Decision

1. **The owner runs the trial protocol as written**, playing both roles: the
   shift lead confirming proposals, and the technician working a job on a
   phone-sized screen. The criteria in `trial-protocol.md` stay unchanged,
   because they were written before anybody tried it.
2. **The agent does not coach during the run.** It gives the task list and
   the accounts beforehand, and nothing else until the run ends. Each question
   the owner has to ask, each time they get stuck, and each moment a screen
   misleads is written down as it happens.
3. **Results go to `docs/results/owner-trial.md`**, each finding with the
   screen, what was expected, what happened, and the PR that fixed it or the
   reason it was not fixed.
4. **The report names the trial for what it is**: a usability pass by the
   person who built the system. It is not evidence that a technician can work
   from the ticket. That criterion stays open, and the report says so.
5. If a technician becomes available before 12 November, they run the same
   protocol and the results sit next to the owner's. Nothing needs rebuilding.

## Reasons

A builder-run trial is weak evidence on the question ADR-014 cares about most.
The builder already knows what every field means. But it is strong evidence on
the questions that are cheap to fix before the freeze: a broken flow, a screen
that needs knowledge the screen does not give, a number without a unit, or a
Thai string that reads wrong. Finding those after 22 October means they reach
the report as defects instead of fixes.

Waiting for a technician who may never be in reach risks the end of term with
nobody having used the system at all. That outcome is worse than a named, limited
trial.

## Consequences

- `docs/results/confirmations.md` will get rows from the owner's run. Those rows
  measure the scheduler against its own author, and the file has to say that
  beside the numbers.
- "Nobody outside this project has used the system" stays true in `README.md`
  after the run. Only the wording around it changes.

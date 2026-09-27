# The owner's trial

[ADR-092](../adr/0092-the-owner-tries-it-first.md). The protocol is
[`trial-protocol.md`](../trial-protocol.md), and its criteria were written before
this run. The owner is the person who built the system, so this is a usability
pass, not evidence that a technician can work from the ticket.

## Run 1 - 27 September 2026: failed

**Verdict, in the owner's words:** the screens were confusing ("UX UI งงมาก"),
the people using it are Thai and need Thai that is easy to follow, and the
system has to be something people want to use. It did not pass.

What reading the live stack afterwards found, in order of how much each one
explains:

| # | Screen | Expected | What happened | Outcome |
|---|---|---|---|---|
| 1 | every ticket | why the job exists, in words a technician reads | "MC-012 unknown: SYM-002 detected by R-safety-interlock-open"; priority reasons in English; times in UTC | fixed: every sentence the backend writes is Thai, on the plant clock ([ADR-093](../adr/0093-what-a-person-reads-is-thai-and-familiar.md), #133) |
| 2 | shift lead, technician | proposals waiting to be confirmed; the technician's job once confirmed | both empty while the round said work was released: at `SIGNAL_SPEED=60` a thirty-minute confirmation window lasted thirty seconds | fixed: demos run at real speed with a head start into the scenario ([ADR-094](../adr/0094-a-persons-minutes-are-real-minutes-in-a-demo.md)) |
| 3 | home | the role's own work | a menu of "screens", with slice and ADR numbers on it | fixed: each role lands on its work, with tabs at the bottom (ADR-093) |
| 4 | line overview | one thing per screen | line, load, proposals, held work, health and gaps on one page | fixed: split into the shift lead's board, the line, and the engineer's gaps screen |
| 5 | technician | a job card to act on | a reason paragraph and a small start button | fixed: one job card with the machine large, facts in tiles, one large button, steps as a checklist, and a printable ticket |
| 6 | every screen | Thai labels | "playbook", ADR references, English demo names | fixed |

## Run 2

Not run yet. The same protocol against the rebuilt screens.

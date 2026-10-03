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

## Run 2 - 30 September 2026: failed

On main `3717406`, rehearsed 7/7 and left untouched for the trial.

**Verdict, in the owner's words:** the frontend does not pass yet - it may be
usable, but it is not something people would want to use - and several
decisions behind it should be looked at again for a better way.

| # | Screen | What the owner asked or saw | What reading the live stack found | Outcome |
|---|---|---|---|---|
| 1 | shift lead's line overview (`/overview`) | "what is this page for? I'm very confused" | a status page of station codes, symptom codes, component labels in English, and two blocks about what it cannot compute | fixed: ADR-122 - a line saying what it is for, machine and symptom in Thai, the caveats folded beside the figures |
| 2 | shift lead's board | "if you do not answer by 22:37 it goes back to the queue" - past 22:37 and nothing moved | the page was never re-read, and the expiry re-proposed the same pairing | fixed: ADR-120 §4 - the board re-reads itself, the sentence is gone |
| 3 | shift lead's board | "waited 1 h 30 min - true?"; "why does a job I did not send come back to the same place?" | the waiting time was true when written; a rejection was proposed again at the next round (ADR-071 §4) | fixed: ADR-120 §1-2 - "พักไว้ก่อน" lasts the shift, with a column and a way back |
| 4 | technician's step screen, WO-000015 | no repair steps | no approved playbook for that symptom; the screen named the manual and page (ADR-118) but drafting waits for an engineer to ask | fixed: ADR-121 - the first ticket of a symptom with no steps asks for a draft by itself |
| 5 | technician | "a job handed over and waiting for someone - where does it go?" | nowhere: `handed_over` was placed by no round and listed on no screen | fixed: ADR-120 §3 - back to the queue with its note |
| 6 | engineer's review | "drafting is not automatic, I have to write it myself - must the engineer know more than the technician?" | the engineer asks for each draft, and types the Thai for each step | partly: ADR-121 - the system asks for the draft and the engineer only checks it against the page; the Thai for each step is still typed |
| 7 | reporting a fault | "I reported it - where did it go?" | the report screen forgets the report once sent; it reached the shift lead's board as a proposal | fixed: ADR-122 - "เรื่องที่คุณแจ้งไว้" under the form, each with where it is |


## Run 3 - 3 October 2026: failed (agent, not a person)

An agent played each role through the real pages on a stack rehearsed 7/7 at
`a9df639`. This is a usability pass by software, not evidence that a person can
work from the system (ADR-092). Verdict against `docs/trial-protocol.md`: fail.
The pre-check found no live ticket carrying approved steps.

| # | Role | Screen | What happened | Outcome |
|---|---|---|---|---|
| 1 | shift lead, technician | cards | a live "14:56" beside a frozen "in about 41 minutes", and "not yet failed" after the time had passed | fixed: ADR-126 |
| 2 | shift lead | line vs board | the line's worst fault (MC-018 fan) had no ticket - a Finding the content-path check seeded without one | fixed: ADR-126, the check issues the ticket |
| 3 | technician, shift lead | handover | the job came straight back to the technician who had put it down | fixed: ADR-126 |
| 4 | operator | report | "ยังไม่เคยแจ้ง" directly under "รับเรื่องแล้ว" | fixed |
| 5 | operator | duplicate warning | only a ticket number | fixed |
| 6 | shift lead | board summary | "ปล่อยงาน 0 ใบ" beside four waiting cards | fixed |
| 7 | shift lead | board vs overview | queued work invisible until a round | fixed: a line under the waiting column |
| 8 | shift lead | board | a closed job vanished with no outcome or note | fixed: "เสร็จแล้วกะนี้" |
| 9 | engineer | review | "SYM-014" with no Thai name | fixed |
| 10 | engineer | review, gaps | a "not found" result listed as awaiting approval | partly: the gaps wording |
| 12 | everyone | after an action | no confirmation | fixed for close and handover |
| 13 | technician | steps | PDF in a new tab; PM called a symptom | partly: the PM wording |
| 11, 14-16 | - | - | cosmetic | open |

Worked well and kept: the one-card technician screen, the no-steps screen's "do
not guess" with a cited page, the engineer's figure check refusing a wrong Thai
torque, set-aside with a reason and a way back, the operator's status line, and
page times under 0.05 s.

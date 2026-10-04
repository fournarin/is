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
| 10 | engineer | review, gaps | a "not found" result listed as awaiting approval | fixed: its own section, "คู่มือไม่มีคำตอบ ต้องตัดสินใจ" |
| 12 | everyone | after an action | no confirmation | fixed for close and handover |
| 13 | technician | steps | PDF in a new tab; PM called a symptom | fixed: the cited page reads inside the job, one tap back to the step |
| 11, 14-16 | engineer | loops, notes | rule ids and SYM codes where names belong | fixed: names from `rules.yaml`, codes kept beside them |

Worked well and kept: the one-card technician screen, the no-steps screen's "do
not guess" with a cited page, the engineer's figure check refusing a wrong Thai
torque, set-aside with a reason and a way back, the operator's status line, and
page times under 0.05 s.

## Run 4 - 4 October 2026: failed narrowly (agent, not a person)

An agent played every role through the real pages on a stack rehearsed 7/7 at
`e666b23`, with the content path end to end: an engineer approved Thai steps and
the technician's open job got them at once. No error page and no dead end. The
verdict against `docs/trial-protocol.md` is fail on its third question - does
anything actively mislead - for the first three rows. Not evidence that a person
can work from the system (ADR-092).

| # | Role | Screen | What happened | Outcome |
|---|---|---|---|---|
| 1 | shift lead, technician | cards | every card said "แผนของกะให้เริ่มงานนี้ทันที", three of them for one technician | fixed: the plan's clause is "จัดตามแผนทั้งกะ", no claim about when |
| 2 | shift lead | board | a fan already past its threshold wore the pill "ปกติ" | fixed: "เกินเกณฑ์แล้ว · ความสำคัญปานกลาง", "แจ้งซ่อม · ..." for reports |
| 3 | shift lead | overview | "MC-012 ไม่มีอะไรค้าง" beside an urgent open report | fixed: the panel says it counts sensor signals only |
| 12 | technician | manual page | "page 2. 2. Remove" split into two "2." lines | fixed: a number starts an item only after a sentence ends |
| 16 | engineer | review | approve and dismiss showed nothing afterwards | fixed: a line saying what the press did |
| 21 | trial setup | roster | tech-2 and tech-3 had no published password | fixed: `docs/demo.md` lists them |
| 7 | shift lead | board | an urgent report losing 180 units sat third, under a medium job losing 37 | fixed: proposals listed by priority score |
| 14 | technician | close | closing at step 1 of 6 said nothing about the rest | fixed: the close screen says how many steps were never reached |
| 15 | engineer | gaps | a "not found" counted as a draft waiting for approval | fixed: counted and named apart |
| 10 | technician | card | tool names in English on an otherwise Thai card | fixed: ADR-130, tools rendered in Thai under the figure check |
| 17 | engineer | review | the skill typed as an id | fixed: ADR-130, chosen by its Thai name |
| 4 | shift lead | overview | "เสียบ่อยที่สุด MC-001 · เสีย 1 ครั้ง" for a predicted job closed before anything failed, over "0.0 วัน" of history | fixed: a prediction repaired before its detection counts as prevented, not failed; under a week the panel shows one sentence and no ranking |
| 5 | shift lead | board | "(เครื่องนี้มีใบงานเปิดอยู่แล้ว: WO-000011, WO-000014)" stayed after WO-000011 closed, and named numbers only | fixed: read with the ticket from what is still open, each named by machine and symptom |
| 6, 9, 13 | - | - | cosmetic: the remaining run-4 wording items | open |
| 8 | shift lead | board | banners said "ยืนยัน WO-000011 แล้ว" | fixed: "ยืนยันงาน MC-001 <symptom> แล้ว → <technician>", and the same for set aside, bring back and release |
| 11 | technician, engineer | no-steps screen, gaps | a PM job with no steps named the manual with no page, and `/gaps` never listed PM tasks | fixed: the ticket says to open the manual's maintenance schedule section and that no page is recorded for the task; `/gaps` lists PM tasks with nothing approved |
| 18 | engineer | loops | "ใบงานที่ปิดแล้วของ R-motor-temp-high มี 0 ใบ" after a predicted job for it closed | fixed: forecast jobs filed under `<rule>/trend` are gathered to their rule and named as not counted, and the sentence uses the rule's Thai title |
| 19 | operator | report | two reports on one machine looked the same in "เรื่องที่คุณแจ้งไว้"; no way to a fresh form after sending | fixed: each shows what was written; "แจ้งเรื่องอื่น" opens an empty form |
| 20 | operator | report | the duplicate warning listed a scheduled PM and ran the tickets into one paragraph | fixed: faults only, one line each by machine and symptom; a PM no longer refuses a report |

Worked well and kept: the figure check refusing a wrong Thai torque, the
technician's card and its banners, the no-steps screen, set aside and bring back,
the duplicate guard, the operator's status line, and no regression of run 3.

## Run 5 - 4 October 2026: failed narrowly (agent, not a person)

An agent played every role on a stack rehearsed 7/7 from `main` after ADR-130.
The content path passed end to end again, now with Thai tool names refused by
the figure check when a range was wrong ("5-50 Nm") and a skill chosen by its
Thai name. No fix of runs 1-4 regressed, except half of the `/gaps` count. The
verdict is fail on the protocol's third question for the first two rows. Not
evidence that a person can work from the system (ADR-092).

| # | Role | Screen | What happened | Outcome |
|---|---|---|---|---|
| 1 | technician, shift lead | work, board | an urgent report on a machine already stopped ranked below a predicted job on a machine still running | fixed: ADR-131, a predicted job's delay costs nothing until the stop it forecasts |
| 2 | shift lead | board | the handover note asked for an electrician; the lead could only confirm the proposed technician or set the job aside | fixed: ADR-132, "ให้คนอื่น" confirms to another rostered technician who holds the skill, recorded as a disagreement |
| 3 | engineer | review | the Thai tool fields came back empty after a refusal | fixed |
| 4 | engineer | gaps | the heading still counted a "not found" among drafts | fixed |
| 6 | shift lead | overview | the health ranking on minutes of history, and a prevented prediction counted as a failure | fixed (#183) |
| 10, 13 | engineer, technician | review, close | "ปิดใบนี้" ambiguous; the close screen's back link lost the step | fixed: "ปิดร่างนี้"; back to the step reached |
| 11, 12 | shift lead | board | "ไม่มีงานใหม่ที่จะเสนอ" beside waiting cards; a pill spilling out of a narrow column | fixed |
| 5, 7, 8, 9, 14 | - | - | a dismissal's note not shown to the technician, the line map ignoring open reports, the lockout page in English, an old playbook's English tools, machine codes on the report form | open |

Worked well and kept: the duplicate guard naming the open ticket in words, the
operator's status line following the job, the approval banner and the open job
adopting its steps at once, set aside and bring back, the handover note on the
receiver's screen, and no error page or dead end.

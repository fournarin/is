# Loop log

One line per unattended run, newest last. Kept so that a week of unattended work
can be read in a minute without opening GitHub.

Format: `YYYY-MM-DD HH:MM UTC · slice · outcome · PR`

- 2026-08-15 · loop set up · protocol and backlog written by hand, first run pending
- 2026-08-22 00:32 UTC · slice 9.1 (#51) · accept / start / hand over / close, and actual_minutes from the segments · #61, merged 02:18 by the next run
- 2026-08-22 02:40 UTC · none (by hand) · the log moves out of `.claude/`, where every write stopped a run on a permission prompt · —
- 2026-08-22 03:10 UTC · slice 10.1 (#55, by hand) · the web app exists: sign-in, the shell, and which screens a role is offered (ADR-058) · #63
- 2026-08-22 08:31 UTC · slice 9.2 (#52) · the two overrides get written down: a disagreement that changes nothing, a release that changes the next round (ADR-059) · #64
- 2026-08-22 10:20 UTC · slice 9.3 (#53) · `GET /overview/gaps`: symptoms with nothing to serve, ranked by events not firings (ADR-060); the review queue per model; playbooks whose manual changed · #65
- 2026-08-22 11:59 UTC · slice 10.3 (#57, by hand) · one job, its reason, its steps, and the objection that changes nothing (ADR-061) · #66
- 2026-08-22 12:21 UTC · slice 10.4 (#58, by hand) · closing in two taps, and the one thing kept on the device when the network drops (ADR-062) · #67
- 2026-08-22 14:32 UTC · slice 9.4 (#54) · `GET /overview/line`: stations in line order with their buffers, one marker per station, and the shift band taken from the round itself (ADR-063) · #68
- 2026-08-22 16:46 UTC · slice 10.2 (#56) · the review screen: draft beside the page it came from, edit and approve with the diff stored, send back as a redraft, and review time measured with no clock on screen (ADR-064) · #69
- 2026-08-22 17:10 UTC · slice 10.5 (#59, by hand) · the overview: the line to scale, held work named, and what the system cannot answer (ADR-065) · #70
- 2026-08-22 20:18 UTC · slice 11.1 (#60) · Loop 1: the median of `repair_minutes` over closed jobs, capped at ADR-022's 20%, proposing and never writing (ADR-066); false alarms counted per rule · #71, left for a person as the issue asks
- 2026-08-23 02:32 UTC · slice 11.2 (#75) · Loop 2: a separating threshold that would still have fired on every confirmed fault, capped at 10% (ADR-073); six named refusals, and the one-sidedness of the evidence carried on every proposal · #77, left for a person as the issue asks
- 2026-08-23 02:44 UTC · slice 13.1 (#76, by hand) · the rehearsal: one script that starts the stack and runs the four screen checks inside it, and the demo page (ADR-067); backlog refilled with #73-#76 after #71 merged. Its first run found three defects every CI tier had passed - the image had never contained the migrations, so the stack as shipped had never once started; three redirects pointed at the server's own bind address, which on a phone goes nowhere; and one check was passing because cookies ignore the port · #78
- 2026-08-23 03:14 UTC · slice 12.1 (#73, by hand) · layer 4 gets its port: `TicketSink`, `OwnSystemSink`, and a delivery record that is at-least-once rather than fire-and-forget (ADR-068); dispatch and work may not import sinks at all · #79
- 2026-08-23 06:52 UTC · slice 12.2 (#74, by hand) · a second destination: `FileSink`, a registry, and `sinks.destination` in policy.yaml with the path left to the environment (ADR-069); the same round against two sinks places the same work and lands it in two places · #80
- 2026-08-23 08:10 UTC · slice 14.1 (by hand) · the advisor's answers of 2026-08-23 land: the plant has a CMMS so our own screens become the floor rather than the plan (ADR-070); a round now proposes and the shift lead confirms, with the switch to automatic left as policy and its evidence as a table (ADR-071); machine health recorded before it is built (ADR-072). Building it found a defect three screen checks had passed - the technician's screen filtered a recomputed round, so a job vanished the instant a round wrote it, invisible because the rehearsal stops worker-runtime while the checks run · #84

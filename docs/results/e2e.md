# End-to-end flows and the accessibility scan

Run on 2026-11-18 at `a6c0c95`, against the repo-v2 stack (built web server
and API) over a freshly reset demo world, in Chrome
([ADR-144](../adr/0144-end-to-end-flows-and-an-accessibility-scan-in-the-repo.md)):

```bash
E2E_WEB_URL=http://localhost:3001 DATABASE_URL=postgresql://.../pdm_web_check_v2 npx playwright test
```

## The flows: 7 of 7 passed

| Spec | What it does | Result | Time |
|---|---|---|---:|
| `a11y.spec.ts` - sign-in | axe on the sign-in page | pass | 2.8 s |
| `a11y.spec.ts` - operator report | axe on the station list and the form | pass | 6.3 s |
| `a11y.spec.ts` - shift lead board | axe on the board at 1280 and 390, and on a drawer | pass | 8.9 s |
| `a11y.spec.ts` - technician screens | axe on the job, a step, the manual page, close and handover | pass | 13.8 s |
| `board.spec.ts` | confirm the job the board puts first; set the next one aside with a reason | pass | 7.4 s |
| `report.spec.ts` | station → machine → three answers → a 3200 × 2400 photo → send, answering "a different problem" when the machine already has a report | pass | 5.0 s |
| `technician.spec.ts` | from the job page, every energy step as the screen offers it (switch off, lock, wait, zero-energy check, the plant's restore checks, lock off), then the close sent **offline**, kept on the phone, and delivered when the network returns | pass | 56.1 s |

Every flow checks the database as well as the screen: the order is `assigned`
after the confirm; the set-aside reason is on the proposal and the order is back
`queued`; the report is a `manual` order on the right machine with one photo
under 1 MB (shrunk on the phone); no lock is left on after the restore step;
the order stays `in_progress` while the close is queued and is `closed` after.

### What the flows found

**A restore step held "next" shut on the screen.** On the MC-018 job (10
steps), taking the lock off at step 9 made the screen say "step 2 is not
finished - put your lock on" and disable "next", although the API would have
accepted it: the server already treats the restore step being worked as
restoring its points (ADR-137, N4), and the screen's copy of that rule did
not. A technician would have been stuck one step from closing. Fixed in
`web/lib/energy.ts` with a unit test (ADR-144 §4). The screenshot checks never
reached it because they moved the job forward through the API.

## The accessibility scan: 0 violations on 11 screens

axe-core 4.13.0, WCAG 2.2 A and AA rules (`wcag2a`, `wcag2aa`, `wcag21a`,
`wcag21aa`, `wcag22aa`). A serious or critical violation fails the test.

| Screen | Violations | Rules passed | Left for a person (axe "incomplete") |
|---|---:|---:|---|
| sign-in, 390 | 0 | 22 | - |
| report, station list, 390 | 0 | 24 | colour contrast, 55 elements |
| report, form, 390 | 0 | 28 | colour contrast, 69 elements |
| board, 1280 | 0 | 25 | - |
| board drawer, 1280 | 0 | 30 | - |
| board, 390 | 0 | 25 | - |
| technician job, 390 | 0 | 29 | colour contrast, 18 elements |
| technician step, 390 | 0 | 24 | colour contrast, 26 elements |
| manual page, 390 | 0 | 20 | - |
| close, 390 | 0 | 24 | colour contrast, 10 elements |
| handover, 390 | 0 | 24 | colour contrast, 4 elements |

The first scan also left `aria-prohibited-attr` for review: station tiles and
the plant clock carried an `aria-label` with no role. They now have one
(`img`, `group`), and the rule no longer appears.

"Incomplete" colour contrast is text axe could not measure, usually over a
layered or translucent background (the sticky bars, the chips). The design
system's own check measured every text element of the same screens at 7:1 or
more against its computed background (`shots/v2/final/*/measure.json`); axe
did not confirm or contradict that.

## Not tested

Keyboard-only use, 200 % zoom, greyscale, a screen reader, and Chrome 109 (the
plant's oldest browser) - in the backlog. A machine can test the rules above;
it cannot say a screen makes sense.

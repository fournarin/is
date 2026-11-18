# ADR-144: End-to-end flows and an accessibility scan in the repository

Written on 2026-11-18. Phase 1 of the owner's last week (items D and E, and the
measurement in C). Decided by the agent on the owner's delegation (ADR-090).
axe-core was approved by the owner as Q10 (design/research/oss-audit.md).

## Context

The screens of the second frontend were checked by screenshots, measurements
of the rendered page and the Python screen checks (`web/check-*.py`), all
against a running stack, and none of it walked a whole job the way a person
does: report with a photo, confirm on the board, isolate, wait, verify,
restore, close. Nothing ran an accessibility engine over the screens.

## Decision

1. **Two dev dependencies, pinned exactly**: `@playwright/test` 1.65.1 (the
   same Playwright the screenshot tools already use from Python) and
   `axe-core` 4.13.0 (already in the tree through `eslint-plugin-jsx-a11y`,
   now named directly). Neither ships in the image: they are devDependencies,
   and the browser is the installed Chrome (`channel: "chrome"`), so nothing is
   downloaded.
2. **`web/e2e/`** holds the flows, run in file order on one worker because
   they change a shared world: `a11y.spec.ts` (axe over every v2 screen,
   WCAG 2.2 A/AA tags, serious or critical fails, the rest written to
   `test-results/axe.json` with the rules that passed and those axe left for a
   person), `board.spec.ts` (confirm the top job, set the next aside with a
   reason), `report.spec.ts` (station, machine, three answers, a photo larger
   than the phone's 1600 px, send, including the "already reported" answer)
   and `technician.spec.ts` (every energy step tapped as offered, the wait
   moved back in the database rather than slept, the close sent offline and
   delivered when the network returns). Each checks the database as well as
   the screen.
3. **`web/measure/before-after.spec.ts`** with its own config counts actions,
   visible words (the browser's Thai word segmenter) and screens for three
   tasks, run once against the v1 build (f1499b8) and once against v2 on the
   same reset world and API. A count, not a usability result.
4. **The restore step no longer reopens the isolation behind it on the
   screen.** `firstUnfinished` in `web/lib/energy.ts` now counts the restore
   step being worked as restoring its points, as the server's
   `first_unfinished` already did through `restoring` (ADR-137, N4). Before,
   taking the lock off at step 9 of 10 made step 2 ask for that lock again and
   held "next" shut on a step the API would accept. Found by the technician
   flow; a unit test pins it.
5. **Labelled generic elements get a role**: station tiles `role="img"`, the
   plant clocks `role="group"`, so their `aria-label` is allowed
   (axe `aria-prohibited-attr`, left for review).
6. **Sign-in is drawn in the design system** (ADR-133): the dark plate with a
   Lucide wrench, 56 px fields, the primary button, errors as a callout. Same
   form fields and action, so `web/check-sign-in.py` is unchanged.

## Consequences

- The flows need a seeded world with one job under way that isolates energy
  and proposals on the board; they look the job up instead of naming it,
  because the round that places work is not the same twice.
- axe's verdicts cover what a machine can test. Contrast it could not decide
  (text over layered backgrounds) is listed, not claimed; keyboard order,
  200 % zoom, greyscale and screen-reader sense remain untested (backlog).

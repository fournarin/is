# Before and after: the same three tasks on the old and new screens

Measured on 2026-11-18 by `web/measure/before-after.spec.ts`
([ADR-144](../adr/0144-end-to-end-flows-and-an-accessibility-scan-in-the-repo.md)).
Raw records: [before-after.json](before-after.json).

**This is a measurement of the screens, not a usability result.** Nobody used
them while it ran: a script tapped what each version offers for the task, the
shortest way it offers it. It counts what the trial technician said was wrong
with the first version - too much to read and too many places to look - and
says nothing about whether a person finds the second one easier.

## How it was run

- **v1** is the web build at `f1499b8` (4 October, the build the trial
  technician used); **v2** is the build at `a6c0c95`.
- Both ran against **one API and one database** (the repo-v2 backend, a
  superset of v1's), reset to the same seeded demo world before each version.
  Same accounts, same jobs, same machine (MC-001) reported.
- Each task starts on the role's own home screen after signing in. Sign-in is
  not counted.
- **Actions**: a tap, a pick from a list, a field typed into, a file chosen.
  Characters typed are counted separately.
- **Words**: the visible text of the page (`innerText`, so closed sheets and
  hidden panels do not count) split by the browser's Thai word segmenter
  (`Intl.Segmenter("th")`), counted on arrival at each screen.
- **Screens**: distinct addresses passed through, the home screen included. A
  form that answers on the same address is one screen.

## Results

| Task | Version | Done | Actions | Typed characters | Screens | Words on each screen | Words in all |
|---|---|---|---:|---:|---:|---|---:|
| Shift lead confirms the job the board puts first | v1 | yes | 1 tap | 0 | 2 | 955 → 907 | 1,862 |
| | v2 | yes | 1 tap | 0 | 2 | 213 → 213 | 426 |
| Technician opens the job, then the manual page of step 1 | v1 | yes | 2 taps | 0 | 3 | 206 → 273 → 140 | 619 |
| | v2 | yes | 2 taps | 0 | 3 | 264 → 197 → 143 | 604 |
| Operator reports a machine with a photo | v1 | **without the photo** | 4 (1 pick, 1 typed, 2 taps) | 10 | 1 | 280 | 280 |
| | v2 | yes | 6 (5 taps, 1 photo) | 0 | 2 | 250 → 330 | 580 |

In both report runs MC-001 already had an open report, so both versions asked
"is this a different problem?" and one action of each row is that second
press.

## What it says

- **The board is where the text went.** The shift lead's screen carries 78 %
  fewer words (955 to 213) for the same one tap, because the reasons, costs and
  people moved behind a tap on the row (ADR-139, ADR-141).
- **The technician's path did not get shorter.** Same two taps, about the same
  words in all (619 against 604). The job page now has *more* words than before
  (264 against 206): the history line, the tools and the photo from the reporter
  were added to it. The step page is shorter (197 against 273).
- **The report takes more taps and no typing.** v1 asked for a machine from a
  list and a typed description (10 characters here, more in practice); v2 asks
  the station, then three questions by tap, and takes a photo, which v1 could
  not do at all. More actions, no keyboard: whether that is faster for someone
  in gloves is a question for a trial, not for this count.

## Limits

- One run per version; the counts are deterministic for this world, the words
  depend on the data shown (names, numbers of jobs).
- A tap on a photo button stands for opening the camera and taking the picture,
  which is more than one touch on a real phone.
- The script knows where everything is. A person looking for the manual link
  or the confirm button is what a trial measures, and none was run on v2.

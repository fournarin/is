# Traceability: requirement -> screen -> test (Phase 4, REQ-A-02)

Build: repo-v2 `feat/frontend-v2` @ a8d228a (published to ~/is 2026-11-18). Requirements: design/REQUIREMENTS.md
(107 REQs). Written by Claude Code at the end of FINAL PLAN window 2. Statuses are what the build and its evidence
show today, not what the spec intended; "not verified" means nobody checked it this window - it may still hold.

**Status**
- **Built**: in the new-look app, with the evidence named.
- **Partial**: built in part; the missing part is named.
- **Spec**: designed in design/system (mockup PNGs, usable as figures labelled "design"), not built. Cut by the
  FINAL PLAN (engineer screens, line overview).
- **Old UI**: works on a screen not rebuilt yet (pre-redesign look).
- **Future**: neither built nor designed; future work in the report.
- **Report**: evidence for the written report (Cowork / owner).

**Evidence codes**
- **M** = measure records in `shots/v2/final/<dir>/measure.json`: no h-scroll, no clipped or overlapping text,
  phone text >= 18 px, taps 56 phone / 48 desk, contrast >= 7:1. Dirs: `set1`, `set2` (technician), `board`,
  `report`.
- **SS** = screenshot in the same dirs, at 360x640, 390x844 and 1280x800 (board also 1024 and 1920).
- **PT** = pytest file under `tests/api/`. **WT** = web unit test under `web/lib/`.
- **WC** = screen check `web/check-*.py`, which drives the real web server without JavaScript.
- **UT** = usability test, the friends' test and พี่คง round 2, ~25-28 Nov, still pending.

## 3.1 General (G)

| REQ | In short | Status | Screen | Evidence |
|---|---|---|---|---|
| G-01 | No emoji; one SVG icon set, each icon with visible words | Partial | new-look screens use Lucide + drawn signs; old screens (review, overview, gaps) still have emoji | SS set1/set2/board/report |
| G-02 | No internal codes as the main text; MC-xxx only beside a name | Built | all new-look screens | SS; WC check-the-technicians-screen |
| G-03 | Plant clock, one time format | Built | `Clock`, `plantTime` | SS; WC technicians |
| G-04 | Fixed priority words, shapes and colours | Built | `Prio` (shape + word) | SS set1, board |
| G-05 | Colour by meaning only | Built | v2.css tokens (amber = forecast/over, red = stop) | SS; design/system/contrast.py |
| G-06 | Phone text >= 18 px, desk >= 15 px | Built | all new-look screens | M (every record minFont 18 on phones; board desk minFontReal 15) |
| G-07 | Contrast >= 7:1 for content | Built | all new-look screens | M contrast (min 7.05, set3) |
| G-08 | Layout by device (no bottom bar >= 1024, 360/390 phones) | Built | board 360-1920; technician and report are phone-first, centred 600 px on desk | M board@1024/1280/1920; SS |
| G-09 | Nothing sticky over steps, warnings, buttons or fields | Partial | sticky "ต่อไป" on energy steps and sticky send on /report cover the last line under them on the first view, then scroll clear (w1 check note 5) | SS set2 tech-step.360x640, report.390x844 |
| G-10 | Feedback within 1 s; button disabled while sending | Built | "กำลังส่ง..." on report and close; done lines (ADR-126) | WC reporting, technicians |
| G-11 | Permanent "ข้อมูลจำลอง" banner | Built | `PhoneFrame`, board | SS (every phone shot) |
| G-12 | Backend sentences shown as written | Built | reason, priority_reason, assigned_because, where | PT test_the_ticket_explains_itself; code review |
| G-13 | Empty pages say why and what next | Partial | /work empty, board tabs; not every page re-checked | SS set1 tech-job-empty (spec) |
| G-14 | No dead ends: wrong role goes to its own page | Built | `/` redirects by role (ADR-093); `NotYours` | WC check-sign-in (44/44), reporting (operator lands on /report) |
| G-15 | No sentence repeated >= 3 times on a page | Built | - | not measured this window; refresh round 3 removed the repeated forecast |

## 3.2 Safety (H)

| REQ | In short | Status | Screen | Evidence |
|---|---|---|---|---|
| H-01 | Thai and the manual's English together | Built | step card: Thai, then "ต้นฉบับ หน้า N" | SS set1 tech-step-normal |
| H-02 | Never guess a safety step from words | Built | only `Step.kind` set by the approver (ADR-135) | PT test_isolation_point_by_point; WT energy.test.ts |
| H-03 | Critical steps marked only when the backend says so | Built | `KindHeader`, ISO signs | SS set2 tech-step, -verify, -restore, -hot |
| H-04 | Isolation, verify and restore confirmed point by point at the server | Built | energy step points | PT test_isolation_point_by_point (TestTheJobWaitsForEachPoint, TestNothingIsConfirmedAhead); WT energy.test.ts |
| H-05 | OSHA order: isolation -> verify; restore as its own step | Built | steps page; next link names the next point (w1 fix 2) | PT TestRestoring, TestARestoreStepWithTwoPoints; WT energy.test.ts (`nextLine`) |
| H-06 | Close and handover ask the lock state | Built | tech-close-locked: one line + "ทำไม" | PT TestClosingSaysWhatIsLocked; SS set2 tech-close-locked |
| H-07 | Lock register, carried over between shifts | Partial | lock banner, "ล็อกอยู่" board tab; issued-padlock list and abandoned-lock record not built | PT TestEveryoneHangsTheirOwnLock, TestTheCarryOver, TestOneMachineOneWriter |
| H-08 | No approved steps: say so, point to the manual page | Built | tech-noplaybook | PT test_what_the_system_cannot_answer, test_a_pm_job_without_steps; SS set1 tech-noplaybook |
| H-09 | ECP sentence approved by EHS, from config | Not verified | - | - |
| H-10 | playbook_warning on every step and the print | Partial | shown on the job page; every step not verified this window | SS set1 |
| H-11 | Manual page that fails to load says which, with retry | Not verified | tech-manual | - |
| H-12 | No cars-lost or hurry text on the technician's steps | Built | steps page shows none | SS set2 |
| H-13 | ISO 7010 signs, drawn to ISO 3864, Thai signal words | Built | `signs.tsx` | SS set2 tech-step-hot |

## 3.3 Technician (T)

| REQ | In short | Status | Screen | Evidence |
|---|---|---|---|---|
| T-01 | First screen of "งานของฉัน" without scrolling | Built | /work | M set1 tech-job (primary above the fold at 390x844); SS |
| T-02 | Taps >= 56 px, 8 px apart; primary button full width | Built | all technician and report screens | M (minTap 56 on every phone record) |
| T-03 | Tools, time, skill and people on the card | Built | /work "เตรียมก่อนเดินไปเครื่อง" | SS set1 tech-job.390.full |
| T-04 | Accept and start in <= 2 taps, double tap harmless | Built | "รับงานและเริ่มทำ" (one tap) | WC check-the-technicians-screen (60/60); PT test_working_a_job |
| T-05 | One step at a time, manual named | Built | /work/[ref]/steps | SS set1 tech-step-normal |
| T-06 | Manual page inside the job, zoom, back in one tap | Partial | tech-manual; pinch-zoom not verified on a device | SS set1 tech-manual |
| T-07 | Step progress kept on the device | Not verified | - | - |
| T-08 | Step reached recorded at the server | Built | `work_step_reached` (migration 0020) | PT test_working_a_job, test_isolation_point_by_point |
| T-09 | Four big outcome buttons on close | Built | tech-close | SS set2 tech-close; WT close.test.ts |
| T-10 | Confirm page that summarises close / handover | Built | tech-close-confirm, tech-handover | SS set2 |
| T-11 | Nothing typed is lost offline | Partial | a close is kept on the phone (`pending-closes`); a report is not queued offline yet | WT pending-closes.test.ts; SS set1 tech-offline |
| T-12 | "งานของฉัน" refreshes itself, "new job" bar | Partial | `KeepFresh`; vibration not built | - |
| T-13 | "ไม่เห็นด้วยกับลำดับ" with ready reasons | Built | tech-states-disagree sheet | PT test_the_two_overrides (TestDisagreement); SS set1 |
| T-14 | Print fits one A4, black and white | Old UI | /work/[ref]/print not re-shot in final | spec PNG tech-print |
| T-15 | Revision, approver, role and time on steps | Built | `Approved` line | SS set1; PT test_what_the_job_page_shows |

## 3.4 Shift lead (S)

| REQ | In short | Status | Screen | Evidence |
|---|---|---|---|---|
| S-01 | Top of the board answers without scrolling | Built | line strip + "รอคุณตัดสินใจ N" + focal card | M board (focal confirm 617 at 360x640 after fix 1, 710 at 390x844, 364 at 1280) |
| S-02 | Pending work one line per job | Built | one-line rows "name · N คัน" (ADR-140 replaced the table) | SS board |
| S-03 | "Cars lost if it waits" as its own number | Built | focal card and rows | PT (ADR-141 API tests); SS board |
| S-04 | Confirm in one click, 5 s undo | Partial | confirm is one click; undo not built (the API has no undo) | WC check-the-overview-screen (33/33) |
| S-05 | Give to somebody else, with what each holds | Built | "ให้คนอื่น · พักไว้" menu (ADR-132) | SS board-menu |
| S-06 | Set aside with ready reasons | Built | same menu, reason required | SS board-menu; PT test_the_two_overrides |
| S-07 | Work in progress grouped by technician | Built | "ช่างในกะ" tab | SS board-people |
| S-08 | Load per technician (status, minutes committed / free) | Partial | jobs in hand shown; free minutes not built (no endpoint) | SS board-people |
| S-09 | Open the ticket read-only from any row | Partial | drawer shows the work order; full read-only steps not verified | SS board-drawer |
| S-10 | Tablet landscape | Built | board at 1024 | M board@1024x768 |
| S-11 | Shift handover page | Future | - | - |
| S-12 | No work lost silently (expired, set aside) | Partial | tabs "ระบบกันไว้ก่อน", "คุณพักไว้"; expired list not verified | SS board-aside |
| S-13 | Confirm several rows at once | Future | - | - |
| S-14 | Wall mode readable at 3 m | Partial | type x1.25 at >= 1600 px; ~200 px blank at the bottom of 1920 (w1 check B5) | M board@1920x1080 |

## 3.5 Engineer (E)

All engineer screens were cut from the build by the FINAL PLAN. They are designed (design/system/png/eng-*), and the
pre-redesign review, gaps, loops, notes and health screens still work in the old look.

| REQ | In short | Status | Evidence |
|---|---|---|---|
| E-01 | Side-by-side draft review | Spec; Old UI | spec eng-review; WC check-the-review-screen (45/45, old UI) |
| E-02 | Highlight only where `locate()` found the text | Spec; Old UI | PT test_the_review_screen |
| E-03 | Numbers and units emphasised in both languages | Spec | spec eng-review |
| E-04 | Every step names document, edition, page | Spec; Old UI | PT test_the_review_screen |
| E-05 | Edit Thai line by line | Spec; Old UI | WC review |
| E-06 | Approve only when every step is checked | Spec; Old UI | WC review |
| E-07 | Unapproved draft labelled | Spec; Old UI | PT test_review_queue |
| E-08 | "No steps yet" split into 4 reasons | Spec; Old UI | spec eng-gaps |
| E-09 | Loops as a table | Spec; Old UI | PT test_the_improvement_loops |
| E-10 | Machine health as a sortable table | Spec; Old UI | PT test_machine_health_on_the_overview |
| E-11 | Filter technician notes | Spec; Old UI | WT notes.test.ts |
| E-12 | Audit trail by WO number, printable | Spec | spec eng-audit |
| E-13 | Open orders affected by an approval; refuse steps with no evidence | Spec | - |
| E-14 | Safety-word hints only on the review page | Spec | - |

## 3.6 Report a fault (P) - set 4, this window

| REQ | In short | Status | Screen | Evidence |
|---|---|---|---|---|
| P-01 | Report with no typing; send visible at 390x844 | Built | /report?machine= : stopped? -> what seen -> send (3 taps from QR); sticky send bar | SS report.390x844 (send visible); M report (in flow); WC check-reporting-a-fault (23/23, no JavaScript) |
| P-02 | Pick by station or partial code; `?machine=` preselects | Partial | station list -> machine -> form; `?machine=` works; typing part of a code is not built | SS report-stations; WC reporting |
| P-03 | Floor name beside the code | Partial | station name from plant.yaml (`/machines.station_name`); a machine nickname is not in config | SS report |
| P-04 | "Is the machine stopped?" as its own question | Built | question 1, stored first in the description (field = Phase B) | WC reporting; PT test_reporting_a_fault |
| P-05 | Four stages, same words everywhere | Built | track under "เรื่องที่คุณแจ้งไว้" | PT test_the_track_has_four_stages_and_names_nobody; SS report-sent |
| P-06 | No technician names to the operator | Built | the operator's list never shows `where` | PT (stages carry no names); code; SS report-sent |
| P-07 | Warn about open work on the chosen machine | Partial | own open report shown on opening the form; others' open work named on the first send (ADR-077 refusal) | SS report-already, report-refused; WC reporting |
| P-08 | Keep "ระบบนี้เป็นคิวงาน ไม่ใช่ช่องทางฉุกเฉิน"; maintenance phone | Partial | sentence kept; phone number not configured | SS report |
| Q15 photo | One photo, shrunk, stored with the report | Built | photo question; "รูปจากคนแจ้ง" on the job page | PT TestOnePhotoWithTheReport (5 tests); WC reporting step 6; shoot_report: 4000x3000 895 KB -> 130 KB, kept through a refusal; SS report-answered, tech-job-photo |

## 3.7 Line overview (L)

Cut from the build. The calm line overview is a spec (design/system line.py; shots/v2/round3/spec/line-overview*).

| REQ | Status | Evidence |
|---|---|---|
| L-01 station plan in seq order | Spec; Old UI | spec line-overview; PT test_the_line_as_the_overview_draws_it |
| L-02 open work never shown as "no signal" | Spec; Old UI | PT test_the_line_as_the_overview_draws_it |
| L-03 ETA date + time + ± | Built on technician screens; Spec on the overview | SS set1 "ถึงเกณฑ์ราว ... ±2 ชม." |
| L-04 shift load in words with its base | Spec; Old UI | WC check-the-overview-screen |
| L-05 ETA in shift language | Future | - |
| L-06 mini trend | Future | - |

## 3.8 IT and reliability (I)

| REQ | In short | Status | Evidence |
|---|---|---|---|
| I-01 | Nothing loaded from outside | Built | fonts self-hosted (next/font local); not re-audited this window |
| I-02 | Chrome/Edge 109, Android Chrome 100 | Future | cut (FINAL PLAN) |
| I-03 | Fast 3G budget | Future | not measured |
| I-04 | "Updated hh:mm:ss" and a stale bar | Partial | board stale bar when offline; per-page time not everywhere |
| I-05 | Idle sign-out by role | Not verified | - |
| I-06 | Sign out in one tap clears the session | Built | WC check-sign-in step 4 |
| I-07 | Keyboard, visible focus, 200 % zoom, lang="th" | Partial | focus ring and SheetFocus (Escape, focus return); 200 % zoom and full keyboard pass not tested (axe-core cut) |
| I-08 | Names only as far as a role needs | Partial | P-06 holds on /report; other screens not audited |
| I-09 | Sign-in autocomplete, show password, Caps Lock | Old UI | sign-in not rebuilt |
| I-10 | Rights checked at the API | Built | PT (403s across tests/api; photo: only the reporter may attach) |
| I-11 | Server-enforced session lifetime | Not verified | - |

## 3.9 Evidence for the report (A)

| REQ | Status | Where |
|---|---|---|
| A-01 source type on every REQ | Built | REQUIREMENTS.md "ที่มา" column |
| A-02 this trace table | Built | this file |
| A-03 >= 8 design rationales | Report | design/concepts/V rationale, ADR-133..142 |
| A-04 baseline on the old UI | Built | shots/before; trial-kong 2026-11-17 (design/research/trial-kong-2026-11-17.md) |
| A-05 pass/fail criteria written first | Built | REQUIREMENTS.md acceptance column; design/review/PANEL.md |
| A-06 owner / agent runs not called user tests | Report | Cowork, report chapter |
| A-07 demo seed and capture scripts | Built | tools/seed_world.py, seed_board.py, seed_trial.py, shoot_*.py |
| A-08 phone shots at viewport size | Built | shots/v2/final (viewport PNG + .390.full) |
| A-09 heuristic review by non-designers | Built | design/review/* (fresh reviewer agents, w1-check) |
| A-10 disclose AI use | Report | Cowork, window 3 |
| A-11 demo script, seed and video | Partial | tools/trial_stack.sh (one-command world); video not made |

## Counts

Of the 107 requirements: built 53, partial 21, spec 17, future 6, not verified 5, report 3, old ui 2. Counted from the status column (the part before ';'), so a row like "Spec; Old UI" counts as spec. The photo row (Q15) is extra and not counted.

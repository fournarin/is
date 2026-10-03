# ADR-126: What the third trial found

Written on 2026-10-03, from usability trial run 3. An agent played each role
through the real pages on a stack rehearsed 7/7 at `a9df639` (see
`docs/results/owner-trial.md`, run 3). It is not evidence from a person (ADR-092).
What it found is listed and fixed here.

## Blockers

1. **A card still showed two times for one forecast.** The live ETA (ADR-123)
   sat beside a "why first" sentence frozen at proposal, "ในอีกราว 41 นาที". After
   the expected time passed, the card still said "ยังไม่เสีย".
   - The ranking sentence no longer prints a time: "พยากรณ์ว่าใกล้ถึงเกณฑ์",
     "รอในคิวนานกว่างานอื่น".
   - Once a forecast's time has passed, the card reads "เลยเวลาที่คาดว่าจะถึงเกณฑ์แล้ว
     … ให้ตรวจเครื่องโดยเร็ว" and its tag "เลยเวลาที่คาด · ตรวจเครื่อง".
   - The overview no longer prints "อีกราว -0 ชั่วโมง".
2. **The worst fault on the line had no ticket.** Not a system defect.
   `check-the-content-path.py` seeds a Finding for MC-018 and wrote no ticket, so
   every rehearsed stack carried a fault nobody was sent to. The check now issues
   the ticket the trigger loop would, and asserts that approving the playbook
   fills it with the approved steps (ADR-102). A rehearsed stack therefore has a
   ticket with approved steps, which the trial protocol's pre-check requires.
3. **A job put down came straight back to the same technician.** A round no
   longer offers a handed-over job to anybody who worked it (`put_down_by`),
   greedy and CP-SAT alike. With nobody else on shift it waits as "รอช่างว่าง"
   for the lead.

## Confusions fixed

- The operator's list of reports updates the moment a report is sent; before,
  it said "ยังไม่เคยแจ้ง" under "รับเรื่องแล้ว" until a reload.
- A duplicate-report warning names what each open ticket is about, not only its
  number.
- The board's summary says what the next round will propose instead of
  "ปล่อยงาน N ใบ", and the waiting column says how many more the next round will
  propose.
- A "เสร็จแล้วกะนี้" column on the board lists what was closed this shift, with
  outcome, who and the technician's note (`GET /work-orders/finished`). The
  in-progress column is renamed "ส่งถึงช่างแล้ว", because it also holds jobs not
  yet started.
- Closing and handing over end on a line saying what happened.
- The review queue and the draft page name the symptom in Thai, with the code and
  model beside it.
- A PM job without steps says "สำหรับงานนี้", not "อาการนี้".
- The gaps panel says a draft is waiting for an engineer to look at, rather than
  "รออนุมัติ" for a "not found" result that cannot be approved.

## Not done here

- The cited manual page still opens as a PDF in a new tab.
- Two cards for two faults on one machine are not merged into one visit.
- Raw rule identifiers remain on the improvement-loop screen.

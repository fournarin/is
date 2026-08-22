# ADR-064: What a reviewer may change, and what the review screen records

## Context

ADR-003 is the most expensive constraint in this design: no LLM writes repair
text at runtime, and every drafted playbook passes an engineer before a
technician can be given it. Everything else bends around that sentence - the
worker split (ADR-026), the network boundary (ADR-029), the two tables
(ADR-038), the span-selection and figure gate (ADR-037).

All of it rests on the engineer actually reading the draft. Nothing in the
system has been able to say whether that happens. The review queue existed as
two endpoints and no screen: a proposal could be approved with one POST and no
evidence in front of anybody, and the row that came out looked identical either
way. A control nobody can observe is a control that has already decayed and not
told anybody.

Slice 10.2 builds the screen. Four questions had to be answered first, and none
of them is a layout question.

1. **What is the reviewer allowed to change?** A draft is usually nearly right.
   "Approve or reject" makes the nearly-right case expensive, and expensive
   review is review that gets waved through.
2. **What is the fourth button?** Approve, edit-and-approve and dismiss leave no
   way to say "this is the wrong procedure, try again" - and dismissing is not
   that, because a dismissed symptom is one nobody wants a playbook for.
3. **How is review time measured without a timer?** The report needs
   minutes-per-proposal and the edit rate. A clock on screen would buy a better
   number and a worse review, from somebody reading safety-critical text.
4. **What counts as evidence beside the draft?** ADR-019 serves the manual at a
   page. If a reviewer has to open a PDF for every proposal, question 3's number
   climbs until approval is a formality.

## Decision

### 1. A reviewer rewords steps. They do not change the shape or the citation

"Edit and approve" sends the text of every step, position for position. Three
consequences, all deliberate:

- **The count cannot change.** Adding or dropping a step is refused. ADR-037 §4
  already refused the drafter a trimmed procedure, on the grounds that one reads
  as complete and the reviewer cannot see the hole; there is no argument for
  allowing the same thing to the person the drafter is checked by. A draft with
  the wrong steps is sent back (§2).
- **`source_doc`, `page` and `confidence` are carried across untouched, and no
  path in the system lets a person type them.** A step whose citation may be
  retyped is a step that says what somebody wished the manual said, and
  invariant 4 would then be true of the field and false of the fact.
- **The difference is stored on the proposal** as `edits`: index, before, after.
  The playbook table is overwritten on the next approval (ADR-018), so the
  question "what did a person change here, and which person" has to be answered
  on the proposal or nowhere.

### 2. The figure gate is not re-run over a human edit

ADR-037 §2 requires every figure in a drafted step to appear in the chunk it
cites. That check is about a model quoting a torque the page does not carry. The
engineer approving is the authority ADR-003 put in the model's way, and refusing
their correction on the strength of the model's check would make the reviewer
the least-trusted party in the system.

What replaces it is attribution: the edit is stored, the approval names the
approver and the role held at that moment (ADR-024), and a closed work order
carries the whole thing in its `playbook_snapshot` (ADR-018). "An engineer wrote
this figure" is a defensible provenance; it is a different one from "the manual
says so", and the two are distinguishable in the record.

### 3. Send back is a refusal and a request, in one transaction

A fourth status, `sent_back`, and the reviewer's note becomes the question the
next drafting job is asked (ADR-039 §7). Both commit together, which is ADR-017's
argument in the small: a refusal recorded without the job that answers it leaves
a symptom with nothing to serve, nothing coming, and nobody who knows to press
the button again.

It is a status of its own rather than a dismissal with a particular note because
the two answer different questions about a symptom that still has nothing to
serve - *nobody thinks it needs a playbook* against *the drafts so far have been
wrong* - and ADR-038 §6 asks the queue to be able to answer that.

**Only a drafted proposal can be sent back.** A technician's objection came from
somebody standing at the machine (ADR-038 §4); answering it with a drafting job
files the model's opinion as a reply to a person who saw the fault. That path is
refused with a 422 saying so.

### 4. Review time is measured server-side, between the open and the decision

The detail endpoint stamps `opened_at` from the Clock (ADR-028) on every read of
a pending proposal, and the decision writes `review_seconds` in the same
statement that records it. Three properties follow:

- **Nothing is timed in the browser.** A number the screen sends is a number the
  screen can be wrong about, and this one goes in the report.
- **`opened_at` moves on every open, so the measurement is the sitting the
  decision was made in.** Opened on Monday, opened again on Thursday and decided
  in two minutes is a two-minute review. The alternative - first open to
  decision - reports three days and makes the median meaningless.
- **Null is a real answer.** A decision made without the detail ever being
  opened records no duration, because that is an approval made with no evidence
  in front of anybody, which is precisely the thing this record exists to make
  visible.

`ProposalDetail` does not serialise either field. "No timer on screen" is then a
property of the API rather than a promise about the markup: a screen cannot
render what it is not sent.

The edit rate needs nothing further - it is the proportion of applied proposals
whose `edits` is non-empty.

### 5. The evidence panel is the indexed page text, not the PDF

`GET /documents/{id}/pages/{page}` returns the chunks of that page joined back
into the page as the drafter saw it, with the document's title, edition and
machine model. The screen locates the drafted step inside it using ADR-037's own
normalisation - whitespace, case, a leading step number - and highlights it.

Three answers rather than two, because a blank panel states nothing
(principle 5):

| What came back | What the screen says |
|---|---|
| text, span found | the page with the span highlighted |
| text, span not found | *this step's text is not on that page - check the manual first*, and the page unhighlighted |
| no text | which of `no_text` (a scan), `unreadable` (a damaged page) or `not_indexed` (ingest has not read this manual, or not this far) |

A page the index has never read is **answered, not refused**: the document is
real, and which manual - and which machine model - a step cites is the one thing
ADR-015 does not relax about. The reviewer has to be told that step 3 points at
another model's bulletin whether or not there is text to show beside it. Only a
document that does not exist is a 404.

The route is authorised and logged exactly like the bytes are (ADR-019). It is
the same NDA material in another form, and an endpoint serving the text of a
manual without the check the file route applies would be the way round it.

### 6. What the screen does with all of that

- **Grouped by machine model**, because reviewing an R-2000iC draft and an
  M-710iC draft alternately means holding two manuals in mind, and that is where
  a step from the wrong model gets approved.
- **Draft left, evidence right, one screen, no modal**, and which step's
  evidence is shown is a query parameter rather than client state, so the panel
  arrives rendered with the page.
- **A step citing a different document from the rest of the draft is flagged.**
  Against the rest, not against its neighbour: comparing neighbours flags the
  step after the odd one too and leaves the reviewer working out which of the
  two is odd. Where two documents are cited equally there is no majority, and
  every step is flagged - which is the honest description of a procedure
  assembled from two manuals.
- **A supervisor may read the queue and may not decide it.** Refused at the
  endpoint, not by hiding a button (invariant 6). A supervisor who cannot see
  the queue cannot ask why it is not moving, which is their job.

## Consequences

- Migration 0010 adds `opened_at`, `review_seconds` and `edits` to
  `playbook_proposal`, and `sent_back` to its status check. `edits` is
  constrained to applied rows: a dismissed proposal carrying a diff would be a
  record of text nobody applied.
- `GET /playbooks/queue/{id}` now writes on a read. That is the cost of not
  having a timer in the browser, and it is bounded: one UPDATE on one pending
  row.
- The queue is bounded at 200 by the endpoint and the screen does not page. With
  a plant's worth of manuals it will have to; the honest statement today is that
  the corpus is nineteen chunks of synthetic manual (ADR-033), and paging a
  queue nobody has filled would be a guess about how it fills.
- **What is given up:** an engineer can still approve without opening the
  detail, and this record does not forbid it. Forbidding it would mean refusing
  an approval on the strength of a page load, which is a rule about the screen
  rather than about the review. Instead it is recorded - `review_seconds` is
  null - and the count of those is the number to look at if approval starts
  looking like a formality again.
- If review turns out to be slow in practice, `review_seconds` and the edit rate
  are already being collected, and this record is what to revisit.

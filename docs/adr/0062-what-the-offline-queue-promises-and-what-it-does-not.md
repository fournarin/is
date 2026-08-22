# ADR-062: What the offline queue promises, and what it does not

Extends [ADR-058](0058-what-the-web-layer-may-not-contain-and-how-it-reaches-the-api.md),
which said what the web layer may not contain and left open what it must
survive, and rests on
[ADR-025](0025-work-orders-support-handover-and-multi-person-jobs.md) and
[ADR-006](0006-estimated-and-actual-minutes-are-separate.md), whose feedback
loop is what a lost close destroys.

## Context

The screens are used standing at a machine on a plant network that drops. That
is a reason to design for failure, and also a reason not to design for all of
it: "make the app work offline" is a project with a synchronisation model, a
conflict policy and a local database, and this is a one-term individual study
whose report is due in week 13.

So the question is not whether to be offline-capable but **which single loss is
unacceptable**. It is the close. Everything else a technician does can be done
again: the queue can be re-read, a ticket re-opened, a step re-navigated. A
close is the only moment where information exists solely on the device - the
outcome, which of the elapsed time was waiting rather than repair, and the
sentence about what actually happened. `no_problem_found` in particular is the
only false-alarm signal this system will ever receive, and the loop that tunes
rule thresholds does not exist without it (ADR-022).

## Decision

### 1. Exactly one thing is queued on the device: a close that could not be sent

No general synchronisation, no local ticket store, no optimistic writes. Content
already loaded stays readable because the browser has it; nothing is fetched
into a cache for later.

### 2. A dropped network is queued; a refusal is shown

A `fetch` that never reaches anybody is the case the queue exists for. An API
that answers 4xx or 5xx has been reached and has said no, and retrying that for
ever is how a queue stops draining and a screen says "not sent yet" until
somebody clears the browser.

### 3. One entry per work order, and a later close replaces an earlier one

Two closes of the same job are the same close.

### 4. The form is a plain HTML POST to a route handler; JavaScript only adds the queue

`<form method="post" action="…/close/send">`. With no JavaScript it posts and
the route redirects. With JavaScript the component takes the submit over, posts
JSON to the same route, and queues on network failure. There is no server
action in this path.

### 5. The screen says plainly that a close has not been sent

Not a spinner and not a silent retry: the words, the count, and a button to try
again now. Retries also fire on load and on the browser's `online` event.

### 6. No field anywhere asks how long the job took

`actual_minutes` is the sum of the segments that "start" and "hand over" opened
(ADR-025). `blocked_minutes` is asked for, because it is the opposite quantity -
time that was **not** repair - and it is subtracted rather than counted.

### 7. The queue's logic is a pure module, tested with `node --test`

Node runs TypeScript directly, so this needs no test framework and no new
dependency, which matters because CLAUDE.md wants an ADR for one and four
functions are not that argument.

## Reasons

1. **Scope discipline is the decision, not a caveat on it.** The issue asked for
   a narrow promise and the narrow promise is worth more than a broad one that
   is half-built by week 13. Naming the single unacceptable loss is what makes
   the feature finishable and reviewable: there is one queue, one key, one
   retry, and a person can read all of it.

2. **Point 2 is the difference between a queue and a leak.** The two failures
   look identical to a technician and are opposite to the system: one will
   succeed later, the other never will. Distinguishing them needs a client-side
   `fetch`, which is the only reason JavaScript is involved in this path at all.

3. **Point 4 keeps the failure mode from being the feature's own bundle.** A
   close that requires JavaScript to submit cannot be submitted by the phone
   whose JavaScript did not load - which is the same network condition the queue
   is for. A plain form works first, and the enhancement is the part that can
   fail safely.

   Slice 10.3 supplies the other half of this argument: a bound server action
   that returns state rather than redirecting hangs on the no-JavaScript path.
   The close path avoids server actions entirely.

4. **Point 6 protects the measurement rather than the technician.** ADR-058
   already forbids showing a technician a clock; asking them to fill one in is
   the same mistake from the other side, and the number that comes back is a
   guess that then prices every future job of that kind.

5. **Point 7 is what makes "covered by a test, not only by hand" honest.** What
   is tested is the queue's meaning - one entry per job, a later close wins,
   unreadable storage reads as empty rather than white-screening a phone - and
   not the browser integration, which needs a browser and is checked by hand
   and by `check-the-technicians-screen.py` on the online path. That limit is
   stated rather than papered over.

## Consequences

- **`localStorage` is now a place this system keeps data.** One key,
  `pdm.pending-closes`, and its name is a compatibility surface: renaming it
  orphans every close queued on every device that has not drained. A test
  asserts the name for that reason.
- **A close queued on a device nobody opens again is lost**, and nothing on the
  server knows it existed. That is accepted: the alternative is a server-side
  record of an intention to close, which is a second source of truth about
  whether a job is finished.
- **`npm test` joins the web CI tier**, before the build, so a broken queue is
  its own red line.
- Photographs are **not** part of a close. The contract has no field for one and
  the API has no route; adding it means a decision about where images are stored
  and who may read them, which is its own record.

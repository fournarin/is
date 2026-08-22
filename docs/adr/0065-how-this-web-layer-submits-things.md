# ADR-065: How this web layer submits things

Extends [ADR-058](0058-what-the-web-layer-may-not-contain-and-how-it-reaches-the-api.md),
which decided that the browser talks only to this server and left open how a
form gets from one to the other, and
[ADR-062](0062-what-the-offline-queue-promises-and-what-it-does-not.md), which
took the first step of this decision for one screen.

## Context

Four screens now write something: a technician starts a job, hands it over,
closes it and objects to its rank; a shift lead releases held work; an engineer
approves a playbook. Next offers two ways to submit, and the choice looked like
taste until three separate afternoons said otherwise.

**One.** In slice 10.3 the handover form used a Server Action bound with
`.bind()` and returning state on failure. It worked in a browser and **hung for
ever with JavaScript off** - no error, nothing in any log, the request simply
never finished. The phone this is built for is the one whose bundle did not
arrive, so the failure mode was aimed exactly at the user it was written for.

**Two.** In slice 10.4 the close form began as a Server Action and became a
plain form posting to a route handler, because only a client-side `fetch` can
tell a dropped network from a refusal, and the offline queue needs that
distinction (ADR-062).

**Three.** In slice 10.5 releasing held work returned its confirmation as
component state, and the confirmation never appeared. The reason is structural
and would have been hard to find by reading: **a successful release takes the
ticket out of the held list**, so the component that submitted no longer exists
when the page re-renders, and the state it returned has nowhere to land. The
override was written correctly every time; only the screen said nothing.

Three different symptoms, one shape: a Server Action's result is bound to a
component instance and to a hydrated page, and this application's most important
writes happen where one or both are absent.

## Decision

### 1. The default is a plain HTML form posting to a route handler, which redirects

`<form method="post" action="…">`, a `route.ts` that calls the API, and a 303
back to a page that renders the result from the URL. It works with no
JavaScript, it survives the submitting component disappearing, and a repeated
POST cannot happen because the browser follows with GET.

### 2. A Server Action is used only when its result belongs to a component that
outlives the submission

Signing in and objecting to a rank qualify: both leave the page as it was and
show a message in place. Closing, releasing and handing over do not.

### 3. A Server Action that returns state is never bound with `.bind()`

Its arguments come from hidden fields. A bound action that returns state hangs
with JavaScript off, which is the condition the whole design is aimed at.

### 4. Nothing is declared working until it has been driven with JavaScript off

`check-*.py` posts the form Next renders for exactly that case. Every one of the
three findings above passed `next build`, `eslint` and `tsc --noEmit` first.

## Reasons

1. **The failure modes are silent and they are aimed at the worst case.** A hang
   with no log entry, and a write that succeeds while the screen says nothing,
   are both invisible to every gate this project runs. They are visible in about
   a minute to a script that posts a form. The rule is therefore not "prefer
   forms" as an aesthetic - it is that the cheap check only exists for the form
   path.

2. **A redirect is the only confirmation that survives its own cause.** The
   general shape is that a successful write changes the page it was made from.
   Held work leaves the held list; a closed job leaves the queue. Anything the
   component held goes with it, and the URL is the one place a message can
   outlive the component that produced it.

3. **Point 2 is not a ban.** A Server Action is the better tool where the result
   is genuinely local - a wrong password, an objection recorded beside the reason
   it objects to - and those screens read better for it. The distinction is
   whether the component survives the success.

4. **Point 4 is what makes the other three enforceable.** None of this is
   checked by a type, so it is checked by a script; and the script is worth
   having anyway, because it is the only thing in this repository that reads a
   screen.

## Consequences

- **`revalidatePath` is not used on these paths.** Revalidating the route a form
  just posted to re-renders it fresh and throws away anything the action
  returned. The screens are dynamic and re-read on the next navigation regardless.
- **A hidden field can be edited and does not need to be trusted.** The API
  refuses a handover, a close or a release from somebody without the standing to
  make it; the field says which order, not whether it is allowed.
- **Every write path is reachable without JavaScript**, which is a property
  worth stating in the report: the technician screens degrade to plain HTML on a
  network that drops, and the only thing lost is the offline queue.
- If a later screen needs a genuinely interactive write - a draft saved as
  somebody types - this record is what to revisit, and the answer will be a
  fourth case rather than a relaxation of the first three.

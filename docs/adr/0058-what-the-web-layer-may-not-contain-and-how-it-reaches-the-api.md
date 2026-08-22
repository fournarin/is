# ADR-058: What the web layer may not contain, and how it reaches the API

Revisits [ADR-008](0008-technology-stack.md), which chose Next.js and said
nothing about what it would be allowed to do, and
[ADR-036](0036-sessions-in-the-database-behind-an-identity-adapter.md), which
settled how a person is identified without saying who forwards the cookie.

## Context

Until this record the frontend existed only as a line in `docker-compose.yml`.
That is the point at which its shape is cheapest to decide and most expensive to
leave open, because a screen is where every constraint in this design is either
honoured or quietly undone. Three of them are undone by features that look
obviously useful:

- a question box, which is a runtime LLM by another name;
- a figure showing how fast a technician works, which is measurement pointed at
  the person being measured;
- a list of open work, which is the load gate with a way around it.

None of these would be added deliberately. Each arrives as "while we are here",
weeks from now, from somebody who has not read
[ADR-003](0003-no-llm-generated-repair-text-at-runtime.md),
[ADR-006](0006-estimated-and-actual-minutes-are-separate.md) or
[ADR-011](0011-load-ratio-switches-dispatch-behaviour.md). A record is the only
thing that survives that gap.

There is also a mechanical question that has to be answered before a single
screen is written, because it decides where the session cookie lives: does the
browser call the API, or does the Next server call it on the browser's behalf?
The compose file assumed the first - `NEXT_PUBLIC_API_URL`, handed to the web
container as an environment variable.

**That assumption does not work.** Next inlines `NEXT_PUBLIC_*` into the
JavaScript bundle at *build* time, and the compose file supplies it at *run*
time to a container built without it, so the browser would receive `undefined`.
Repairing it as written means a build argument, which bakes the API's address
into the image - and this image is handed to a plant and installed on their
machine ([ADR-029](0029-where-the-models-run.md)), so its address is not
knowable when the image is built. It would also make the API a cross-origin
target for the browser, which means CORS configuration that does not currently
exist anywhere in this system.

## Decision

### 1. The browser talks to the web server; the web server talks to the API

`API_URL` is read on the server, per request. Sign-in, sign-out and every read
go through a server component or a server action, which forwards the session
cookie to the API and returns only what the screen needs. No page bundle
contains the API's address, and there is no `NEXT_PUBLIC_*` variable in this
system.

### 2. No chat box, no question box, no free-text answer

There is no input on any screen whose answer is generated. The one place text
reaches a technician is a playbook an engineer approved.

### 3. No per-technician performance figures

No screen shows how long a named person took, how many jobs they closed, or how
they compare to anybody. Durations are shown per work order, and the aggregate
view is per line, per station and per shift.

### 4. Never a list of work for a technician to choose from

A technician is shown the job the scheduler chose. What is queued behind it may
be shown, collapsed and unselectable, so that the shift is not a black box.

### 5. No UI framework, component library or state library

Plain CSS and what Next ships with. Adding one needs its own record, argued for
by a screen that could not be built without it.

## Reasons

1. **Point 1 is the deployment argument before it is a security one.** An image
   whose behaviour depends on an address compiled into it cannot be handed over;
   it has to be rebuilt per site, by somebody with the toolchain, which is
   exactly the handover failure this project keeps designing away from. Reading
   the address at runtime makes the image the same everywhere and the
   environment the only thing that differs.

   What follows is a boundary that costs nothing to keep: the browser has one
   origin, so the session cookie stays `HttpOnly` and same-origin, no CORS
   configuration exists to get wrong, and the API is reachable only from inside
   the compose network rather than from every phone on the plant floor.

2. **Point 2 is ADR-003 at the only seam where it can be undone by accident.**
   ADR-003 is enforced by an import rule and a network boundary, and both live
   on the Python side. A question box in the web app calls a model directly, on
   a machine those two checks do not cover, and produces exactly the artefact
   ADR-003 forbids: a generated instruction in front of somebody standing at a
   machine. The web layer is the hole in an otherwise closed argument, and this
   is the only place the hole can be named.

3. **Point 3 protects the measurement rather than the technician's feelings.**
   `actual_minutes` is the sum of segments a technician opens and closes
   themselves (ADR-025), and it feeds the estimates the scheduler prices work
   with (ADR-006). A person who believes the clock is grading them stops
   pressing "start" until the job is nearly done. The number then reads low, the
   estimate it feeds reads low, the shift looks emptier than it is, and the load
   gate releases work there is nobody to do. The feedback loop does not degrade;
   it inverts.

4. **Point 4 is the load gate.** ADR-011 exists because the useful behaviour on
   a heavy shift is to hold work back, and on a quiet one to release it. A list
   lets a technician take the easy job first, which is not the job the gate
   admitted and not the job the score ranked, and after a week of that the
   ordering describes nothing. Showing what is next is a different act from
   offering it: the first answers "is the system hiding work from me", the
   second hands back the decision the system was built to make.

5. **Point 5 keeps a dependency argument from being made by momentum.** ADR-008
   requires a record for a new dependency. A component library added for the
   sign-in form is a library the four screens then depend on, argued for by the
   least demanding screen in the system.

## Consequences

- **`NEXT_PUBLIC_API_URL` is gone from `docker-compose.yml`**, replaced by
  `API_URL: http://api:8000`, and the now-unread `API_URL` key is deleted from
  `.env.example` under that file's own rule about keys nothing consumes.
- **Every screen is server-rendered and dynamic**, because every screen reads a
  cookie. There is no static page in this application beyond the 404, and there
  is nothing to cache: a ticket, a queue and a shift's load are all answers
  about right now.
- **The web container is on the `app` network and needs no port to the API.**
  Only its own 3000 is published. A deployment that wanted to close 8000 to the
  plant network entirely now can.
- **An operator has no screen.** ADR-024 gives the role one power - uploading
  and replacing manuals - and slices 10.2 to 10.5 build none of it, so the shell
  says so plainly rather than offering a door that opens onto nothing.
- **Offline behaviour is not decided here.** Slice 10.4 makes one narrow
  promise - a close that cannot be sent is queued on the device - and everything
  wider than that is a project of its own.
- Points 2 to 4 are prohibitions, and nothing enforces them mechanically the way
  `.importlinter` enforces ADR-003 on the Python side. They are enforced by
  review, which is why they are written as a record rather than left as taste.

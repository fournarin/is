# ADR-074: The CMMS contract is ours, and what the third destination may promise

Builds the adapter
[ADR-070](0070-the-plant-has-a-cmms-and-what-that-changes.md) §2 decided to
write, under the delivery record
[ADR-068](0068-a-ticket-that-was-dispatched-and-a-ticket-that-arrived.md) built
and the registry
[ADR-069](0069-the-destination-is-a-name-in-policy-and-a-path-in-the-environment.md)
put a name in front of. Revisits nothing.

## Context

ADR-070 settled the shape of the third destination in one paragraph: an HTTP
sink named `cmms`, its address and credential from the environment, its request
body the `Ticket` ADR-068 already defines, its response an identifier, and the
whole contract declared to be ours rather than anybody's product.

That paragraph leaves four things undecided that cannot be left to the code,
because each of them is a place where a plausible choice is silently the wrong
one:

1. **What the request actually is.** A method, a path, a body and a header for
   the credential. Ours to choose, and therefore ours to write down somewhere
   other than in the adapter that implements it - otherwise "the contract is
   ours" means "the contract is whatever the code happens to do".
2. **How long to wait.** The first destination that can hang. Every other
   constant in this repository has a source (`.claude/autonomy.md`: a manual, a
   measurement, or a record), and a timeout that merely looks reasonable is the
   same defect as an unapproved playbook.
3. **What counts as a refusal.** ADR-068 §3 divides the world into
   `DeliveryFailed`, which is recorded and retried, and every other exception,
   which is a defect that rolls the round back. A network has more failure modes
   than a directory does and each one has to be put on one side of that line.
4. **What "accepted the ticket and lost it" is.** ADR-070 §2 names it as the
   thing a CMMS adds and neither `OwnSystemSink` nor `FileSink` can produce: a
   destination that answers 2xx and issues no identifier.

## Decision

### 1. The request, written down here rather than only in the adapter

```
POST {CMMS_BASE_URL}/work-orders
Authorization: Bearer {CMMS_TOKEN}
Content-Type: application/json; charset=utf-8
Idempotency-Key: {work_order_ref}

{ "ticket": { ...Ticket, as JSON... } }
```

and the answer this expects:

```
2xx
{ "id": "<the destination's own identifier>" }
```

Three details of that are decisions rather than typing.

**The body is wrapped in `{"ticket": ...}` rather than being the ticket.** The
same shape `FileSink` writes, minus the `written_at` a file needs and an HTTP
response does not. A bare ticket would leave no room to add a field later
without every existing field moving, and the destination here is somebody
else's system - the one place where "we changed the shape" is expensive.

**The credential is a bearer token in a header, and nothing else is
configurable.** Not a username and password, not a query parameter, not a
choice between them. A single scheme is one thing to replace on the day access
is granted; a configurable one is a matrix to be tested against a system nobody
has seen.

**`Idempotency-Key` carries the work order's ref**, which is also in the body.
Duplicated on purpose: the header is what a destination that deduplicates at
its edge reads, the body is what one that deduplicates in its application
reads, and at-least-once (ADR-068 §1) means both are eventually asked the same
question twice. A destination that reads neither issues two records, and §4
below is what this project does about that.

**UTF-8, unescaped.** `reason` and the steps are Thai (ADR-069 §4 makes the
same point about the file destination), and a body that arrived as `ร` is
one nobody can check by eye against the screen a technician is looking at.

### 2. Five seconds, derived from the batch and the round

`ADR-068` §4 caps a delivery pass at fifty tickets, on the argument that one
round must not hold its transaction open across hundreds of calls to somebody
else's system while the next round waits. A per-request timeout is the other
half of that argument and is what makes it true rather than intended: without
one, a destination that accepts a connection and never answers holds the pass
open for as long as the operating system allows, and the cap on the number of
requests bounds nothing at all.

So the number is derived rather than chosen:

```
batch x timeout  <=  round_seconds
  50   x    5    =        250       <=  300
```

Five seconds, from the fifty in ADR-068 §4 and the three hundred in
`policy.yaml`. It is the same form of argument ADR-054 makes for the solver's
time limit - a ceiling bounded by the round above it - and it is asserted as a
test rather than left as a comment, because both of the numbers it is derived
from can be changed by somebody who never reads this file.

It is deliberately not in `policy.yaml`. ADR-069 §1 divides that file from the
environment along the line between a plant's decision and a deployment's fact,
and this is neither: it is a consequence of two numbers already recorded.

### 3. Every way a network says no is a refusal. Nothing here is a defect

A non-2xx status, a connection refused, a name that does not resolve, a
timeout, a body that is not JSON, a body that is JSON and has no `id`: all
`DeliveryFailed`, all recorded on the delivery row, all retried next round.

The argument is ADR-068 §2's, one destination further out. None of these says
anything about this system's own correctness - they say the destination is down,
misconfigured or not what we think it is - and a round that rolled back because
a CMMS was restarting would take a scheduling decision away from a technician
who can already see the job on their own screen.

The message names the destination and what it said, because it is stored on the
delivery row and is what somebody reads days later when they ask why a ticket
never arrived. A status code with no URL in it answers that question with
"something, somewhere, returned 502".

### 4. A 2xx with no identifier is a failure, not a delivery

This is the case ADR-070 §2 says a CMMS adds and the two existing destinations
cannot produce, and the decision is to treat it as the destination not having
taken the ticket.

The alternative - record the delivery with our own ref, the way `OwnSystemSink`
does - is available and is wrong here for a reason that does not apply there.
`OwnSystemSink` returns the work order's ref because the ticket genuinely is
where it started; a CMMS that answered 2xx and named nothing has put the ticket
somewhere we cannot point at, and a delivery row saying `delivered` with our own
number in `external_ref` would be a row that cannot reconcile the two systems -
which ADR-068 §1 says is the only thing the column is for.

The cost is honest and is accepted: the ticket goes out again next round, and a
destination that did create a record the first time now has two. That is
at-least-once (ADR-068 §1) meeting a destination that will not say what it did,
and a duplicate ticket is the failure this project already chose over a missing
one.

### 5. `http` and `https` only, checked when the sink is built

`urllib` will open `file:///var/tmp/x` as readily as an address, and a base URL
that arrived from the environment with the wrong scheme would produce a sink
that reports every delivery as successful while writing to a local path, or
reads one. Refused at composition, where `TICKET_DIR`'s absence is refused, and
for the same reason: a destination that is not a destination must fail before
the first round rather than during it.

### 6. What may be said about it

Unchanged from ADR-070 §3, and repeated because this is the record somebody
will read when the adapter exists and the temptation is at its highest: two
destinations are implemented, a third is prepared against a contract of our
own, and integration with the plant's CMMS is **not delivered**. `policy.yaml`
keeps `own-system`. A name in the config with no destination behind it is the
failure ADR-069 §2 refuses, and `cmms` pointed at a host nobody has confirmed
is exactly that.

## Consequences

- The registry gains a third name, `SinkPolicy.destination` a third literal, and
  `CMMS_BASE_URL` and `CMMS_TOKEN` join `TICKET_DIR` as deployment facts with no
  defaults. `docker-compose.yml` carries them unset with the reasoning beside
  them.
- The refusal path in ADR-068 §3 is now exercised by something that fails the way
  real destinations do rather than by a double that was asked to fail: the tests
  run a fake CMMS over a real socket that can be slow, refuse, answer nothing
  and issue a second identifier for a ticket it has already seen.
- `Deliveries.batch` and `dispatch.round_seconds` are now load-bearing for a
  third thing. The test in §2 is what tells whoever changes either of them.
- What is still untested is the thing no fake can provide: whether the plant's
  system will accept this request at all. That is not an engineering gap and
  cannot be closed by building more of it (ADR-070 §1).

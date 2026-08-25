# ADR-077: Who may report a fault, at what severity, and what a second report means

Builds [ADR-010](0010-work-orders-have-an-origin.md), which named three origins
and left the third unbuilt, and applies
[ADR-023](0023-findings-have-a-lifecycle-and-a-suppression-window.md)'s argument
at that origin. Sits under [ADR-024](0024-roles-and-approval-authority.md), whose
table does not mention reporting,
[ADR-005](0005-every-ticket-carries-its-reason.md), which owns the sentence a
report becomes, and
[ADR-071](0071-a-round-proposes-and-a-person-decides.md), which is the reason a
report does not have to be trusted to be accepted.

## Context

`WorkOrders.from_report()` has existed since the work module was written, and
until this slice nothing outside `tests/` and the screen checks called it. The
API had `accept`, `start`, `handover` and `close` and no create, and the web
application had no screen for it. A technician who found a fault the rules did
not catch could do everything with the system except tell it.

[ADR-014](0014-report-and-technician-trial-are-reserved-unconditionally.md)
reserves the technician trial unconditionally, and
`docs/results/confirmations.md` already states in writing that it has no figures
until that trial runs. The trial is a person standing at a machine. The first
thing that person does is tell the system something it did not already know, and
three sentences in `CLAUDE.md` turn into questions the moment they try.

## Decision

### 1. Any authenticated account may report; the role is not the gate

All four roles in ADR-024 may report a fault - technician, engineer, supervisor
and operator. It is checked at the endpoint like every other authority in this
system and recorded in the access log as `report_fault`, so a report and a
refusal are both evidence (invariant 6).

The person standing next to a machine when it starts making a noise is as likely
to be an operator as a technician. Requiring them to find a technician to type it
in is how a fault gets reported by radio and the system never learns it happened,
which is the failure this whole slice exists to remove.

Nor does the login need to carry the weight. A report becomes a **queued** order:
a round proposes it and a shift lead confirms it before anybody is sent (ADR-071),
so a mistaken report costs a person ten seconds of reading and never a walk
across the plant. What the endpoint does refuse is an **anonymous** report.
ADR-024's consequence that no mode disables authentication holds here for a
second reason: `reason` names the reporter, and a report nobody can be asked
about is one nobody can settle.

### 2. A reporter may set low, medium or high, and never critical

Severity does two things in this system, and the ceiling is chosen against both.

It decides **admission** at the load gate: on a heavy shift, ADR-011 holds
everything below `high`. A report of `high` therefore already passes the gate on
the busiest shift there is, and the ceiling costs a reporter nothing they would
notice.

It also **scales the priority score** - ADR-045's severity term is the rank over
`critical`'s. What the ceiling stops is one person's account of a machine
outranking a measured threshold crossing in the queue. `critical` is what
`config/rules.yaml` gives the one rule marked `safety_critical`, and a report is
evidence of a different kind: unverified, unrepeatable, and worth acting on
without being worth putting ahead of that.

The refusal says so, and says what to do instead: a fault that cannot wait for
the next round is a phone call to the shift lead, and the ticket records it
afterwards. That is honest about what this system is. It is a queue, not an
emergency channel, and pretending otherwise is how somebody ends up waiting for
a round while a machine burns.

If the trial in ADR-014 shows people routinely need the level they cannot set,
the record to replace is this one.

### 3. A report on a machine that already has an open ticket is refused, and the reporter is shown what to do about it

ADR-023 exists because one overheating motor raising a Finding on every reading
becomes a hundred work orders. The same arithmetic arrives at the manual origin
with people instead of readings: a line stops, four people see it, and four
tickets are dispatched to four technicians for one fault.

So a report against a machine with an open order is refused with **409 and the
references of the orders already open**, which is the answer to the question the
reporter actually has - *does anybody know about this yet?*

The way past it is part of the decision, because the refusal is wrong about a
second, genuinely different fault. A reporter who has seen the open tickets may
send the report again naming them in `distinct_from`, and the order is written
with "reported alongside WO-000123" in its reason. Naming them rather than a
plain override flag is deliberate: if a new ticket appeared between the refusal
and the retry, the retry is refused again with the new list, so the override is
always against what the person was actually shown.

The key is the **machine**, not the symptom, and that is a limitation worth
naming rather than hiding. `symptom_code` is not stored on a work order -
ADR-041 copies onto the order only what the scheduler needs - so a finer key
would need a contract change nothing else has asked for yet. The cost is one
extra tap for a second real fault on a busy machine, and the thing it buys is
that the common case, four people reporting one stopped line, produces one
ticket.

### 4. A report with no symptom code becomes a ticket with no playbook, and says so

`symptom_code` stays optional, as `from_report()` already has it. A person may
not know which code it is, and a system that requires a diagnosis before it
accepts a problem is one that gets a diagnosis invented for it.

**Nothing infers a code from the description.** That would be ADR-009's rule
broken from the other end - a component chosen by inference - and, if it were
done well, an LLM deciding at runtime what a technician is shown, which is
ADR-003. An order with no code carries no playbook, is priced from
`fallback_minutes` with `estimate_is_fallback` set, and leaves `required_skill`
empty rather than guessed (ADR-041).

### 5. The reporter's words are the reason, and are not rewritten

`reason` is what they typed, with who and when around it, exactly as
`domain.from_report()` already writes it. The endpoint may not rephrase,
summarise or translate it. It is the only account of the machine that came from
somebody standing next to it, and the system's phrasing is worth less than
theirs (ADR-005).

The description is required and may not be whitespace, refused at the schema the
way ADR-025's handover note is: an empty one leaves a technician arriving at a
machine knowing only that somebody thought something was wrong with it.

## Consequences

- The three origins ADR-010 named all exist at runtime once
  [16.1](https://github.com/fournarin/is/issues/90) lands; this record finishes
  the third.
- The access log gains `report_fault`, which is what makes "who reported this"
  answerable after an incident even for a report that was refused.
- Operators are offered a screen for the first time. The shell has shown them
  nothing since ADR-058, and this is the one thing they have authority to do.
- The load gate now receives work whose severity a person chose. `load_ratio`
  moves with reports, which is a new way for the quiet-shift behaviour to be
  wrong, and the confirmation record (ADR-075) is where that would first show up
  as reports being rejected by the shift lead.
- The duplicate rule reads open orders on the machine, so it needs the same
  connection the order is written on. It cannot move to `dispatch/`, which may
  not read the work table at all, and it does not belong in layer 1, which has
  its own suppression window for its own reason.

# ADR-069: The destination is a name in policy and a path in the environment

## Context

ADR-012 puts layer 4 behind an interface because nobody knows yet whether the
plant has a CMMS, and its argument is that the outbound layer stays cheap to
change while that question is open. ADR-068 built the port, one adapter and the
delivery record.

One adapter does not exercise the argument. With a single sink `TicketSink` was
a class with one subclass, `OwnSystemSink` could not fail because its
destination was the same database, and "swappable" was a sentence in a record
rather than a property anything could fail on.

Adding the second one forces a question the first did not: **who chooses, and
where is the choice written.**

## Decision

### 1. The name is policy. The path is deployment

`policy.yaml` gains one key:

```yaml
sinks:
  destination: own-system    # or: file
```

and nothing else. Where the `file` destination writes comes from `TICKET_DIR` in
the environment.

They are two different kinds of fact. Which destination a site sends tickets to
is a decision about how that plant works, sits beside the load thresholds and
the trigger rules, and belongs in the file an operator is expected to read. A
host path is a property of the machine the container is on; it changes when the
volume layout changes and never when the plant's process does. `policy.yaml`
has no paths in it anywhere, and this decision is what keeps that true.

`TICKET_DIR` has no default, for the reason ADR-019 gives `STORAGE_DIR` none: a
worker that starts against a guessed directory looks healthy while writing
tickets somewhere nobody will look. `file` configured with no directory is a
startup failure naming the variable.

### 2. An unknown name stops the process, and says what it does have

Never a quiet fall back to `own-system`. A plant that configured `cmms` and got
our own system would look like it was working, and the tickets nobody was
reading would be the first anybody heard of it. The error names the value it was
given and lists the destinations this build has, because the next thing somebody
does is look for the spelling they got wrong.

The check runs twice, deliberately. `python -m pdm.platform.config config`
rejects it before anything starts, which is the gate a deployment runs; the
registry raises at composition, which is what catches a config that changed
under a running system.

### 3. The names are duplicated, with a test holding them together

`SinkPolicy.destination` is a `Literal` repeating `NAMES` in
`pdm/sinks/registry.py`. It cannot import them: `pdm.platform` sits underneath
everything and reaching up to `pdm.sinks` would invert the package layout
(ADR-030).

So the list exists twice and a test asserts the two agree - the same pattern
`test_package_layout.py` uses for the module names `.importlinter` refers to as
strings. The alternative, a plain `str` validated at composition only, would
mean `config` could not reject a bad destination, and that command is the one
thing a deployment runs before it starts anything.

### 4. `FileSink` writes one file per work order, named for it

Not one per delivery attempt. At-least-once means every adapter is eventually
called again for the same ticket (ADR-068), and a destination that grew a file
per attempt would turn a retry loop into a full disk.

A directory it cannot write raises `DeliveryFailed` rather than crashing the
round - the cheapest honest version of a CMMS that is down, and the first time
the refusal path in ADR-068 §3 is exercised by something other than a test
double.

## Consequences

- **"Swappable" is now a property with a test.** `TestTheSameRoundTwoDestinations`
  runs a round against each sink and asserts the schedule is identical - same
  placements, same `priority_reason`, same score, same assignees - and only the
  delivery differs. Anything else moving would mean the choice of destination
  had reached back into layer 3.
- The delivery record needed no column for the second destination, which is some
  evidence it was built for delivery rather than for the first sink.
- Still no CMMS. `file` is a real destination outside this process, not a stand-in
  for one, and what it does not test is the thing a CMMS adds: an identifier
  issued by somebody else, and a system that can accept a ticket and then lose
  it.
- `docker-compose.yml` carries `TICKET_DIR` unset with the reasoning beside it,
  so the error message's "see the worker services in docker-compose.yml" points
  at something that is actually there.

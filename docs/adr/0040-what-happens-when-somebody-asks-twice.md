# ADR-040: What happens when somebody asks twice, and what a worker with no handlers does

## Context

Slice 3.8 gave the pipeline its two entrances - an upload queues its own ingest,
and an engineer can ask for a draft - and in doing so changed two things that
were already written down.

**ADR-039 section 8 says a job of a kind this worker does not handle is failed
rather than crashing the worker.** That is right for a worker with handlers and
wrong for `worker-runtime`, which has none: it would claim every runtime job that
appears and burn its attempts as unknown kinds, months before the handler that
was meant to run it ships.

And both new entrances can be pressed twice. A double-submitted draft request
costs a full pass on the machine holding the only GPU (ADR-029) and files a
second identical proposal in a queue whose whole purpose is that a person reads
it. A re-uploaded manual costs an ingest.

## Decision

### 1. A worker with no handlers claims nothing

It reaps and waits. `worker-runtime` runs that way until layers 1 and 3 give it
work, which is what lets the container exist at all - and a container that exists
and idles is worth having, because the alternative was the crash loop compose has
produced on every `up` since slice 0.3.

This narrows ADR-039 section 8 rather than reversing it: a worker that *has*
handlers and meets a kind outside them still fails that job, because there the
job is genuinely unrunnable rather than merely early.

### 2. A draft request for a pair that already has one pending returns the first

Same status, same shape, the original job's id. Not a 409: asking twice for
something that is already coming is not an error, and an interface that answered
one would teach people to press the button again to find out.

The check is on the **job**, not on the proposal. A pending job is work not yet
done; a pending proposal is work done and waiting for a person, and re-drafting
after a manual is replaced is exactly the case where a second proposal for the
same pair is correct (ADR-038 allows several).

### 3. An upload always queues an ingest, even for bytes already in the library

Re-ingesting replaces a document's pages and chunks rather than adding to them,
so the duplicate is idempotent where it matters. The alternative - deciding at
upload time whether the index is current - is a second opinion about a question
`document_page` already answers, and it would be wrong in the one case that
matters: a manual whose first ingest failed and whose row is therefore already
there.

**The cost is not free and it is not in PostgreSQL.** The vector half is dropped
and rebuilt outside any transaction (ADR-035), so a duplicate upload re-embeds
the whole manual and leaves that document's dense half empty while it does.
Accepted at this size, and worth revisiting when a manual is two hundred pages
and something other than the worker is reading Qdrant.

### 4. A question that is only whitespace is not a question

Stripped and rejected at both entrances. It passes a `min_length` check, retrieves
nothing, and files a `not_found` proposal that reads as "the manuals do not answer
this" - which is a statement about the corpus, made on the strength of a typo.

## Reasons

**Idempotence at the entrance is worth more than idempotence in the handler.** A
handler that can run twice safely still costs the run; a door that recognises the
second press costs nothing. The two doors are also where a person is standing,
which is where a duplicate is most likely and least explicable.

**The handler-less rule is what makes an empty container honest.** Without it,
`worker-runtime` would have to either not exist - leaving the crash loop, and
teaching everybody to ignore a red container - or claim work it cannot do.

## Consequences

- **The draft endpoint reads the queue before writing to it.** One extra query on
  a path nobody is waiting on.
- **`JobQueue.enqueue` accepts a `JobKind` or a string**, and the entrances pass
  the enum. Making it enum-only was tried and reverted: *a kind no handler
  claims* is a real runtime case with a real behaviour (ADR-039 section 8), and a
  signature that cannot express it cannot test it. It would also have forced
  names to be declared now for the dispatch tick and the trigger scan, which is
  the config-entry-with-no-consumer pattern `lessons_carried.md` 4.4 warns
  about. The queue's `kind` column stays text for the same reason.
- **Dedupe is per pair, not per request.** Two engineers asking with different
  questions get one job - the first question - and the second gets the first
  one's id back. Wrong only if the second question was better, and the answer
  there is to look at the draft the first produced.

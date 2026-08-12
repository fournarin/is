# ADR-037: Drafting selects spans, figures are gated, and a failed draft is withheld whole

## Context

ADR-003 moved the LLM to build time and put an engineer between it and the
technician. ADR-015 tuned retrieval for recall on that side of the line, and
slice 3.3 made both halves of it work. What nothing has settled is the step in
between, which is the one the whole arrangement exists for:

> given a symptom code and a machine model, what is the model allowed to
> produce, and what has to be true of it before a person is asked to review it?

Four questions have to be answered before any of it can be written.

1. **What may the model write?** "Draft a playbook from these pages" invites
   fluent prose that reads like a manual and cites a page that does not say it.
   Invariant 5 exists because of exactly that failure in the author's earlier
   system.
2. **How is invariant 5 enforced, mechanically?** design.md section 12 states it
   as "the figures in a draft are a subset of the figures in the evidence it
   cites" and names authoring as the place it is enforced. Nothing says what
   counts as a figure, or what happens when the check fails.
3. **What runs in CI?** Tiers 1 and 2 must pass on every commit
   (design.md 12), on a machine with no GPU and no model server. Drafting that
   can only run against `llm-server` is drafting that is never tested.
4. **What is the honest output when the manual has no procedure?** The corpus
   was built with three categories for this reason (ADR-033), and two of them
   are not repair playbooks.

## Decision

### 1. The model selects spans; it does not write text

A drafting backend is asked to choose, from evidence it is given, which spans
become steps and in what order. Each returned step names the chunk it came from,
and the service checks that the step's text is contained in that chunk once
whitespace and a leading step number are normalised away.

A step that is not contained in the chunk it cites is not a step. There is no
"mostly matching" tolerance, because a tolerance is a size, and every size is a
number with no source (workflow.md 4.1).

### 2. Every figure in a step must appear in the evidence it cites

Invariant 5, as a mechanical check that does not depend on the backend:

- A **figure** is a numeric literal, taken with its decimal part and with
  thousands separators removed: `1,200` and `1200` are the same figure, `42` and
  `42.0` are the same figure, and `4 to 6 mm` is two figures.
- The step's figures must be a **subset** of the cited chunk's figures. Equality
  is not required: a step that omits a figure on the page is a shorter step, not
  a wrong one.
- Order and unit are not checked. The gate is about where a number came from,
  not about whether the sentence around it is right.

### 3. Both checks exist, because one of them has a known expiry date

Containment (1) makes fabricated figures impossible by construction, which makes
the figure gate (2) look redundant today. It is not:

**The manuals are English and the technicians read Thai.** The moment a step is
translated - which this project needs and the author's earlier system already
did - containment cannot hold, and the figure subset is the only mechanical
guarantee left standing. Writing it now, while containment makes it easy to test,
is what makes it available then.

Until that day, the gate is proved by adversarial backends in the tests rather
than by the drafts the real ones produce, and the tests say so.

### 4. A draft that fails either check is withheld whole, never trimmed

If any step fails containment or the figure gate, no playbook draft is produced.
The rejected steps and the reason go to the review queue in place of it.

Dropping the offending step and offering the rest is the alternative, and it is
worse: a procedure with step 4 removed reads as complete. The engineer reviewing
it has no way to see the hole, and step 4 of the belt procedure is the one that
sets the tension the first three steps prepared for.

### 5. Three outcomes, matching the three categories of ADR-033

| Outcome | When | What the reviewer gets |
|---|---|---|
| `repair` | the evidence contains numbered instructions | steps, tools, and the figures they carry |
| `diagnostic` | the symptom is documented, no procedure is given | what the manual does say, including any prohibition on the page |
| `not_found` | retrieval returns nothing above the authoring floor | the symptom, and the fact that the corpus is silent |

`not_found` is a result, not a failure. Principle 5 requires the system to say
so, and ADR-033 built a symptom into the corpus that has no answer anywhere so
that this path is executed by a test rather than first in front of a technician.

### 6. A step's confidence is the retrieval score of the chunk it cites

Not a number the model reports about itself. A model-reported confidence has no
provenance in any of the three senses workflow.md 4.1 admits, and the fused score
already means one fixed thing: how far the two halves of retrieval agreed
(ADR-035).

### 7. A step may only cite evidence from the machine model it is drafted for

The authoring profile searches across models on purpose (ADR-015), and those
candidates stay visible to the reviewer. They may not become steps. This is the
one line ADR-015 says does not move, and the corpus contains the trap it exists
for: the same symptom on the other model, reading perfectly well, with 28 Nm
where this model wants 42 Nm.

### 8. Skill, duration and tools are extracted, never invented

Taken from the evidence when it states them, validated against the skill
vocabulary in `plant.yaml` (invariant 13). When the evidence does not state them,
the draft carries nothing and the reviewer supplies it. A default duration
guessed here would enter `estimated_minutes`, which the scheduler computes with,
carrying the authority of a figure from a manual and the provenance of nothing.

### 9. Two backends behind one port, chosen by configuration

`Drafter` is the port. `ExtractiveDrafter` runs in process with no model at all
and is what tiers 1 and 2 use. `LlmServerDrafter` talks to `llm-server` over
HTTP and is tier 3 only (ADR-029).

Configuration chooses between them. Neither falls back to the other: a system
that silently degrades to the extractive backend when the model server is down
would report drafts of a different quality under the same name, and nobody would
know which they were reading.

### 10. The prompt lives in one file and versions with the repo

Changing it invalidates every drafting number measured before the change, the
same way changing the embedding model invalidates retrieval numbers (ADR-035).
It is also the artefact workflow.md section 3 names as the one that must not be
delegated: it is what decides whether a technician is handed the right torque
figure.

## Reasons

**The dangerous output is not a wrong sentence; it is a right-looking sentence
with a wrong number in it.** A technician reads a step, sees 42 Nm, and applies
42 Nm. Everything above is arranged so that a figure reaching that person came
off a page somebody can open, and so that the failure to achieve it stops the
draft instead of decorating it.

**Selection is where a model earns its place here anyway.** The manuals already
contain the sentences. What is genuinely hard is knowing that the belt-tension
procedure on page 4 answers "motor above 85 degrees" while the belt-replacement
procedure on page 5 - which repeats the same torque figure - does not. That is a
judgement about relevance, and it is what the model is being asked for.

**A check that cannot fail is worse than no check.** This project has already
shipped three of them (the answer-key tests in slice 3.0, the memory test in 3.1,
the fake embedder in 3.3). The figure gate is in that category by construction
today, so the tests that prove it work drive it with backends that fabricate on
purpose.

## Consequences

- **The extractive backend passes the figure gate by construction.** Any figure
  in a span of the cited chunk is in the cited chunk. The report must not present
  a clean gate result on extractive drafts as evidence that the gate works; the
  evidence for that is the adversarial tests.
- **Drafting quality is bounded by how the manual is written.** A manual whose
  procedure is a paragraph rather than a numbered list drafts poorly, and the
  measurement records that rather than hiding it behind a model that would
  rewrite it into a list.
- **`Playbook` is not the drafting output.** A draft may lack a skill or a
  duration, which the contract requires; the drafting result is its own object
  and becomes a `Playbook` when a person completes it. The slice that stores
  drafts decides what the nullable columns look like.
- **The drafting job is not wired to the queue in this slice.** It is an
  authoring job by ADR-026 and will be claimed by `worker-authoring`; nothing
  claims anything yet, and that entrypoint is its own slice.
- **Not decided here: that a repair draft must begin with isolation.** The corpus
  declares each manual's lockout page and every repair procedure in it starts by
  citing that page, so a check is temptingly easy to write. It would only work on
  this corpus - nothing can locate the lockout page of an arbitrary manual - and
  a guarantee that holds on the fixture and not in the plant is an eval wearing
  the clothes of an invariant.

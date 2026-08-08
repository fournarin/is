# ADR-015: Authoring is tuned for recall; runtime keeps precision first

## Context

ADR-003 moved the LLM to build time with an engineer approving every page. The
side effect not yet recorded is that **the cost of the two kinds of error is no
longer the same in the two situations**. At authoring time, missing the right
manual page means that playbook never exists and nobody learns the gap is there;
retrieving something irrelevant costs a reviewer a few seconds.

## Decision

Split retrieval configuration into two profiles.

- **Authoring:** low threshold, wide candidate pool, document type unconstrained,
  never abstain. Offer everything plausible, labelled with confidence.
- **Runtime:** strict threshold, abstain as soon as the gate is not met.

One line does not move even at authoring time: **machine model scope**. Expanding
across instances of the same model is fine; candidates from another model must be
labelled as such and must never be mixed silently into one list.

## Reasons

At runtime nobody stands between the system and the technician, because the
review already happened at approval. Carrying a recall-first profile into runtime
would bring back the entire risk ADR-003 was written to remove.

The machine model line does not move because reviewers are reliable at judging
"is this relevant" and unreliable at judging "is this the right model". A lockout
procedure for a neighbouring model reads correctly line by line and is wrong only
in the order the interlocks are released, which the eye cannot catch unless the
reader knows they are looking at the wrong model.

## Consequences

1. **The cost moves to the reviewer, and that is where this can genuinely fail.**
   Too many candidates and the engineer approves in bulk, turning the approval
   step into ceremony. Deduplicate by page rather than by chunk, cap the number
   per topic, highlight the span that decides it so the judgement can be made on
   one screen, and group the review by machine model.
2. **`Playbook.steps[]` must carry provenance per step**, not per page, because
   wider context raises the chance of a draft mixing two machines. Per-step
   provenance makes a mixed draft report itself.
3. Recall@k must be measured against a gold set mapping symptom codes to the
   right manual pages, and locked before tuning rather than found afterwards.
4. A useful by-product: once recall is a variable we control, "minutes per page
   for the engineer" and "rate of edits required" become curves rather than
   single points, which is the data behind the second publication direction.

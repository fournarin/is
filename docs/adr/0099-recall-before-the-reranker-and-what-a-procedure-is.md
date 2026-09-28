# ADR-099: Enough candidates for the reranker, and what counts as a procedure

Written on 2026-09-28, from the real-manual measurement ADR-098 started.

## Context

Two things were still wrong on the two real Mitsubishi manuals after ADR-098.

1. **The reranker never saw the answer.** In the 456-page motor manual, most of
   it dimension tables, the first stage (MiniLM embeddings with full-text,
   fused) ranked the inspection page 21st and 73rd for two English questions.
   Authoring passed 40 candidates to the reranker, so it chose the best of the
   wrong pages.
2. **A wrong page was drafted as a repair.** Two Thai questions landed on pages
   with numbered text that is not a procedure: "1) Grease 2) Lubricant" (the
   headings of a lubrication table, one of them the single word
   "Maintenance-free") and a function table numbered "1. 2.". The drafter
   required only two numbered items, so both became repair playbooks. That is
   the costliest kind of error.

## Decision

1. **The authoring profile passes 120 candidates** (was 40). Build time only.
   A draft takes longer, which an engineer waiting once per symptom can
   afford.
2. **A numbered procedure needs at least three steps, each 3 to 80 words.**
   Every procedure in both synthetic corpora has three to six steps of six
   words or more. Headings and table cells fail the rule, and a page that fails
   it is drafted as fault-finding text, never as a repair.

## Consequences

The measurement is in `docs/results/rag-evaluation.md`. A real procedure with
two steps would now be drafted as fault-finding text. The engineer approving it
sees the same page and can still approve it, so the cost is a label, not the
text a technician receives.

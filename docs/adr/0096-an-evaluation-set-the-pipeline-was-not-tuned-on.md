# ADR-096: An evaluation set the pipeline was not tuned on

Written on 2026-09-27, when the owner narrowed the rest of the term to the
advisor's five requirements. Two of the five, saying where a technician should
repair and how, rest on retrieval and drafting from the plant's manuals. A
wrong procedure there is the most expensive mistake this system can make.

## Context

Every figure the repository quotes about drafting was measured on
`fixtures/corpus` (ADR-033): two manuals, eighteen pages and five symptoms.
Every drafter change since August was made while looking at those same five,
and ADR-089's 10/10 is a result on the data it was tuned on. It cannot say how
the pipeline does on a manual it has not seen, and "it works on the examples it
was built from" is not evidence a plant should act on.

## Decision

1. **A second corpus, `fixtures/evalset`**: four manuals for body-shop
   equipment (two sister servo weld guns, a skid conveyor and a sealer
   dispenser), 32 pages and 21 symptoms. It is written to have the shapes real
   manuals have and the first corpus lacks: sister models with different
   figures, a specification table repeating every figure, a troubleshooting
   table naming symptoms in the question's words, a procedure that runs over
   two pages, and symptoms the manuals discuss without a procedure or never
   mention.
2. **The answer key was written before the pipeline ran on it.** Each entry
   is `dev` or `test`. Dev entries may be looked at while changing the
   pipeline. Test entries are measured and never tuned on. A change is kept
   only if the test figures hold or improve.
3. **Queries are phrased as a technician would type them**, in English and in
   Thai. Some carry no figures, because a technician will not always type one.
4. **`scripts/measure_rag.py`** reports, per split and language, the rank of
   the answer page, whether drafting did what the key implies, and a separate
   count of **unsafe** drafts: a repair procedure where the key has none, or one
   citing a page that is not the answer. The reviewer is the last line against
   those (ADR-003), and this counts how often it has to be.

## Consequences

- The first measurement is in `docs/results/rag-evaluation.md`. It is the
  baseline every retrieval or drafting change is compared against.
- Still synthetic. It measures the pipeline's behaviour on shapes real manuals
  have, not its accuracy on the plant's documents, and the report says so.

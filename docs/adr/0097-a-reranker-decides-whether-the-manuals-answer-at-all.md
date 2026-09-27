# ADR-097: A reranker decides whether the manuals answer at all

Written on 2026-09-27. Supersedes the "closed for this term" entry for the
reranker in [ADR-086](0086-what-this-term-does-not-do.md).

## Context

The evaluation set (ADR-096) measured what `docs/reranking-candidates.md`
predicted: rank fusion cannot say "nothing here". **Six of the eight questions
about symptoms the manuals never mention got a repair procedure**, and every
unsafe draft but one on the set came from that. Where a wrong procedure costs a
machine or a person, this is the failure that matters most.

ADR-086 closed the reranker for the term on two grounds. The multilingual model
fastembed ships (`jina-reranker-v2-base-multilingual`) is licensed for
non-commercial use only. The permissive alternative needed an ONNX export the
environment could not reach. The second no longer holds:
`onnx-community/bge-reranker-v2-m3-ONNX` is an ONNX export of
`BAAI/bge-reranker-v2-m3`, which is Apache-2.0, multilingual and reads Thai.
fastembed 0.8, already a dependency, loads it as a custom cross-encoder.

## Decision

1. **Authoring scores every candidate page with `bge-reranker-v2-m3`** (int8,
   571 MB, CPU) and uses the relevance, in [0, 1], as the page's score. Build
   time only; nothing at runtime calls it (ADR-003).
2. **A page below `retrieval.authoring.min_relevance` (0.10) is not evidence.**
   When no page clears it, the outcome is "not found" and an engineer is asked.
   The value was chosen on the dev split only. There, the best page for every
   absent symptom scored 0.000, and every answered symptom but one had its
   answer page at 0.62 or above.
3. **Among pages scored at least half as relevant as the best, a numbered
   procedure comes before a page that prescribes nothing.** A specification
   table repeats every figure of a procedure and scores nearly as high (0.87
   against 0.99 on dev). This applies only when scores are relevances, not
   fused rank scores (`DraftRequest.relevance_scored`), because only a
   relevance can be compared as a magnitude.
4. The model ships inside the image, named by the module that loads it, like
   the embedding model (ADR-079).

## Result (test split, never tuned on)

| | outcome as the key implies | unsafe drafts |
|---|---:|---:|
| English, before | 9/12 | 2 |
| English, with the reranker | **12/12** | **0** |
| Thai, before | 7/12 | 3 |
| Thai, with the reranker | **10/12** | **0** |

Both remaining Thai misses are "not found" for a symptom the manual discusses
without a procedure. They err towards asking an engineer. The original corpus
stays at 10/10.

## Consequences

- The image grows by 571 MB and a draft takes a few seconds longer.
- A false "not found" is possible, as with EV-101 in Thai on dev, where a
  question with no figures and no shared words scored 0.001. It shows on the
  engineer's gaps screen, and the engineer can ask again in other words. That
  is the error this design accepts, in exchange for not drafting procedures
  for things the manuals never mention.
- The threshold is a measurement on synthetic manuals. The first plant manuals
  are where it has to be checked again, with `scripts/measure_rag.py` against
  a small key written for them.

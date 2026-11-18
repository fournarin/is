# ADR-143: Three more real manuals, measured as shipped

Written on 2026-11-18. Phase 1 of the owner's last week (item A). Decided by
the agent on the owner's delegation (ADR-090).

## Context

The weakest number in the report was drafting on real manuals: two manuals,
nine questions per language (ADR-098), and neither manual prescribes a field
repair, so a correct repair draft was never an outcome the set could reward.
Three more manufacturer manuals were downloaded (two SMC pneumatic manuals with
seal-replacement sections, one SEW gear-unit manual with an oil-level check).
An answer key for them, 18 symptoms (5 covered, 9 documented without a
procedure, 4 absent), was written by a separate reviewer by reading the
manuals before the pipeline ran on them.

## Decision

1. **The key is `fixtures/realdocs2/manifest.yaml`, copied from the reviewer's
   file.** One edit, made before any run: line 121 was not valid YAML (an
   unquoted `: ` inside a `why`), so that string is quoted. No page, query or
   category was changed.
2. **The loader accepts what a key of real manuals does not have.**
   `lockout_page`, `required_skill` and `estimated_minutes` become optional:
   a skill or a duration written down for a stranger's machine would be a
   number with no provenance. The synthetic corpus still has all three, and
   its tests now say so. A key may record `encrypted`, an answer its `why`,
   and a documented-only entry its `supporting_pages` (still off-key for the
   verdict: the page that says it is the one rewarded).
3. **`scripts/measure_rag.py realdocs2`** reads the PDFs from `REALDOCS_DIR`
   like `realdocs`, and `--json=PATH` writes one record per question plus each
   manual's ingest coverage. For a covered entry the record says whether each
   figure the key names is in the draft, beside the verdict rather than inside
   it.
4. **Measured with the shipped settings only**: reranker on, `min_relevance`
   0.10 / 0.35 / 0.50 from `config/policy.yaml`, 120 candidates, the symptom
   described (ADR-121). Nothing was tuned on this set, and the other three sets
   were re-run at the same commit so one table holds them all
   (`docs/results/realdocs2.md`).

## Consequences

- The ingest risk named before the run did not happen: the pypdf in the lock
  file (6.19.0) reads every page of `om_mb2_doc1088008en.pdf`, warning that the
  `90msp-RKSJ-H` encoding is not implemented, and the answer pages come out as
  readable English. A page that does throw is already recorded as unreadable
  rather than sinking the manual (ADR-034), so no ingest change was needed.
- Two keys of real manuals are checked for internal consistency without their
  PDFs (`tests/corpus/test_the_real_manual_keys.py`).

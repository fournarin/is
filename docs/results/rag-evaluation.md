# Retrieval and drafting on the evaluation set

Produced by `scripts/measure_rag.py evalset` ([ADR-096](../adr/0096-an-evaluation-set-the-pipeline-was-not-tuned-on.md)).
Each symptom is asked once in English and once in Thai. **`test` entries were
never looked at while changing the pipeline.**

## Baseline - 27 September 2026

Pipeline as on `main` after #135: `paraphrase-multilingual-MiniLM-L12-v2` embeddings,
PostgreSQL full-text, rank fusion, `ExtractiveDrafter` choosing the page by the
question's figures (ADR-089). No reranker, no abstention.

| split | lang | outcome as the key implies | unsafe drafts | answer page first | answer page in top 3 |
|---|---|---:|---:|---:|---:|
| dev | en | 7/9 | 1 | 7/7 | 7/7 |
| dev | th | 6/9 | 1 | 6/7 | 6/7 |
| test | en | 9/12 | 2 | 9/10 | 10/10 |
| test | th | 7/12 | 3 | 7/10 | 10/10 |

What it says:

- **Retrieval finds the page.** The answer page is in the top three for every
  test question, in both languages.
- **Nothing says "not found".** Six of the eight questions about symptoms the
  manuals never mention got a repair procedure, and the other two got
  fault-finding text. This is the failure that costs the most, and every
  unsafe draft in the table but one comes from it.
- **A procedure over two pages is drafted from one of them** (EV-104 in Thai
  cites page 10, the continuation).
- **Thai questions without figures fare worst** (EV-101, EV-122), because the
  drafter chooses a page by the question's figures and the word half of
  retrieval matches Thai poorly.

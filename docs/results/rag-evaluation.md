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

## With the reranker - 27 September 2026

`bge-reranker-v2-m3` scoring each page, `min_relevance` 0.10 chosen on dev
([ADR-097](../adr/0097-a-reranker-decides-whether-the-manuals-answer-at-all.md)).
`scripts/measure_rag.py evalset --rerank`.

| split | lang | outcome as the key implies | unsafe drafts |
|---|---|---:|---:|
| dev | en | 8/9 | 0 |
| dev | th | 8/9 | 0 |
| test | en | **12/12** | **0** |
| test | th | **10/12** | **0** |

- **Every question about a symptom the manuals never mention is now "not
  found"**, in both languages and both splits.
- **No unsafe draft anywhere.** Every remaining miss errs towards an engineer:
  a "not found" (EV-101 and EV-105 in Thai, EV-134 in Thai), or fault-finding
  text from the overview where the key wanted the procedure (EV-101 in English).
- The two-page procedure is drafted from its first page in both languages
  (EV-104). The continuation's steps 5-7 are not yet joined on.
- The original corpus stays at 10/10 with the reranker.

## Two real manufacturer manuals - 28 September 2026

A Mitsubishi servo motor instruction manual (456 pages) and an MR-J4 servo
amplifier Modbus manual (118 pages), supplied by the owner as test material and
not committed. Key: `fixtures/realdocs/manifest.yaml`, written by reading them
first. Neither prescribes a field repair, so the right answer to every answered
question is the inspection or reference text from the right page, as
fault-finding ([ADR-098](../adr/0098-what-two-real-manuals-changed.md)).

| | outcome as the key implies | unsafe drafts | answer page in retrieval's top 3 |
|---|---:|---:|---:|
| English, before ADR-098's fixes | 6/9 | 2 | 4/7 |
| English, after | **7/9** | **0** | 4/7 |
| Thai, before | 4/9 | 4 | 6/7 |
| Thai, after | **6/9** | **2** | 6/7 |

- **Every question about something the manuals do not cover is "not found"**,
  in both languages.
- **Two unsafe drafts remain, both Thai** (RD-02 on page 113, RD-07 on page
  15): a wrong page carrying a numbered list, drafted as a repair. In a
  456-page manual that is mostly dimension tables, the first stage of
  retrieval ranks the answer page 13th or 21st for some questions, and the
  reranker only sees what that stage returns. Better Thai retrieval in the
  first stage, a stronger embedding model or more candidates, is the next
  measured change.
- The evaluation set is unchanged by these fixes: 12/12 English and 10/12 Thai
  on test, no unsafe draft.

## 120 candidates, and a procedure is three instructions - 28 September 2026

[ADR-099](../adr/0099-recall-before-the-reranker-and-what-a-procedure-is.md).

| set | lang | outcome as the key implies | unsafe drafts |
|---|---|---:|---:|
| real manuals | en | **9/9** (was 7/9) | **0** |
| real manuals | th | **8/9** (was 6/9) | **0** (was 2) |
| evaluation set, test | en | 12/12 | 0 |
| evaluation set, test | th | 10/12 | 0 |
| original corpus | en / th | 5/5 / 5/5 | 0 |

**No unsafe draft remains on any of the three sets.** Every remaining miss is a
"not found" (RD-03, EV-101, EV-105 and EV-134 in Thai) or fault-finding text
where a procedure was wanted (EV-101 in English): the system asks an engineer
rather than guessing.

## A procedure over two pages is drafted whole - 28 September 2026

[ADR-100](../adr/0100-a-procedure-that-runs-over-a-page-is-drafted-whole.md).
EV-104 (secondary cable replacement, steps 1-4 on page 9 and 5-7 on page 10)
is now drafted with all seven steps in both languages, each citing its own page.
Every set is otherwise unchanged: real manuals 9/9 and 8/9, evaluation set test
12/12 and 10/12, original corpus 10/10, **no unsafe draft on any**.

## Two floors on relevance - 29 September 2026

[ADR-103](../adr/0103-drafts-that-must-not-become-repairs.md). Below 0.35
relevance nothing is drafted; below 0.50 a numbered page is fault-finding text,
never a repair. Both floors sit in the gap the dev split's scores show
(answers 0.618 and up, absent symptoms 0.000).

| set | lang | outcome as the key implies | unsafe drafts |
|---|---|---:|---:|
| evaluation set, dev | en / th | 8/9 / 8/9 (unchanged) | 0 |
| evaluation set, test | en | 12/12 (unchanged) | 0 |
| evaluation set, test | th | **6/12** (was 10/12) | 0 |
| real manuals | en | **8/9** (was 9/9) | 0 |
| real manuals | th | **7/9** (was 8/9) | 0 |
| original corpus | en / th | 5/5 / 5/5 (unchanged) | 0 |

Every answer lost became "not found": EV-104, EV-111, EV-122 and EV-131 in
Thai, RD-03 in English, RD-01 in Thai. None became wrong. This is the cost of
the floors, and it falls mostly on Thai, whose relevance scores run lower.

**The ranks quoted in two places are both right.** ADR-099 gives 21st and 73rd
for two English questions; the section above gives 13th and 21st. Per question
they are RD-01 English 73rd, RD-02 English 21st and RD-01 Thai 13th.

**With 9 to 12 questions per cell, these are wide.** A Wilson 95% interval on
12/12 is 76-100%, on 6/12 25-75%, on 8/9 57-98%. "No unsafe draft" on 12
questions is compatible with an unsafe rate of up to 24%. The test split has
also been looked at after each change since ADR-097, and a change was kept when
test did not get worse, so it has been used to select changes and is no longer
fully held out.

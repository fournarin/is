# Retrieval baseline

Produced by `scripts/measure_retrieval.py`, which CI does not run and must not
(ADR-035). Committed because these numbers will be quoted in the report, and a
figure that lives only in a terminal gets quoted from memory.

**Measured 9 August 2026** ·
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions ·
corpus: 2 synthetic manuals, 18 pages, 19 chunks (ADR-033)

## Rank of the page the answer key names

| symptom | language | sparse | dense | fused |
|---|---|---:|---:|---:|
| SYM-014 | en | 2 | 2 | 2 |
| SYM-014 | th | 2 | 2 | 2 |
| SYM-021 | en | **1** | 3 | 2 |
| SYM-021 | th | **1** | 4 | 3 |
| SYM-047 | en | 1 | 1 | 1 |
| SYM-047 | th | 1 | 1 | 1 |
| SYM-002 | en | 1 | 1 | 1 |
| SYM-002 | th | 1 | 1 | 1 |

Fusion finds the answer in all 8 cases and ranks it first in 4.

## What this says, including the part that is not flattering

**Fusion does not beat the word half on this corpus, and on SYM-021 it is
worse.** Sparse ranks that answer first; dense ranks it third or fourth, and
reciprocal rank fusion averages the two into second or third. That is not a bug
in the fusion - it is what fusing a strong signal with a weak one does.

**The table cannot show what the dense half is for**, because every question in
the answer key contains a threshold figure. Slice 3.2 found that those numerals
are the only reason the word half answers a Thai question at all. Questions
without one:

| question | sparse | dense | fused |
|---|---|---|---|
| สายพานหลวมต้องทำอย่างไร *(what to do about a loose belt)* | **nothing** | 5, 11, 4 | 5, 11, 4 |
| พัดลมเสียงดังผิดปกติ *(the fan is making an unusual noise)* | **nothing** | 5, 6, 4 | 5, 6, 4 |
| the belt feels loose, what should I do | 3, 4, 5 | 4, 5, 3 | **4**, 3, 5 |

The first two are the case the whole cross-lingual requirement exists for
(ADR-029): the word half returns an empty list, and the meaning half returns the
belt pages. The third is the SYM-014 failure in a naturally phrased question -
sparse puts the overview page 3 first, fusion puts the procedure on page 4 first.

## What it is honest to conclude

1. On questions quoting an exact threshold, the word half is already right and
   fusion adds nothing. **It costs a rank on one symptom.**
2. On questions phrased the way a person speaks - especially in Thai - the word
   half returns nothing and the meaning half carries the query entirely.
3. **Nineteen chunks is too small and too clean to separate these properly.**
   Every page of the corpus is about a different subsystem, so almost any method
   finds the right one. This measurement can show that a method fails; it cannot
   establish that one is better.

## What it is not honest to conclude

That hybrid retrieval improves accuracy. It did not, here. What it did was
answer questions the other half could not answer at all, which is a different
claim and the one the report should make.

## Next measurement

A reranker is deferred until this says ordering is the problem (ADR-035). It is
not obviously the problem: the failures above are recall on one side and a
strong signal being diluted on the other. If anything, the next thing worth
measuring is whether weighting the halves by which one found a result at all
beats fusing them evenly.

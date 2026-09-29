# ADR-103: Drafts that must not become repairs

Written on 2026-09-29, from a safety review of the drafting path at `d549ca3`.
Amends ADR-097 (one relevance floor) and ADR-100 (a procedure over two pages).

## What the review found

Every result in `docs/results/rag-evaluation.md` read "no unsafe draft", and
every one was true of the questions in the answer keys. Questions outside them
found five ways a plausible wrong procedure still reached the reviewer:

1. **A weakly relevant page was drafted as a repair.** Under ADR-097's single
   0.10 floor, two questions about symptoms the manuals do not cover drew repair
   drafts from pages the reranker scored 0.107 and 0.129.
2. **A figure in the question beat relevance.** A page stating the asked figure
   at 0.11 relevance was chosen over the answer at 0.99, because the "nearly as
   relevant as the best" rule (ADR-097) was applied only to questions with no
   figures in them.
3. **A page joined to a procedure could be the answer.** ADR-100 brings in the
   page before or after a chosen page. That page carried the chosen page's score
   and could then be chosen itself on the next question's ranking.
4. **A part number read as a step marker.** "Lock out valve MV-1. 2. Open ..."
   made the "1." of "MV-1." step one's marker; step one came out empty and was
   dropped, and a draft missing its lockout step still read as complete.
5. **"Continued on page N" inside a note joined two pages** whose steps had
   nothing to do with each other.

## Decision

1. **Two floors on relevance** (`retrieval.authoring` in `policy.yaml`):
   below `min_relevance_to_draft` (0.35) nothing is drafted and the answer is
   "not found - ask an engineer"; below `min_relevance_for_repair` (0.50) a
   numbered page is drafted as fault-finding text, never as a repair. Both sit in
   the gap the evaluation set's **dev split** shows: every dev answer page scored
   0.618 or more, every absent symptom 0.000. The test split's answer pages were
   not used to place them.
2. **The "nearly as relevant" rule applies to figure-matching too.** A page
   stating the figure must score at least half the best page's relevance.
3. **A joined page is `joined_only`** and is never itself a candidate answer.
   When a procedure is chosen on its second page, the first borrows the chosen
   page's score for the repair floor, since it was brought in to join.
4. **A number glued to a word or hyphen is not a marker**, and **a procedure
   with any empty step is refused**, not drafted with the step missing.
5. **"Continued" joins only when it closes the page** (within 40 characters of
   the end), and the next page must start at the step number that follows.

## What it costs

Measured with the reranker on 2026-09-29, against the numbers before:

| set | lang | outcome as the key implies | unsafe drafts |
|---|---|---:|---:|
| evaluation set, dev | en / th | 8/9 / 8/9 (unchanged) | 0 |
| evaluation set, test | en | 12/12 (unchanged) | 0 |
| evaluation set, test | th | **6/12** (was 10/12) | 0 |
| real manuals | en | **8/9** (was 9/9) | 0 |
| real manuals | th | **7/9** (was 8/9) | 0 |

The Thai test split lost four answers (EV-104, EV-111, EV-122, EV-131) and the
real manuals one per language (RD-03 English, RD-01 Thai): the reranker scores
Thai questions lower, and those answer pages fell under the draft floor. They are now "not found", not wrong. That is the trade principle 5
asks for, and it is reported rather than tuned away: lowering the floor after
seeing the test split would turn the test split into a second dev split, which
is the mistake ADR-096 was written to stop. Calibrating the floor per language
on a dev split large enough to do it is future work.

The original corpus is in `rag-evaluation.md`.

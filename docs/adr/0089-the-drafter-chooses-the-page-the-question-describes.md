# ADR-089: The drafter chooses the page the question describes

Written on 2026-09-27. Revisits
[ADR-037](0037-drafting-selects-spans-and-a-draft-is-withheld-whole.md) §9
(the extractive backend reads the highest-scoring page) and
[ADR-086](0086-what-this-term-does-not-do.md), which closed the reranker for
this term on the argument that it was the named fix for the drafter's failures.
It changes neither decision's rule against generated text: the drafter still
quotes the manual and nothing else.

## Context

`docs/drafting-baseline.md` measured drafting on 12 August at **4 of 10**
outcomes matching the answer key. Two repairable symptoms out of three were
drafted from the wrong page, and a symptom the manuals never mention got a
six-step repair procedure at a fused score of 0.95. After a rehearsal that
leaves a technician with one approved playbook, so most tickets arrive with no
steps. The advisor asked for the system to say *how* to repair, and this was
the weakest point against that.

Retrieval was not the problem: the answer key's page was in the top three every
time (`docs/retrieval-baseline.md`). The drafter read only the first page, and
the first page was wrong in two recognisable ways:

- the belt-motor **overview** outscored the corrective procedure a page later,
  because it repeats the question's words. Both state 85 degrees; only one
  tells anybody what to do;
- the **axis 2** page outscored axis 1. The question asks about 12.5 A, and
  the axis 2 page states 11 A.

The reranker ADR-086 closed would have addressed this by meaning. The question
already carries something more exact than meaning: its figures.

## Decision

`ExtractiveDrafter` chooses its page like this:

1. Only pages of the machine model being drafted for, as before.
2. **If the question contains figures, a page is a candidate only if it states
   every one of them**, using the same `figures()` normalisation invariant 5
   uses (`1,200` equals `1200`). `figures()` moves from `authoring/drafting.py`
   to `llm/domain.py` so that both can use it, and every caller imports it
   from there.
3. Among candidates, a page with a numbered procedure comes before one without,
   then fused score, then page number for determinism.
4. **If the question has figures and no page states them, the answer is "not
   found".** That is principle 5 applied to drafting: a manual that says
   nothing about a 62-second cycle time is not answered with the nearest page.
5. A question with no figures ranks by fused score alone, exactly as before.

## Reasons

- **A figure is the most specific thing in a maintenance question.** Rules fire
  on a threshold, and a manual section that addresses the condition states it.
  Agreeing on it is a check a reviewer can repeat by eye, which a relevance
  score is not.
- **It needs no new dependency and no model.** ADR-086 closed the reranker
  because of a licence and an export problem. This decision needs neither, and
  it runs in tier 1 on every commit.
- **Measured, not argued.** Re-measured on 27 September:
  **10 of 10**, in Thai and English, with retrieval unchanged
  (`docs/drafting-baseline.md`).

## What it costs, and the assumption taken

- **A question worded with a figure the manual does not use finds nothing.** If
  the plant sets an alarm at 80 degrees and the manual says 85, "above 80
  degrees" is not found. This fails in the safe direction: nothing wrong is
  drafted, the queue files "not found", and the engineer asks again with the
  manual's figure or with none. The opposite failure, drafting from the wrong
  axis's page, puts a wrong torque in front of a reviewer.
- **Incidental figures count.** "Station 3, axis 1 above 12.5 A" requires the
  page to state 3 as well. Questions are typed by an engineer or a reviewer
  (ADR-040), not generated, so the remedy is to leave out figures that are not
  about the fault. The review screen's placeholder should say so.
- **A figure-free question about an uncovered symptom still gets a draft.** The
  gap `docs/drafting-baseline.md` described remains open for that case, and a
  DB test pins it so that closing it is noticed.
- **Tested only on the synthetic corpus.** The corpus was written with a
  `Symptom:` line on every procedure page. Real manuals state thresholds in
  troubleshooting tables more often than in prose, and pypdf may split a table
  so that a figure lands on a line of its own. `figures()` reads the whole page,
  so a split table still counts, but this has not been checked on a real manual.

## Consequences

- `README.md` and `docs/demo.md` no longer say the drafter is wrong on two of
  three symptoms. The demo can draft SYM-014 and SYM-021 live.
- ADR-086's closing of the reranker still stands for a different reason: the
  figure-free case needs a relevance magnitude, and that is what a cross-encoder
  gives.

# Drafting baseline

Produced by `scripts/measure_drafting.py`, which CI does not run and must not
(same reason as `retrieval-baseline.md`: it needs the embedding model).
Committed because these numbers will be quoted in the report, and a figure that
lives only in a terminal gets quoted from memory.

**Measured 12 August 2026** · extractive backend (no LLM) ·
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, 384 dimensions ·
authoring profile from `policy.yaml`: 40 candidates, floor 0.20, never abstains ·
corpus: 2 synthetic manuals, 18 pages, 19 chunks (ADR-033)

## What came out, per symptom

`wanted` is what the answer key's category implies: a repair draft where a
procedure exists, a fault-finding draft where the manual documents the symptom
and prescribes none, and nothing at all where the corpus is silent.

| symptom | lang | wanted | got | key page | cited | fused score | word half | figures |
|---|---|---|---|---:|---:|---:|---:|---|
| SYM-014 | en | repair | diagnostic | 4 | **3** | 1.00 | 1.600 | 1/6 |
| SYM-014 | th | repair | diagnostic | 4 | **3** | 1.00 | 0.100 | 1/6 |
| SYM-021 | en | repair | diagnostic | 7 | **8** | 0.98 | 1.000 | 0/4 |
| SYM-021 | th | repair | diagnostic | 7 | **8** | 0.98 | 0.200 | 0/4 |
| SYM-047 | en | repair | repair | 5 | 5 | 0.99 | 1.600 | 3/4, 1 misleading |
| SYM-047 | th | repair | repair | 5 | 5 | 0.99 | 0.500 | 3/4, 1 misleading |
| SYM-002 | en | diagnostic | diagnostic | 11 | 11 | 1.00 | 1.000 | - |
| SYM-002 | th | diagnostic | diagnostic | 11 | 11 | 1.00 | 0.500 | - |
| SYM-031 | en | not found | **repair** | - | 5 | 0.95 | 0.200 | - |
| SYM-031 | th | not found | **repair** | - | 5 | 0.95 | 0.100 | - |

**4 of 10 outcomes are what the answer key implies.** Every failure is one of
two things, and neither of them is the drafter.

## Failure 1: the draft is only ever as good as the page it is handed

Drafting takes the highest-scoring page for the machine model and reads it. Two
of the three repair symptoms are handed the wrong page:

- **SYM-014** gets page 3, the belt-motor *overview*, which repeats the
  question's words and gives no procedure - so the draft comes out as
  fault-finding text rather than the six-step repair on page 4. Slice 3.3 saw
  the same thing and called it "the failure reranking exists to fix".
- **SYM-021** gets page 8, which is **axis 2** - the distractor the answer key
  declared in slice 3.0, before any retriever existed: *"the same procedure and
  different figures (60 g, 8 Nm, 11 A) - a draft mixing the two reads correctly
  and is wrong."* The corpus predicted this exact failure and then caught it.

The end-to-end tests in `tests/authoring/test_drafting.py` draft all three
symptoms correctly, because the vectors declared there put the right page first.
That contrast is the point: **with the right page in front of it the drafter is
right, so what is measured here is a ranking failure and not a drafting one.**

## Failure 2: no score the system produces can say "there is nothing here"

SYM-031 is the symptom ADR-033 put in the corpus with nothing written about it
anywhere. Drafting returns a six-step repair procedure copied off the cabinet-fan
page, at a fused score of **0.95**.

That number is not a bug and no threshold fixes it:

- reciprocal rank fusion knows **positions, not distances** (ADR-035). A page
  that is first in both halves scores 1.0 whether it answers the question or is
  merely the closest of nineteen chunks;
- the vector half returns its nearest neighbours **however far away they are**;
- the word half does discriminate - 1.600 for a real English answer against
  0.200 here - but not enough to separate on: a Thai question about a documented
  symptom scores **0.100**, *below* the absent symptom's English 0.200.

So the honest position is that at authoring time the system cannot presently tell
"the manuals do not cover this" from "the manuals cover it badly", and drafting
therefore produces a draft that a reviewer has to reject. What is missing is a
**relevance magnitude**, which is what a cross-encoder produces and what ADR-035
deferred until something showed it was needed. This is that something.

`tests/authoring/test_drafting.py::TestTheSymptomNothingInTheCorpusDocuments`
pins the gap as a test, so it fails when it is closed rather than persisting
quietly.

## What did work

- **Invariant 5 held on every draft.** Every figure in every step is on the page
  the step cites, checked by reading the page back out of the index rather than
  by trusting the drafter.
- **No step ever cited the other model's manual**, on a corpus where both
  manuals document belt-motor overheating under the same heading with 42 Nm and
  28 Nm respectively.
- **The tools, duration and skill came off the page** where the page states
  them: 25 minutes and `electrical` for SYM-047, matching the answer key. Where
  the page states none, the draft says so and the reviewer supplies it.
- **The prohibition survived**: the interlock draft carries "bypassing an
  interlock to continue production is prohibited under all circumstances",
  which is the one sentence on that page a draft must never drop.

## The figure column, and the gate's known limit

`3/4, 1 misleading` for SYM-047 is the gate's limit in one line. The draft used
three of the four figures the answer key calls correct, and also the `3` that the
key records as belonging to the **hex driver size** rather than the mounting
torque - the two sit one line apart on the page and are the same numeral.

The subset gate passes it, because the figure genuinely is in the cited evidence.
Nothing mechanical here can catch that, which is why ADR-037 says so and why the
reviewer is not optional.

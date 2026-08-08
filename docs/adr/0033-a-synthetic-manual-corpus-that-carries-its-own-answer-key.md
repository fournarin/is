# ADR-033: A synthetic manual corpus, carrying its own answer key

## Context

Layer 2 has layer 1's problem and no answer for it yet.

`git.md` 4 already forbids using the plant's manuals as test fixtures: CI runs on
GitHub's machines, so a fixture under NDA is an NDA document uploaded to a third
party. That rule was written before there was any code to test. Now the next four
slices - ingest, retrieval, drafting, review - each need documents to run against,
and **none of them can be given a real one**.

There is a second problem behind the first, and it is the one that decides the
shape of the answer. Retrieval quality figures, and the authoring gate that
checks a drafted number against its cited evidence, are only as meaningful as the
documents they were measured on. A corpus of plausible-looking pages produces
plausible-looking numbers that say nothing. ADR-032 hit the same question for
signals and settled it by making the generator carry ground truth; the same is
required here, and for the same reason.

## Decision

### 1. Two synthetic manuals, committed as PDFs, in `fixtures/corpus/`

One per machine model in `plant.yaml`. Shared by the tests and by the demo seed,
so the thing being measured and the thing being shown are the same thing.

### 2. The corpus ships an answer key, not just files

A manifest records, per symptom code: which pages hold the answer, which numbers
in it are the correct ones, which required tools and skills belong to it, and
**which pages are distractors** - pages that look relevant to the same symptom
and are not.

### 3. The documents are English; the queries in the answer key are both

Which is the situation the system is actually in: manuals in English, technicians
asking in Thai.

### 4. The gaps are deliberate and declared

At least one symptom code that `rules.yaml` can raise has **no** coverage in the
corpus, so the fallback ladder - extractive span, deep link, "not found, ask an
engineer" - has something to be tested against.

### 5. The bytes are frozen

The PDFs are committed and their sha256 recorded in the manifest, with a test
that fails if the two disagree. The generator that produced them is committed as
a record of how they were made, and is **not** run by CI.

### 6. One narrow exception in `.gitignore`

`*.pdf` and `manuals/` are blocked to keep NDA documents out of the repository.
The corpus needs a single-level exception for `fixtures/corpus/*.pdf`, which is
why it does not live in a directory called `manuals/`.

## Reasons

1. **Ground truth written before the retriever exists cannot be tuned to
   flatter it.** This is the strongest argument for doing this slice first rather
   than alongside 3.3. The same person writes the corpus and the retrieval; if
   the answer key is written afterwards, "which page is correct" quietly becomes
   "which page came back", and the evaluation measures nothing. Written first, it
   is a commitment made in ignorance of the result.
2. **Distractors are the part that cannot be added later.** A corpus where every
   page is either the answer or obviously unrelated makes any retriever look
   good. The mistakes worth catching are the near misses: the same symptom
   documented for the other machine model, the torque figure that belongs to a
   different fastener on the same page. ADR-015 says reviewers are poor at
   spotting "wrong model", so the corpus has to contain the case that produces
   it.
3. **The declared gap is what keeps principle 5 honest.** "Not found - see manual
   page X or ask an engineer" is a promise the system makes when evidence is
   thin. With full coverage, that path never executes in any test, and the first
   time it runs will be in front of a technician.
4. **Frozen bytes because the document id is the sha256** (ADR-019). Generating
   the PDFs at test time would tie every document id to the version of a PDF
   library: upgrading it would silently change every id, every recorded citation
   in the fixtures, and every assertion referring to them. Committing the output
   makes regeneration a deliberate act with a visible diff.
5. **English documents with Thai queries is not a simplification; it is the
   case.** It also avoids embedding a Thai font in the fixtures, but that is a
   convenience, not the reason - the reason is that ADR-029 requires the
   embedding model to work cross-lingually, and a corpus written entirely in the
   query language would never exercise it.
6. **The corpus in the demo, not just in the tests.** ADR-007 wants a demo the
   advisor can negotiate with. A demo running on a different corpus from the one
   the accuracy figures came from is a demo that can disagree with the report.

## Consequences

- **Every retrieval or gate figure this term is a statement about this corpus**,
  and the report must say so. Two synthetic manuals written by the author are not
  evidence about Ford's documentation, and the numbers should be read as "the
  mechanism works and here is its behaviour on a corpus with known answers",
  never as an accuracy claim about the plant.
- **The corpus is a piece of adversarial writing and will be too easy.** Nobody
  writes distractors as confusing as the ones that occur naturally in a manual
  written by twenty people over ten years. Difficulty can be added later; the
  answer key's structure is what has to be right now.
- The `.gitignore` exception is a hole in a rule that exists to prevent an NDA
  leak. What notices anything else arriving in that directory is the sha manifest
  test, which fails on any PDF that is added, changed, or removed.
- Regenerating the corpus changes the document ids, which invalidates every
  citation recorded in the fixtures. That is the intended cost: it makes a change
  to the measurement baseline impossible to make casually.
- The generator drifting from the committed PDFs is possible and unchecked - CI
  verifies the bytes, not that the script still reproduces them. Accepted,
  because the alternative is running a PDF writer in CI, which is exactly the
  coupling point 4 rejects.

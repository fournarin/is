# ADR-034: PDF text with page provenance, and what happens when there is none

## Context

ADR-008 names Qdrant, PostgreSQL full-text search and reciprocal rank fusion,
but says nothing about how a PDF becomes text in the first place. Three things
have to be settled before the first chunk is written, and each of them is
awkward to change afterwards because every citation already stored depends on
it.

**What a chunk may span.** Per-step provenance is `(source_doc, page)`
(ADR-015). A chunk assembled across a page break has no single page to cite, so
either the citation becomes a range - which is not what the review screen shows
or what a technician opens - or one of the two pages is picked and is sometimes
wrong.

**What happens when a page yields nothing.** The corpus is generated text
(ADR-033) and any parser reads it. **The plant's manuals are scans.** The
author's earlier system read scanned electrical drawings with a
vision-language model precisely because that is the form these documents take.
A text parser handed a scan returns an empty string and no error, so a pipeline
built on the corpus would ingest a real manual, index nothing, and report
success.

**Which half of retrieval carries the languages.** Technicians ask in Thai and
the manuals are English (ADR-033). PostgreSQL full-text search is configured per
language; an English configuration cannot match a Thai query at all.

## Decision

### 1. `pypdf` for text extraction, in its own module

Pure Python, permissively licensed, no system packages to install on a machine
somebody else maintains. It sits behind `authoring/parsing.py` so that adding a
second stage - OCR or a vision model - changes one file.

### 2. A chunk never crosses a page boundary

Pages are split into chunks; chunks are never joined across pages. A page
shorter than the target size stays a chunk of its own rather than being merged
with its neighbour.

### 3. A page with no extractable text is recorded, not skipped

It is stored as a chunk-less page with a reason, and the document's coverage -
how many of its pages produced text - is part of what ingest reports.

### 4. The sparse half is English-only, and the cross-lingual job is not its

`english` text search configuration, and no attempt to make PostgreSQL full-text
search bridge Thai to English. Terms are joined with OR rather than AND, because
one word of a typed question that the page does not use should not remove the
page.

### 5. Chunks are derived data

Re-ingesting a document replaces its chunks. Withdrawing a document removes
them from the index while the file stays exactly where it is (ADR-019).

## Reasons

1. **Point 2 is forced by the contract, not chosen for convenience.** A step
   says "torque to 42 Nm, page 4". If the chunk it came from spanned pages 4 and
   5, that number cannot be checked by opening page 4, and the reviewer's whole
   job on the approval screen - read the step, look at the highlighted span -
   stops working. Making pages the hard boundary costs some retrieval quality on
   procedures that run across a page break, and buys a citation that is always
   exactly right.
2. **Point 3 is the difference between a limitation and a lie.** "This manual is
   indexed" and "83 of this manual's 200 pages produced text, the rest are
   scans" are different statements, and only the second one lets somebody decide
   whether to trust a search that found nothing. Silently skipping empty pages
   would make the first statement the one the system makes.
3. **Point 3 also decides what happens when real data arrives**, which is the
   moment this project has been designed around from the start. Coverage per
   document turns "the pipeline works on synthetic manuals" into a measurement
   against the real ones on day one, and it makes the case for adding OCR an
   observation rather than an argument.
4. **Point 4 is about where the cross-lingual burden sits, not about a number.**
   It belongs to the embedding model, which is exactly why ADR-029 requires a
   cross-lingual one.

   Measuring it first was worth doing, because the obvious expectation is wrong.
   A Thai question against an English index does **not** return nothing: the
   figures in it survive tokenisation, and on a corpus where every symptom is
   defined by a threshold - 85, 12.5, 1200 - those numerals are discriminating
   enough to put the right page first for two of three symptoms. That is a
   property of technical manuals rather than of the retriever, and it collapses
   the moment somebody asks a question with no number in it. Recording it here
   stops a later reading of "sparse handles Thai" from being drawn from the
   same measurement.

   OR rather than AND comes from the same measurement. Under AND, "cabinet fan
   slower than 1200 rpm" returned nothing at all, because the page says "below"
   where the question says "slower" - one wrong synonym and the answer
   disappears. ADR-015 puts recall ahead of precision at authoring, where an
   engineer reviews every candidate, so the trade goes that way.
5. **`pypdf` over the alternatives.** PyMuPDF is faster and better at layout and
   is AGPL, which is a licence question nobody wants to answer for a plant
   handover. `pdfplumber` extracts tables well and carries `pdfminer.six` with
   it; tables are where `pypdf` is weakest, and the corpus has none, so paying
   that cost now would be paying it for a capability with no consumer. When
   scanned pages arrive, the thing that gets added is a second stage, not a
   different parser.
6. **Point 5 follows from ADR-019 already calling Qdrant rebuildable.** The
   index is a projection of the documents; the documents are the record. That is
   also what makes withdrawal safe to implement as a real deletion of chunks
   while the file is untouched - design.md section 5 asks for exactly that.

## Consequences

- **Retrieval quality on procedures that span a page break is worse than it
  could be**, by construction. If that shows up in the eval, the answer is
  overlapping chunks *within* a page or a neighbour-page boost at query time -
  not chunks that span pages.
- **Coverage becomes a number the report has to carry.** Once real manuals
  arrive, "the pipeline works" is only true for the fraction of pages that
  produced text, and that fraction has to appear beside every retrieval figure
  measured on them.
- **A search almost never comes back empty**, which is the price of OR. "No
  answer" therefore has to be a decision about score, not about an empty list -
  and sparse scores are unnormalised, so the thresholds in `policy.yaml` apply
  after fusion rather than here. On the corpus the gap is wide enough to work
  with: the declared-absent symptom's best hit scores 0.20 against 1.60 for a
  symptom the manual documents.
- **The measured sparse baseline on the corpus, for 3.3 to be compared against:**
  the answer page is rank 1 for two of the three documented symptoms and rank 2
  for the third, where an overview page that repeats the question's words
  outranks the procedure page that answers it. That is the failure hybrid
  retrieval and reranking exist to fix, and it is now a number rather than an
  expectation.
- Ingest is not idempotent in the sense of leaving the table untouched: it
  replaces. Two ingests of the same document running concurrently would fight,
  which is acceptable because ingest runs as a queued job with one worker per
  class (ADR-026) and is not reachable any other way.
- No OCR, so a scanned manual ingests to zero chunks today. That is visible
  rather than silent, which is the whole of point 3, but it is still a manual
  the system cannot answer questions about.
- `pypdf` is a new runtime dependency, the first added since ADR-008. It is
  needed by the authoring worker only, and the image is shared by all three
  roles (ADR-026), so it ships to the API container as well.

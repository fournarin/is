# ADR-035: Embedding in process, vectors in Qdrant, and the fusion between them

## Context

Slice 3.2 measured the sparse half against the corpus's answer key. It puts the
right page first for two of three symptoms; on the third an overview page that
repeats the question's words outranks the procedure that answers it. And the
only reason a Thai question works at all is that the figures in it survive
tokenisation - which stops being true the moment somebody asks a question with
no number in it.

Both are the failures the dense half exists to fix. ADR-008 named Qdrant,
reciprocal rank fusion and a cross-encoder; ADR-029 put the embedding model and
reranker in process. Neither says **which model**, what the collection looks
like, or how any of it is supposed to be tested when the model is a download of
several hundred megabytes and the CI tier that may use one is the tier that must
not block a commit (lessons_carried.md 3.6).

There is also a question ADR-008 never considered, because it was written before
ADR-017 existed: **pgvector**. ADR-017 removed Redis on the grounds that a job
and its result must commit in one transaction, so there can be no result without
a job. Chunks and their vectors have exactly that shape.

## Decision

### 1. Vectors stay in Qdrant

Rejecting pgvector, with the cost recorded below rather than waved away.

### 2. Embedding and reranking run on ONNX in process, not on PyTorch

`fastembed` rather than `sentence-transformers`. Same models, same process, no
`torch`.

### 3. `paraphrase-multilingual-MiniLM-L12-v2` as the embedding model

384 dimensions, 0.22 GB, CPU-sized, cross-lingual. The reranker is **deferred**,
not chosen.

### 4. Reciprocal rank fusion is pure, and the ranks are what fuse

`fuse(sparse, dense, k)` in `retrieval/domain.py`, taking two ranked lists and
returning one. No scores cross the boundary between the halves.

### 5. Nothing that needs the model runs before tier 3

Tiers 0-2 exercise the fusion, the ports and the store against a fake embedder
with declared, hand-written vectors. The accuracy measurement against the answer
key is tier 3, run deliberately, and its result is written into the repository
as a number rather than left in a terminal.

## Reasons

1. **Qdrant over pgvector, and it is closer than ADR-008 makes it sound.**
   The argument for pgvector is ADR-017's own: one store means a chunk and its
   vector commit together, and with two there is a window where a chunk exists
   with no vector. That is a real defect and it is the reason Redis was removed.

   It loses on three counts anyway. The index is **derived data** (ADR-019):
   both halves are rebuilt by re-ingesting, so an inconsistency is repaired by
   an operation the system already has, which was not true of a job whose result
   was lost. pgvector is **not installed** in the local PostgreSQL or in the
   `postgres:16-alpine` image CI runs, so adopting it changes the database image
   on the plant's machine to satisfy a component that has a container already
   waiting in `docker-compose.yml`. And ADR-008's central argument still holds:
   one term leaves no time to learn a tool, and the author has taken Qdrant to
   production and pgvector nowhere.

   **The accepted cost:** a chunk can exist in PostgreSQL with no vector in
   Qdrant. Ingest writes PostgreSQL first, so the failure is a chunk the dense
   half cannot see - degraded retrieval, not a missing document. Re-ingesting
   repairs it.

2. **ONNX over PyTorch is about what ships to the plant.**
   `sentence-transformers` pulls `torch`, `transformers`, `scipy` and
   `scikit-learn` - roughly two gigabytes into an image that ADR-026 shares
   between `api`, `worker-runtime` and `worker-authoring`, so every one of them
   carries it. `fastembed` runs the same models through `onnxruntime` at a tenth
   of that. ADR-029 requires the embedding model to be *in process*; it does not
   require the heaviest way of getting it there.

3. **Cross-lingual is not optional, and the first choice was not available.**
   ADR-029 states the requirement: labels and questions are Thai, manuals are
   English. An English-only model would leave the Thai half of the corpus's
   answer key answerable only through its numerals, which is where slice 3.2
   already is.

   The draft of this record named `multilingual-e5-small` before checking, and
   it is not in fastembed's catalogue. What is: the MiniLM paraphrase model at
   384 dimensions and 0.22 GB, and `multilingual-e5-large` at 1024 dimensions
   and 2.24 GB. On a machine already running PostgreSQL, Qdrant and an LLM, ten
   times the weight for a better score on a corpus of nineteen chunks is the
   wrong trade; the larger model is a one-line change if the measurement asks
   for it.

   That switch carries a trap worth naming: e5 models need an instruction
   prefix on every query and passage and are worse without it, while the MiniLM
   model is trained without one and is worse *with* it. The adapter keeps a
   table rather than a decision, so changing the model does not silently change
   the prompting.

4. **The reranker is deferred on order of work, not on availability.** The first
   draft of this record said the obvious cross-encoders are English-trained,
   which is wrong: `bge-reranker-v2-m3` is multilingual, and it is already on
   this machine because the author's earlier system used it. So the reason to
   defer is not that one cannot be had.

   It is that a reranker fixes *ordering*, and nothing has yet measured whether
   ordering is what is wrong. Slice 3.2 found one symptom of three ranked
   second; if fusion alone fixes that, a reranker adds two gigabytes and a
   second model to the plant's machine to improve a number that is already
   right. Measure first, then decide - and the measurement is cheap because the
   model is already downloaded.

5. **Fusion on ranks, not scores, is what makes the two halves comparable at
   all.** `ts_rank_cd` is unbounded and cosine similarity is in [-1, 1]; any
   weighting between them is a made-up constant that changes meaning whenever
   either side is retuned. Ranks discard the magnitudes, which is precisely why
   RRF is the standard answer, and it leaves one parameter with an accepted
   default rather than two with none.

6. **Point 5's other half: it keeps `min_score` honest.** `policy.yaml` carries
   thresholds the sparse half could not use because its scores are unnormalised.
   A fused score is bounded and comparable across queries, so the abstain gate
   ADR-015 requires at runtime finally has a number it can be applied to.

7. **Point 6 on testing is the lesson from 3.6, applied before it hurts.** A
   test that downloads half a gigabyte is a test that fails on a slow network
   and is then skipped, and once one tier is routinely skipped nobody reads any
   of them. Fusion is where the bugs will be and it is pure, so it is tested
   exhaustively without a model. What genuinely needs the model is one thing -
   whether meaning-based retrieval beats word-based retrieval on this corpus -
   and that is a measurement, not a test.

## Consequences

- **The hybrid accuracy figure is produced by a command somebody runs, not by
  CI.** It therefore has to be committed to the repository next to the code that
  produced it, or it will be quoted in the report from memory of a terminal
  window. A stale number in a file is at least a number with a date on it.
- **A fake embedder is a fake.** Fusion tested against declared vectors proves
  the fusion, and nothing about whether the embedding model understands a Thai
  question about a belt motor. Those are different claims and the report must
  not merge them.
- Two stores means two things to keep in step. The reconciliation is
  re-ingesting, and there is no repair job: the same reasoning as ADR-019's
  refusal of a cleanup job, in the opposite direction.
- The model is downloaded on first use and cached. On the plant's machine, which
  may have no route to the internet, it has to be baked into the image or
  mounted - a deployment step that does not exist yet and will be found the hard
  way if it is not written down now.
- **`bge-m3` and `bge-reranker-v2-m3` are already cached on the development
  machine** from the author's earlier system. That makes the heavier path cheap
  to try and worth trying once the light one is measured - but it also means the
  laptop is not representative of the plant's machine, where nothing is cached
  and there may be no route to fetch it.
- If the measurement shows fusion no better than sparse alone on this corpus,
  that is a result to report rather than a problem to fix. Nineteen chunks of
  synthetic manual is a small and friendly corpus, and the honest conclusion may
  be that it cannot distinguish the two.

# Reranking: what the candidates are, and what disqualifies them

[ADR-035](adr/0035-embedding-in-process-vectors-in-qdrant-and-the-fusion-between.md)
deferred a cross-encoder until something showed one was needed.
[`drafting-baseline.md`](drafting-baseline.md) is that something. This page is
the survey that has to happen before the decision, and it decides nothing.

**Compiled 18 September 2026** against `fastembed` 0.8.0 as `uv.lock` pins it.
Everything in the first table was read out of the installed package rather than
from documentation.

## What the reranker is actually for

Worth getting right before choosing a model, because the obvious reading is the
wrong one.

The obvious reading is that two symptoms retrieve the wrong page - SYM-014 gets
page 3 where the key says 4, SYM-021 gets page 8 where the key says 7 - and a
reranker would promote the right one. That is true and it is the smaller half.
[`retrieval-baseline.md`](retrieval-baseline.md) shows the key page is already in
the top three every time, so the ranking error is one or two places.

The larger half is SYM-031, the symptom ADR-033 put in the corpus with nothing
written about it anywhere. Drafting returns a confident six-step repair procedure
at a fused score of **0.95**, and `drafting-baseline.md` explains why no
threshold fixes it: reciprocal rank fusion knows positions, not distances, so a
page that comes first in both halves scores 1.0 whether it answers the question
or is merely the closest of nineteen chunks. **What is missing is a relevance
magnitude**, which is the thing a cross-encoder produces and a fusion of ranks
cannot.

That distinction decides what a candidate has to do. Promoting page 4 above page
3 is a ranking job that an English-only model could do on an English corpus.
Telling "the manuals do not cover this" from "the manuals cover it badly" is a
calibration job, and it has to work on the query as typed. `drafting-baseline.md`
records the shape of that problem in one figure: a Thai question about a
documented symptom scores **0.100** on the word half, *below* the absent
symptom's English **0.200**. The failure is worst exactly where the system is
meant to be strongest.

So a candidate that cannot read Thai does not answer the question being asked of
it, even though it would improve two rows of the table.

## What is in fastembed's catalogue

| model | licence | size | Thai |
|---|---|---:|---|
| `Xenova/ms-marco-MiniLM-L-6-v2` | apache-2.0 | 0.08 GB | no |
| `Xenova/ms-marco-MiniLM-L-12-v2` | apache-2.0 | 0.12 GB | no |
| `BAAI/bge-reranker-base` | mit | 1.04 GB | no (English and Chinese) |
| `jinaai/jina-reranker-v1-tiny-en` | apache-2.0 | 0.13 GB | no |
| `jinaai/jina-reranker-v1-turbo-en` | apache-2.0 | 0.15 GB | no |
| `jinaai/jina-reranker-v2-base-multilingual` | **cc-by-nc-4.0** | 1.11 GB | yes |

Six models, one of which reads Thai, and that one is licensed for
non-commercial use only.

**cc-by-nc-4.0 disqualifies it here, and not on a technicality.** The stated end
of this project is a system installed in a plant that builds cars, and the
advisor confirmed on 2026-08-23 that the plant runs a work-order system this is
meant to feed. Shipping a non-commercial model inside an image handed to that
plant is a licence breach on the day it is useful, and the fact that it would
pass every test first is what makes it worth writing down rather than
discovering later.

## The catalogue is not the boundary

`BAAI/bge-reranker-v2-m3` is **apache-2.0**, 0.6B parameters, built on
XLM-RoBERTa, which is the same family the project already relies on for its
multilingual embedder. It is not in fastembed's catalogue, and that is the whole
of the obstacle - not the licence.

`fastembed` 0.8.0 has `TextCrossEncoder.add_custom_model`, and its signature
takes everything a registration needs:

```
add_custom_model(model, sources: ModelSource, model_file='onnx/model.onnx',
                 description='', license='', size_in_gb=0.0, additional_files=None)
```

So registering a model outside the catalogue needs no new dependency, and
**ADR-035 §2's decision to stay on fastembed and ONNX does not have to be
reopened**. `ModelSource` takes an `hf` name or a `url` and has no local-path
field, which matters less than it looks: the model is resolved through
`FASTEMBED_CACHE_PATH`, and pre-populating that cache at build time is exactly
what [ADR-079](adr/0079-the-embedding-model-ships-inside-the-image.md) already
does for the embedder, proven with `docker run --network none`. The same
mechanism carries a second model.

The remaining work is an ONNX export. The upstream repository publishes
safetensors only. Third-party ONNX conversions exist, including one from the
`onnx-community` organisation and an int8-quantised build, and a conversion can
also be produced from the apache-2.0 weights with `optimum`. **Which of those two
routes is acceptable is a decision about what goes inside an image handed to
somebody else**, and it belongs in a record rather than in a build script.

## What the decision has to weigh

- **Image size.** 0.6B parameters at F32 is roughly 2.3 GB on top of an image
  that already carries an embedder, against a demo that already wants ten
  gigabytes free. An int8 export is a fraction of that and costs accuracy that
  nobody here has measured. Issue #100 already names the image growth as
  needing its own record.
- **Where it runs.** [ADR-029](adr/0029-where-the-models-run.md) places the
  cross-encoder in process, in the API and both workers. A reranker used only at
  authoring time would not need that, and a reranker that also serves runtime
  retrieval would. The two readings imply different images and different
  boundaries, and `.importlinter` currently constrains neither.
- **Provenance of the weights.** ADR-079 bakes a model into the image precisely
  so that a machine with no route to the internet still works. That argument
  applies with more force to a file converted by a third party than to one
  pulled from its author.
- **What it would be measured against.** If the model changes, both
  [`retrieval-baseline.md`](retrieval-baseline.md) and
  [`drafting-baseline.md`](drafting-baseline.md) have to be re-measured, and the
  criterion should be fixed **before** the measurement rather than after. SYM-031
  belongs in that criterion: it is the case this whole page argues the reranker
  is for, and leaving it out would let a model that fixes two rows and still
  cannot abstain look like a success.

## What could not be tested here

No reranker was run. `huggingface.co` is not reachable from the environment this
survey was compiled in, so no model could be downloaded and no figure below the
licence column is measured. **Nothing here says a cross-encoder will fix
SYM-014, SYM-021 or SYM-031** - only that the model the evidence points at is
permissively licensed, that fastembed can carry it without a new dependency, and
that the obstacle is an export rather than a wall.

Thai is taken to be inside XLM-RoBERTa's language set rather than confirmed
against the corpus. That is the kind of claim this project does not usually
accept on a list, and it should be checked by measuring, which is the same run
that would produce the new baselines.

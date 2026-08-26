# ADR-079: The embedding model ships inside the image

Builds [ADR-029](0029-where-the-models-run.md), which put the models on the
plant's own machines and the plant's own network, and
[ADR-035](0035-hybrid-retrieval-and-where-the-vectors-live.md), which chose this
particular model. Same rule as
[ADR-019](0019-content-addressed-document-storage-served-through-the-api.md)'s
refusal of a guessed `STORAGE_DIR`: a service that starts against something it
has not got should fail at boot, not at the first request.

## Context

`OnnxEmbedder` builds `fastembed.TextEmbedding(...)`, and fastembed downloads a
model it cannot find. The class's own docstring has recorded the consequence
since it was written: *"On the plant's machine, which may have no route to the
internet, they have to be baked into the image or mounted - a deployment step
ADR-035 records as not existing yet."*

That step still did not exist, and the shape of the failure is the reason this
record is worth writing rather than a line in a runbook. On a developer's
machine and in CI there is a network, so a missing model is 0.22 GB and a pause;
nothing fails, and no test can tell the difference. On the machine ADR-029
describes - inside the plant, no route out, documents under NDA - the same code
raises a TLS error at the first uploaded document. The message says nothing
about a model, the only place it appears is `worker-authoring`'s log, and the
person watching sees a manual that uploaded fine and a review queue that never
fills.

There is a second, smaller cost even where there is a network: nothing persists
the cache, so a recreated container downloads the weights again.

## Decision

### 1. Baked into the image at build time, not mounted at run time

The alternative was a named volume populated by a documented step. It is
refused for the reason this project refuses most on-site steps: a volume is only
as good as the person who remembered to fill it, and the failure when nobody did
is the one described above - late, quiet, and phrased in the wrong vocabulary.

An image either contains the weights or does not, its digest covers them, and
the machine that needs them is the machine that loads it.

### 2. One variable, named in the code

`FASTEMBED_CACHE_PATH`, held as `MODEL_CACHE_VARIABLE` in
`pdm.retrieval.embedding` and set by the Dockerfile. `OnnxEmbedder` reads it
explicitly rather than leaving fastembed to find its own environment, so what
this system depends on is visible in the file that depends on it.

`docker-compose.yml` may set it - to the same path, or to a mounted copy - and
may not point at a different one. `tests/test_the_model_ships_in_the_image.py`
holds the three files together: the image downloads into the path it declares,
the name it bakes comes from `DEFAULT_MODEL` rather than a string repeated in
the Dockerfile, and the cache belongs to the user the worker runs as.

### 3. The build constructs the embedder rather than fetching a URL

`RUN python -c "... OnnxEmbedder() ..."`. The download is done by the same
library that will read it, at the version the lock file pins, so a fastembed
release that changes the cache layout cannot leave an image full of files the
runtime cannot use. It also means the build fails if the model name is wrong,
where a `curl` would leave a 404 in a layer nobody reads.

### 4. What it costs, said plainly

The image grows by about 0.22 GB - the figure ADR-035 already weighed when it
chose this model over the 2.24 GB one - and the build needs a network.

That split is the one this project already assumes everywhere else: the machine
that builds has the internet, the machine that runs does not. It is why the
manuals are ingested on site rather than sent anywhere (NDA), and why ADR-029
put the models on the plant's own hardware in the first place.

## Consequences

- CI's `tier 0 - the image builds` now also proves the weights resolve, at the
  cost of a slower build. The alternative was proving it on the day of an
  installation.
- Changing `DEFAULT_MODEL` changes the image, which is correct and now visible:
  the test refuses a model name written out in the Dockerfile, so the two cannot
  drift.
- `llm-server` is untouched by this. Nothing in this repository constructs
  `LlmServerDrafter`; the drafting backend is `ExtractiveDrafter` (ADR-037 §9),
  and that container currently serves nothing. Whether it should be in the
  compose file at all is a separate question and not this record's.

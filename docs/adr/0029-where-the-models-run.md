# ADR-029: Where the models run, and enforcing ADR-003 at the network layer

## Context

The stack includes three models - an embedding model for the vector store, a
cross-encoder reranker, and an LLM for drafting playbooks - and no container in
the design runs any of them.

The part that is easy to miss: **the extractive fallback is a runtime path.**
Retrieval therefore has to work at runtime as well as at authoring time, which
means the embedding model and reranker must be reachable from the API process
while the LLM must not.

## Decision

Split the models by whether runtime needs them.

| Model | Where | Reachable from |
|---|---|---|
| Embedding, cross-encoder | In process, in `api` and both workers | every process |
| LLM | A separate `llm-server` container | **`worker-authoring` only** |

`llm-server` sits on its own network, which `api` and `web` are not members of,
and the LLM module talks to it through a single HTTP interface with a swappable
backend.

## Reasons

1. **This gives ADR-003 a second enforcement layer, and a stronger one.** The
   import rule catches calls made through a module. If somebody sends an HTTP
   request directly from the API, the linter sees nothing at all. With no network
   route from `api` to the LLM, **generating at runtime becomes physically
   impossible rather than merely forbidden** - which is what the design said it
   wanted from the start.
2. **The embedding model and reranker are not separated because separating them
   prevents nothing.** Runtime needs them either way, so a separate container
   would add a hop and a thing to run while stopping nothing. They are also small
   enough to run on CPU, unlike an LLM of several gigabytes.
3. **It fits the GPU constraint from ADR-017.** The LLM holds the GPU inside one
   container, and exactly one worker with concurrency 1 talks to it, so no two
   processes contend for it.
4. **Development on a laptop needs no code change**: swap the backend for a small
   model locally and deploy with a serving stack on the plant machine, with the
   calling module unaware of the difference.

## Consequences

- The container count rises beyond what the design originally intended. **This is
  the price of running models on-premise rather than scope creep**, and three of
  the containers come from one image.
- The embedding model must handle cross-lingual retrieval, since labels and
  symptoms are in Thai while the manuals are in English.
- **New invariant: `api` must not be able to reach `llm-server`**, checked
  against the compose file and by an integration test that must fail when it
  tries. Checking only the import linter would leave this unenforced.
- If runtime ever genuinely needs an LLM, it requires a new ADR referencing this
  one, and changes to both the network and the import rules. Two barriers make a
  quiet reversal impossible, which is the intent.

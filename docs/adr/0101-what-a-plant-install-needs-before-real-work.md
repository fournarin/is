# ADR-101: What a plant install needs before real work depends on it

Written on 2026-09-28, from a security and operations audit of `95cb34b`.

## Decision

1. **A technician may take only released work.** `accept` refuses an order that
   is still `queued`, which covers both work the load gate is holding and work
   no shift lead has confirmed. Before this, the accept endpoint took any queued
   order, going round both the gate (ADR-011) and the confirmation (ADR-071).
2. **Sign-in is throttled**: five failures for one name within five minutes
   refuse that name for the rest of the window, before the password is checked.
   Each check costs 32 MiB of scrypt and a database connection.
3. **A request body must declare its length.** A chunked body is refused before
   it is read, so the upload limit cannot be bypassed by leaving the length out.
4. **The session cookie is `Secure` when the install says it serves over TLS**
   (`PDM_COOKIE_SECURE=1`, for both `api` and `web`). `docs/install.md` says how
   to put TLS in front of the web container.
5. **Dependencies with known advisories are updated**: Next.js 16.3.6 and sharp
   0.35.5 (fixing a critical Next.js image-optimiser advisory) and pypdf 6.19.
6. **Compose defaults are safe for a plant:**
   - `SIGNAL_SOURCE` defaults to `none`, not `synthetic`, so an install that
     forgot the line issues no invented work orders.
   - Every service has a memory limit (3 GB for `worker-authoring`, which loads
     the reranker).
   - Logs rotate.
   - Qdrant's telemetry is off.
   - The API is published on loopback only.
   - The rehearsal runs as its own Compose project (`pdm-rehearsal`), so
     `--fresh` can never destroy a real install's volumes.
7. **Accounts are administered from the host**: `python -m pdm.platform.auth.cli`
   with `add`, `reset-password`, `set-role` and `withdraw`. After a restore,
   `python -m pdm.platform.jobs.reindex` queues every manual for ingestion
   again. The backup and restore procedure in `docs/install.md` is rewritten to
   restore into an empty database and stop on the first error.

## Not done, and said so

- TLS itself is a deployment component this repository does not ship.
- The restore procedure has been rewritten and not yet run end to end.
- There is no LICENSE file. That is a decision for the owner and the advisor.

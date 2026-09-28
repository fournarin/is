# Installing this system

Written for somebody installing it on a machine inside the plant network, who
did not build it. [`demo.md`](demo.md) covers what to click once it is running.

Every step below that has **not** actually been carried out on a plant machine
is marked. There are several, and reading past them would be the wrong way to
use this page.

## Before you start

| | |
|---|---|
| Docker | with Compose v2 (`docker compose`, not `docker-compose`) |
| Disk | **about ten gigabytes free.** Two images are built, three are pulled, and the volumes grow from there |
| Ports | 3000 and 8000 published on the host |
| Network | outbound HTTPS is needed **once**, to build the images. After that the stack runs with no internet at all |

Check the disk first: `docker system df`. A Docker daemon that meets a full disk
part-way through a pull stops answering altogether and has to be restarted before
anything here works, which costs more time than the check does.

The embedding model is baked into the image at build time
([ADR-079](adr/0079-the-embedding-model-ships-inside-the-image.md)), so a machine
with no route to the internet indexes a manual rather than failing on the first
one with a TLS error that mentions no model. That is deliberate and it is why the
first build is slow.

## Installing

```bash
git clone <this repository> pdm
cd pdm
cp .env.example .env
```

**Open `.env` and change `POSTGRES_PASSWORD` before going further.** Keep it
URL-safe: it is interpolated into a connection string, so a password containing
`/ ? # @` produces a DSN that libpq reads as something other than what was
written. `.env.example` explains every other key in place.

Then:

```bash
docker compose up -d
docker compose logs -f api
```

The first build on a machine that has never built this takes something like
twenty minutes, most of it downloading. Subsequent builds are minutes.

### Configure the signal source before anybody sees a screen

`.env.example` ships `SIGNAL_SOURCE=synthetic`, which generates a twelve-hour
degradation scenario. **That is the demo setting.** On a plant machine set it to
`none` (an unset value also means `none`, ADR-101): the trigger loop then does not run and `worker-runtime`
reaps expired work only, which is what a deployment waiting on its OPC UA
connection should do rather than invent its own data.

`replay` reads the plant's own readings from a CSV file in `plant-data/`
(`SIGNAL_REPLAY_FILE`); [plant-data/README.md](../plant-data/README.md) has the
format and the settings. `live` (OPC UA) is **not built**, and setting it stops
the worker at boot with a message saying so. That is the intended behaviour
rather than a fault: a deployment that thinks it is reading the plant and is
not would be worse than one that refuses to start.

Left on `synthetic`, the process warns at boot. Do not remove that warning line -
on screen a generated ticket is indistinguishable from a real one, and somebody
will eventually ask which line it came from.

### The accounts

`scripts/seed_demo.py` creates the four accounts. **It generates a password for
each one and prints it once**, and that is the only time anything will show it.
Write them down before the terminal scrolls.

`--demo-passwords` uses the four printed in [`demo.md`](demo.md) instead. Those
are committed to this repository on purpose and are for a demo on a machine that
has nothing to lose. `scripts/rehearse.py` passes the flag, and runs as its own
Compose project (`pdm-rehearsal`), so its accounts live in the rehearsal's
database and not in an installation's.

Accounts are administered from the host (ADR-101):

```bash
docker compose exec api python -m pdm.platform.auth.cli list
docker compose exec api python -m pdm.platform.auth.cli add somsak "สมศักดิ์ ใจดี" technician
docker compose exec api python -m pdm.platform.auth.cli reset-password somsak
docker compose exec api python -m pdm.platform.auth.cli set-role somsak supervisor
docker compose exec api python -m pdm.platform.auth.cli withdraw somsak
```

A new or reset password is generated and printed once. Withdrawing keeps the
person's name on what they approved and closed (ADR-036) and ends their sessions
at once. **On any machine that will hold real work, withdraw the demo accounts**
if a demo was ever seeded there: `withdraw tech-1 tech-2 tech-3 sup-1 eng-1 op-1`.

### Serve it over TLS on a plant network

The web container speaks plain HTTP on port 3000. On a network phones reach
over Wi-Fi, put a TLS-terminating reverse proxy in front of it (the plant's own,
or nginx or Caddy with the plant's certificate), and then set
`PDM_COOKIE_SECURE=1` for the `api` and `web` services so the session cookie is
only ever sent over TLS. The API is published on `127.0.0.1` only and needs no
proxy: the browser never talks to it.

### Check it came up

```bash
docker compose ps
curl -fsS http://localhost:8000/health
```

Seven long-running containers should be up - `postgres`, `qdrant`, `api`,
`worker-runtime`, `worker-authoring`, `llm-server`, `web` - plus `migrate`, which
runs the database migrations once and exits. `migrate` exiting with code 0 is
correct; `migrate` exiting with anything else is the first log to read when the
API answers `/health` but signing in fails.

The web app is at `http://localhost:3000` and the API at
`http://localhost:8000`, whose `/docs` is the interactive one.

### Load the plant's technicians, roster and PM history

On a real installation, and instead of the demo roster:
[plant-data/README.md](../plant-data/README.md) gives the three CSV formats and
the one command that loads them. Every row is checked before anything is
written, and running it twice changes nothing
([ADR-091](adr/0091-plant-data-arrives-as-csv.md)).

### Load the demo data - only on a machine that has nothing to lose

```bash
uv run python scripts/rehearse.py --fresh
```

This **destroys the stack's volumes**, brings everything up cold, seeds accounts
and manuals, runs the screen checks inside the running stack
([ADR-067](adr/0067-the-rehearsal-runs-inside-the-stack-it-rehearses.md)), seeds
again over what those checks truncated, seeds a demo roster, and waits for the
first dispatch round to place work. Without `--fresh` it reuses whatever volumes
are there, which is faster and proves less.

Never run this against an installation holding real work orders.

> **Not re-verified.** The figures `demo.md` reports for what a `--fresh` run
> leaves behind - six accounts, two manuals, nineteen chunks, one approved
> playbook, two proposals waiting - were measured on 26 August 2026 and have not
> been confirmed since. Run it and read the output rather than trusting that
> table.

## Backing it up

Two things hold state that cannot be rebuilt: PostgreSQL, and the `storage`
volume holding the uploaded manuals. Qdrant is rebuilt from them.

```bash
set -a; . ./.env; set +a                 # POSTGRES_USER, POSTGRES_DB
# 1. PostgreSQL, in pg_dump's custom format so a restore can stop on the first error
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB" \
  > "pdm-$(date +%F).dump"
# 2. The storage volume
docker run --rm -v pdm_storage:/storage -v "$PWD":/out alpine \
  tar czf "/out/pdm-storage-$(date +%F).tar.gz" -C /storage .
```

The volume names are the Compose project name (`pdm`) plus the volume's name;
confirm them with `docker volume ls`.

Documents are never deleted from disk. "Delete" is a change to `documents.status`,
and there is no cleanup job, because a job that removes a PDF some closed work
order still cites destroys evidence invisibly.

## Restoring

Into an empty database, never over a populated one: restoring over live tables
mixes two histories.

```bash
set -a; . ./.env; set +a
docker compose down
docker volume rm pdm_postgres-data pdm_qdrant-data     # the stale copies
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  --exit-on-error --no-owner < pdm-YYYY-MM-DD.dump
docker run --rm -v pdm_storage:/storage -v "$PWD":/in alpine \
  sh -c 'cd /storage && tar xzf /in/pdm-storage-YYYY-MM-DD.tar.gz'
docker compose up -d
docker compose exec api python -m pdm.platform.jobs.reindex   # refill Qdrant
```

`reindex` queues every active manual for `worker-authoring` to ingest again.
Ingesting replaces what a document had, so it is safe to run twice (ADR-035).
Until it finishes, drafting finds nothing; tickets, playbooks and work orders
are all in PostgreSQL and are there at once.

## When something does not start

- `docker compose ps` - which containers are up, and which exited.
- `docker compose logs migrate` - read this first if the API answers `/health`
  but signing in fails.
- `docker compose logs api` / `web` / `worker-runtime` - in that order.
- Port 3000 is published on the host and 8000 on loopback only. Another stack already using
  them is the most common reason a rehearsal reports that nothing answered.
- `docker system df` - a daemon that hit a full disk mid-pull stops answering and
  has to be restarted.
- The review queue staying empty is usually not a fault: nothing drafts
  speculatively. A draft is written when an engineer asks for one from the gaps
  panel, and `worker-authoring` has to have finished indexing the manuals first,
  which takes about a minute after seeding.

## Running it without Compose

The three application roles - `api`, `worker-runtime`, `worker-authoring` - come
from one image and differ only in their command
([ADR-026](adr/0026-split-the-worker-into-two-roles.md)). `llm-server` sits on a
network the API cannot reach, which is
[ADR-003](adr/0003-no-llm-generated-repair-text-at-runtime.md) enforced at the
network layer rather than only by an import rule
([ADR-029](adr/0029-where-the-models-run.md)). **Any deployment that does not use
this Compose file has to reproduce that separation**, or the constraint the whole
design is built around stops being true while every test still passes.

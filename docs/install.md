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
`none`, or remove it: the trigger loop then does not run and `worker-runtime`
reaps expired work only, which is what a deployment waiting on its OPC UA
connection should do rather than invent its own data.

`replay` and `live` are the other two values ADR-002 names and **neither is
built**. Setting either stops the worker at boot with a message saying so, which
is the intended behaviour rather than a fault: a deployment that thinks it is
reading the plant and is not would be worse than one that refuses to start.

Left on `synthetic`, the process warns at boot. Do not remove that warning line -
on screen a generated ticket is indistinguishable from a real one, and somebody
will eventually ask which line it came from.

### The accounts, and what you cannot do about them yet

`scripts/seed_demo.py` creates the four accounts. **It generates a password for
each one and prints it once**, and that is the only time anything will show it.
Write them down before the terminal scrolls.

`--demo-passwords` uses the four printed in [`demo.md`](demo.md) instead. Those
are committed to this repository on purpose and are for a demo on a machine that
has nothing to lose. `scripts/rehearse.py` passes the flag, because the screen
checks sign in as those accounts by name - **so a machine that has had the
rehearsal run on it has four accounts whose passwords are public, including a
supervisor who can confirm work orders.** That is correct for a rehearsal and
wrong for anything else, and the paragraph below is why it cannot simply be
fixed afterwards.

**There is no way to change them from inside the system.** `platform/auth/repo.py`
has `set_password`, `set_role` and `deactivate`, written and documented, and no
endpoint, service or script calls any of the three. So on a real installation the
accounts are whatever the seed script made them, a role cannot be changed after
the fact, and access cannot be withdrawn without going to the database by hand:

```sql
-- withdraw access, keeping the person's name on what they approved (ADR-036)
UPDATE account SET active = false WHERE user_id = '...';
DELETE FROM session WHERE user_id = '...';
```

> **Not run, and not a substitute for the feature.** The statements above are
> what `deactivate` does, read out of the source. Nothing in this repository has
> executed them against a real installation, and account administration having
> no interface is a gap rather than a design.

Until that is closed, treat this system as one where the account list is fixed at
install time. That is defensible for a trial and is not for a plant.

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

Two sets, and only two
([ADR-019](adr/0019-content-addressed-document-storage-served-through-the-api.md) §5):

1. **PostgreSQL** - work orders, playbooks, findings, sessions, the job queue,
   and the pointers to every stored document.
2. **The `storage` volume** - the document blobs themselves, named by the sha256
   of their contents.

**Qdrant is not backed up.** Its vectors are derived data, rebuilt by re-ingesting
the documents that are already in the two sets above. On a machine somebody else
maintains, one fewer backup matters more than the rebuild time costs.

```bash
# 1. PostgreSQL
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" \
  | gzip > "pdm-$(date +%F).sql.gz"

# 2. The storage volume
docker run --rm -v pdm_storage:/storage -v "$PWD":/out alpine \
  tar czf "/out/pdm-storage-$(date +%F).tar.gz" -C /storage .
```

The volume's real name is the Compose project name plus `_storage`; confirm it
with `docker volume ls` rather than assuming the directory was called `pdm`.

Documents are never deleted from disk. "Delete" is a change to `documents.status`,
and there is no cleanup job, because a job that removes a PDF some closed work
order still cites destroys evidence invisibly. **If the disk fills, that is an
operator decision following a written procedure**, and this paragraph is the
beginning of that procedure rather than the whole of it.

> **Never run.** Neither command above has been executed against a real
> installation, and there is no script in this repository that performs a backup.
> They follow from ADR-019's structure and from the volume layout in
> `docker-compose.yml`. Before relying on them, run both and then restore into an
> empty stack - a backup nobody has restored is not a backup.

## Restoring

```bash
docker compose down
docker compose up -d postgres
gunzip -c pdm-YYYY-MM-DD.sql.gz | docker compose exec -T postgres \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
docker run --rm -v pdm_storage:/storage -v "$PWD":/in alpine \
  sh -c 'cd /storage && tar xzf /in/pdm-storage-YYYY-MM-DD.tar.gz'
docker compose up -d
```

Qdrant comes back empty. Retrieval returns nothing and the review queue cannot
fill until the documents have been re-indexed, so expect to re-ingest the manuals
after a restore.

> **Never run, and less certain than the backup.** The order above is what the
> volume layout implies, not what anybody has carried out. In particular, whether
> the running stack re-indexes on its own after an empty Qdrant comes up, or
> whether each document has to be queued again by hand, **has not been
> established**. Establish it before you need it.

## When something does not start

- `docker compose ps` - which containers are up, and which exited.
- `docker compose logs migrate` - read this first if the API answers `/health`
  but signing in fails.
- `docker compose logs api` / `web` / `worker-runtime` - in that order.
- Ports 3000 and 8000 are published on the host. Another stack already using
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

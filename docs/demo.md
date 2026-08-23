# Running the demo

What to click, in what order, and as whom. Written for the two meetings this
system exists for - the advisor's, which ADR-007 asks to be able to negotiate
with, and the trial with a technician, which ADR-014 reserves unconditionally.

Everything below is in English because the repository is; the screen labels are
quoted in Thai because that is what is on the screen.

## Before anybody is in the room

```
uv run python scripts/rehearse.py --fresh
```

That is `scripts/rehearse.py` (ADR-067): it destroys this stack's volumes, brings
all seven containers up, seeds the accounts and the manuals, runs the four
`web/check-*.py` screen checks in the order the seeding allows, seeds again over
what those checks truncated, and leaves the stack running.

Expect the first run to take a while, and to need room: it builds two images and
pulls three, and between the layers, the build cache and the volumes it wants
**something like ten gigabytes free**. Finding that out the hard way costs more
than a `docker system df` beforehand does - a Docker daemon that hits a full disk
mid-pull stops answering and has to be restarted.

It ends with four lines saying `ok` or `FAIL` and the output of each check above
them.

Without `--fresh` it reuses whatever volumes are already there, which is faster
and proves less. The report says which of the two happened.

Drive it by hand instead with the plain Compose commands:

```
docker compose --env-file .env.example up -d
docker compose --env-file .env.example logs -f api
docker compose --env-file .env.example down
```

For a real installation, copy `.env.example` to `.env` and change the password
in it first. `--env-file .env.example` is for a demo on a machine that has
nothing to lose.

## The people

`scripts/seed_demo.py` prints these, and they are in the repository on purpose.
They are for a demo on a machine inside the plant network and are not secrets.

| Sign in as | Password | Role | Offered |
|---|---|---|---|
| `tech-1` | `demo-technician` | Somchai, technician | งานของคุณ |
| `eng-1` | `demo-engineer` | Pranee, engineer | คิวรีวิว playbook · ภาพรวมสายการผลิต |
| `sup-1` | `demo-supervisor` | Anan, supervisor | คิวรีวิว playbook · ภาพรวมสายการผลิต |
| `op-1` | `demo-operator` | Malee, operator | — |

The web app is at **http://localhost:3000**, the API at
**http://localhost:8000** (its `/docs` is the interactive one).

## The order to click in

1. **Sign in as `op-1`** and stop there. An operator is offered no screens at
   all, and the page says which slice builds each one it is not offering. This is
   the shortest demonstration that ADR-024's table is enforced rather than
   described - it takes ten seconds and it is the thing people ask about last.
2. **Sign in as `eng-1`** → **ภาพรวมสายการผลิต** (`/overview`). The line drawn in
   station order with its buffers to scale, a marker per station, what the shift
   can absorb, and - at the bottom - the symptoms the system has nothing to serve
   (ADR-060, ADR-063). That last panel is the one to point at: a system that says
   what it cannot answer is the argument for principle 5 in one screen.
3. **Still as `eng-1`** → **คิวรีวิว playbook** (`/review`). The draft beside the
   page it was drafted from, per-step provenance, and approve / edit / send back
   (ADR-064). This is where ADR-003 stops being a claim: nothing reaches a
   technician that a person did not approve. **See the note below about what the
   queue contains.**
4. **Sign in as `tech-1`** → **งานของคุณ** (`/work`). One job, why it exists, why
   it is ranked where it is, its steps, and closing it in two taps (ADR-061,
   ADR-062). Open this one on a phone if there is one in the room; it is built
   for a screen at a machine, without JavaScript.

## What the demo cannot show yet, and why

Say these rather than letting somebody find them.

- **The review queue is empty after a plain seed.** `seed_demo.py` puts the
  manuals in the library; the ingest job that drafts playbooks from them is
  enqueued by the API's upload endpoint, not by the script, and drafting needs a
  model pulled into `llm-server`. Until both happen, `/review` is an empty queue
  rather than a broken screen.
- **The technician's screen has nothing to place work on.** Dispatch needs a
  roster - a technician record with skills, and a shift assignment - and
  `seed_demo.py` deliberately creates neither. It is the script an operator
  reruns on the plant's machine, and inventing technicians there would be the
  same defect as inventing signals (ADR-032, ADR-044 §5). A demo roster is a
  separate thing that does not exist yet.
- **Every work order in this demo is about a machine that is not there.**
  `SIGNAL_SOURCE=synthetic` in `.env.example`, and `worker-runtime` says so in a
  warning at boot. On screen a synthetic ticket is indistinguishable from a real
  one, so this is worth saying out loud before the first one appears rather than
  after somebody asks which line it came from.

## When something does not start

- `docker compose --env-file .env.example ps` - which containers are up, and
  which exited.
- `docker compose --env-file .env.example logs api` (or `web`, `migrate`,
  `worker-runtime`) - `migrate` is the one to read first if the API answers
  `/health` but signing in fails.
- Ports 3000 and 8000 are published on the host. Another stack already using
  them is the most common reason the rehearsal reports that nothing answered.

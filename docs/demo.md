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
all seven containers up, seeds the accounts and the manuals, runs the five
`web/check-*.py` screen checks in the order the seeding allows, seeds again over
what those checks truncated, **seeds the demo roster**, starts `worker-runtime`
and then waits for the first round to place work.

That last wait is the difference between a stack whose screens answer and a stack
with something on them. The checks each seed their own world and truncate it
again, so passing them proves the screens work and says nothing about what a
person will see; the wait ends when `scripts/demo_ready.py` finds work waiting
for the shift lead, and fails naming the link that is missing if it never
arrives.

Expect the first run to take a while, and to need room: it builds two images and
pulls three, and between the layers, the build cache and the volumes it wants
**something like ten gigabytes free**. Finding that out the hard way costs more
than a `docker system df` beforehand does - a Docker daemon that hits a full disk
mid-pull stops answering and has to be restarted.

It ends with one line per check saying `ok` or `FAIL`, and the output of each
check above them.

Before showing the stack to anybody - especially one that has been up for a
while - ask it whether it still has anything to show:

```
docker compose --env-file .env.example run --rm --no-deps rehearsal \
  python scripts/demo_ready.py
```

It walks the chain in order - accounts, roster, Findings, tickets, a round's
proposals - and names the first link that is missing rather than reporting a
total, because "no proposals" has five causes and they are fixed five different
ways.

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
| `op-1` | `demo-operator` | Malee, operator | แจ้งงานเสีย |

The web app is at **http://localhost:3000**, the API at
**http://localhost:8000** (its `/docs` is the interactive one).

## The order to click in

1. **Sign in as `op-1`** → **แจ้งงานเสีย** (`/report`). An operator is offered
   exactly one screen and it is this one: pick a machine, say how bad it is, say
   what you saw. Send it and the answer is a ticket number and the sentence that
   a shift lead still releases it (ADR-071, ADR-077).

   Two things are worth saying while it is on screen. **`critical` is not on it**
   - a report may be low, medium or high, because `high` already clears the load
   gate on a heavy shift and the level above it is reserved for a rule that
   measured something. And **the operator is offered nothing else**: no review
   queue, no line overview. Try `/review` in the address bar and the API refuses
   it and records the refusal, which is ADR-024's table enforced rather than
   described.

   Report the same machine twice to see the third refusal: the second is turned
   back naming the ticket already open, with one button to say it is a different
   fault. That is what stops four people seeing one stopped line from producing
   four tickets.
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
4. **Sign in as `sup-1`** → **ภาพรวมสายการผลิต** (`/overview`), top panel:
   **งานที่รอคุณยืนยัน**. The report from step 1 is in the queue behind this
   panel: the job the operator raised reaches a technician only once somebody
   here has released it, which is the whole of the sentence above. Every placement a round decides waits here for the
   shift lead, which is what the advisor asked for on 2026-08-23 - a person
   presses first, and automatic approval is a switch to be thrown later on
   evidence (ADR-071). Confirm one and it becomes the technician's; reject it
   with a reason and it is back in the queue for the next round.
5. **Sign in as `tech-1`** → **งานของคุณ** (`/work`). One job, why it exists, why
   it is ranked where it is, its steps, and closing it in two taps (ADR-061,
   ADR-062). Open this one on a phone if there is one in the room; it is built
   for a screen at a machine, without JavaScript.

## What the demo cannot show yet, and why

Say these rather than letting somebody find them.

- **The review queue is empty after a plain seed.** `seed_demo.py` puts the
  manuals in the library, but the ingest job that indexes them is enqueued by the
  API's upload endpoint and not by the script, so nothing is chunked, embedded or
  searchable - and a draft is assembled out of retrieved pages. Until a manual
  goes in through the API, `/review` is an empty queue rather than a broken
  screen.

  It is **not** waiting on a model. `worker-authoring` builds its drafter as
  `ExtractiveDrafter()` - the backend with no model in it (ADR-037 §9) - and
  nothing in this repository constructs the `llm-server` one. That container is
  running and currently serves nothing, which is worth saying out loud rather
  than implying a capability the stack does not have.
- **The three technicians in this demo do not exist.** Dispatch needs a roster -
  a technician record with skills, and a shift assignment - and `seed_demo.py`
  deliberately creates neither, because it is the script an operator reruns on
  the plant's own machine and inventing people there is the same defect as
  inventing signals (ADR-032, ADR-044 §5). `scripts/seed_demo_roster.py` is the
  separate script that does invent them, says so every time it runs, and refuses
  to run anywhere the demo accounts are not already present (ADR-078). The plant's
  own roster replaces every row it writes, and it is on the same request as the
  machine register and the maintenance history.

  Note the order this puts step 4 in: `policy.yaml` ships `confirmation:
  supervisor`, so a technician's screen says the work is waiting on their shift
  lead until somebody confirms it.
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
- A Docker daemon that met a full disk mid-pull stops answering altogether and
  has to be restarted before anything here works. `docker system df` first, and
  see the space this wants, above.

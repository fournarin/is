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
all seven containers up, seeds the accounts and the manuals, runs the
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

**What it leaves behind**, measured on a run of 2026-08-26 that took 4m16s from
`down -v` to the last line (the first build on a machine that has never built
this is nearer twenty minutes, most of it downloading):

| | |
|---|---|
| accounts | 6 - the four demo people, plus the two extra technicians the roster invents |
| technicians rostered | 3, on the shift that was running |
| manuals | 2, **19 chunks indexed** |
| approved playbooks | **1 - SYM-047 on the M-710iC** |
| work orders | 2, with **2 proposals waiting for the shift lead** |

That single playbook is not seeded: `web/check-the-content-path.py` drafts and
approves it while proving ADR-003 works, and leaves it there. Two consequences
worth knowing before the room fills. A ticket for an M-710iC cooling-fan fault
**will** carry steps and page numbers, which is the best thing on any of these
screens - and `SYM-047` will no longer be on the gaps panel, so step 3 below
should ask for a draft of something else.

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

`scripts/seed_demo.py --demo-passwords` prints these, and they are in the
repository on purpose. They are for a demo on a machine that has nothing to
lose, and they are not secrets.

**The flag is not optional and the default is different.** Without it the seeder
generates a password per account and prints it once, because the api and web
ports are published and an account whose password is on GitHub can confirm work
orders from anywhere on the network it is installed on. `rehearse.py` passes the
flag; a plant machine should not.

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
3. **Still as `eng-1`**, ask for a draft and then approve it. This is the walk
   that makes ADR-003 something a person watches rather than a claim they are
   asked to accept.

   On `/overview`, the panel from step 2 lists the symptoms nothing serves. Open
   **ขอร่างจากคู่มือ** under one of them and type what to ask the manual - the
   field is there because `SYM-014` retrieves nothing and "belt motor running
   above 85 degrees" retrieves the page (ADR-040). The button is an engineer's
   only: the worker behind it holds the one GPU (ADR-029).

   Ask **in Thai**: a Thai question of an English manual is the cross-lingual case
   the embedding model was chosen for (ADR-029, ADR-035), and it is the case the
   plant will actually use.

   `SYM-047` is the symptom `docs/drafting-baseline.md` measured the drafter
   getting right - but after a rehearsal it is already approved, so what is left
   on the panel is one of the two it gets wrong. That is worth showing rather
   than working around; see the third note below.

   Then **คิวรีวิว playbook** (`/review`): the draft beside the page it was
   drafted from, provenance per step, and approve / edit / send back (ADR-064).
   Approve it, and the next ticket for that symptom carries those steps with
   their page numbers instead of a fallback estimate - which is principle 2 in
   one screen.

   Three things worth saying while it is open. The drafter has **no model in it**:
   `worker-authoring` builds `ExtractiveDrafter`, which picks the highest-scoring
   page and quotes it, so what is on screen is text from the manual rather than
   text about it (ADR-037 §9). The queue fills only after `worker-authoring` has
   indexed the manuals - `seed_demo.py` queues them as it stores them, and the
   first pass takes a minute.

   And the drafter is **wrong about two of the three repair symptoms in the
   corpus**, which is worth saying before somebody finds it. `SYM-014` and
   `SYM-021` are handed an overview page that repeats the question's words rather
   than the procedure a page later; `docs/drafting-baseline.md` has the table and
   names what fixes it - a reranker, which is not built. Showing that on purpose
   is a better answer than hoping nobody asks: it is the same page a reviewer
   would reject, and rejecting it is what the screen is for.
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

- **The review queue starts empty, and fills when somebody asks.** `seed_demo.py`
  queues each manual for indexing as it stores it, so retrieval has something to
  find - but a draft is written only when an engineer asks for one, from the gaps
  panel in step 3. Nothing drafts speculatively: every draft costs a pass on the
  one GPU-bound worker (ADR-029), and a queue that fills itself is a queue its
  owner does not control.

  It is **not** waiting on a model server. `worker-authoring` builds its drafter
  as `ExtractiveDrafter()` - the backend with no model in it (ADR-037 §9) - and
  nothing in this repository constructs the `llm-server` one. That container runs
  and currently serves nothing, which is worth saying out loud rather than
  implying a capability the stack does not have.

  The **embedding** model is a different thing and does ship: it is baked into
  the image at build time (ADR-079), so a machine with no route to the internet
  indexes a manual rather than failing at the first one with a TLS error that
  says nothing about a model.
- **The technician's screen has nothing to place work on.** Dispatch needs a
  roster - a technician record with skills, and a shift assignment - and
  `seed_demo.py` deliberately creates neither. It is the script an operator
  reruns on the plant's machine, and inventing technicians there would be the
  same defect as inventing signals (ADR-032, ADR-044 §5). A demo roster is a
  separate thing that does not exist yet. With one, step 4 above comes first:
  `policy.yaml` ships `confirmation: supervisor`, so a technician's screen says
  the work is waiting on their shift lead until somebody confirms it.
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

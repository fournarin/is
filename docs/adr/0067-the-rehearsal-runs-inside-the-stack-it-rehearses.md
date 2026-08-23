# ADR-067: The rehearsal runs inside the stack it rehearses

## Context

Four scripts drive the screens the way a technician's phone does -
`web/check-sign-in.py`, `check-the-technicians-screen.py`,
`check-the-review-screen.py` and `check-the-overview-screen.py`. They are the
only things in this repository that exercise the web layer, the API and the
database together, and **no CI tier can run any of them**: each needs a
migrated database, a built web app and a running API at the same moment. The
consequence arrived on schedule - PR #70 found one of them asserting against
markup that had changed, and nothing had noticed.

The goal sentence in `CLAUDE.md` is a technician opening this system and working
from it. ADR-007 asks for a demo the advisor can negotiate with; ADR-014 reserves
the trial with a real person unconditionally. Neither can be booked until
somebody can be sure the stack still starts from nothing.

So: one script, `scripts/rehearse.py`. Four things had to be decided before it
could be written, and none of them is about test frameworks.

## Decision

### 1. The checks run inside the compose network, not on the host

A one-shot `rehearsal` container - the application image, the repository mounted
read-only, the document volume attached, on the `app` network - runs each check
with `docker compose run --rm`. It is behind a Compose profile, so a normal
`docker compose up` never starts it.

The alternative was to run them on the host, which is how their own docstrings
describe running them by hand. It needs the database published to the host, and
`docker-compose.yml` deliberately does not publish it. Adding a port for the
benefit of the rehearsal would mean **the stack being rehearsed is not the stack
that ships** - the one difference between them sitting exactly at the boundary
the rehearsal is supposed to be proving.

Inside the network the addresses are service names rather than `localhost`, so
the four scripts now read `PDM_WEB_URL` and `PDM_API_URL`, defaulting to the
published ports. The default is what a person running one by hand already has;
nothing about the by-hand path changes.

Two addresses are still polled **from the host**: `localhost:8000/health` and
`localhost:3000/sign-in`. Those are the two a person types, and a stack that
answers only on its internal names has not finished starting.

### 2. `worker-runtime` is stopped while the checks run, and started afterwards

This is the least obvious line in the script. `worker-runtime` runs a dispatch
round every `round_seconds` **even with no signal source at all** - scheduled and
reported work needs no sensor (ADR-010) - so a round lands in the middle of a
check that is asserting on the orders it seeded itself. The rehearsal brings the
stack up with that container scaled to zero, and starts it once the checks are
done, because a demo wants moving parts and the checks want none.

The cost is real and is stated here rather than hidden: the rehearsal proves
`worker-runtime` starts, and does not prove it does anything.

### 3. The order of the four is fixed by the seeding, not by their names

`check-sign-in.py` signs in as the accounts `scripts/seed_demo.py` creates. The
other three each `TRUNCATE account` and seed a world of their own - which
destroys those accounts. So the sequence is: seed, sign-in, the other three, and
**seed again at the end**. Without that last step a rehearsal reporting four
passes would leave behind a stack nobody can sign in to, which is the opposite of
what it is for.

This ordering is a property of the checks as they are written, not a decision
about how they should be. It is recorded because it is invisible in the files
themselves and a fifth check added in the wrong place would fail for a reason
nobody would find quickly.

### 4. It rehearses against `.env.example`, and cold is a flag

The env file is `.env.example`, not `.env`. A cold clone has no `.env` - copying
the example is the first thing that file's own header tells you to do - so
rehearsing against the example rehearses what a newcomer actually has, and a key
missing from it fails here rather than on their machine.

`--fresh` (`docker compose down -v`) is **opt-in**. Destroying the volumes is
what makes a start genuinely cold, and it also destroys the document store, which
ADR-019 names as one of the two things that must be backed up. A script somebody
runs to feel safe should not have a destructive default. The report says which
mode ran, so a warm pass cannot be read as a cold one.

## What the first rehearsal found

Recorded because it is the evidence for the decision above, and because each of
the three had survived every gate in `.github/workflows/ci.yml`.

1. **The image had never contained the migrations.** `alembic.ini` and
   `migrations/` were not copied in, so `alembic upgrade head` inside the
   `migrate` service failed with `No 'script_location' key found` - exit 255,
   the first time anybody asked the stack to come up. CI builds this image on
   every push and has never once started it. The stack, as shipped, had never
   run.

2. **A redirect pointed at the server's own bind address.** Three route handlers
   built their `Location` with `new URL(path, request.url)`, and `request.url`
   in a container is `http://0.0.0.0:3000` - a bind address, not a destination.
   It cannot be reproduced with `next dev` on a laptop, where the address the
   server listens on and the address the browser used are the same string. On a
   technician's phone the close screen, on a form filled in wrongly, would have
   redirected to nowhere. Fixed by sending a relative `Location`, which the
   client resolves against the URL it asked for.

3. **A check was passing for a reason unrelated to what it tested.**
   `check-the-overview-screen.py` read the API directly with a session cookie
   the jar sent only because `localhost:3000` and `localhost:8000` are one host
   and two ports, and cookies ignore the port. In the topology that ships they
   are two hosts, and the cookie was never sent. The check now attaches it
   deliberately, as its sibling `check-sign-in.py` always has.

The second is the one that matters: it is a defect in what a technician holds,
it had been in the repository since the close screen was written, and no test
that runs on one machine could have found it.

## Consequences

- `docker-compose.rehearsal.yml` is a second Compose file, and every invocation
  needs both. The script is the only caller, and `docs/demo.md` gives the plain
  `docker compose` commands for anyone driving the stack by hand.
- **This is not in CI, and that is a separate decision.** Running the whole
  compose stack in GitHub Actions has a cost in minutes and in flakiness, and it
  needs the script to exist before it can be judged. Until then the rehearsal is
  something a person runs, which means it can be forgotten - the failure mode
  this record does not fix.
- A green rehearsal says the four screens answered on one machine at one moment.
  It is not a test suite and it does not replace one gate in
  `.github/workflows/ci.yml`.

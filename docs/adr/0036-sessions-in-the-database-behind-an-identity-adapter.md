# ADR-036: Sessions in the database, behind an identity adapter

## Context

ADR-024 says who may do what and states that **no mode disables
authentication, not even for a demo** - a rule it took from the author's earlier
system, where a demonstration mode ran unauthenticated requests with elevated
rights and had to be warned about in the handover documentation. ADR-019
requires every document read to pass through RBAC and into an access log,
"without exception". Invariant 6 requires the approval endpoint to reject a
non-engineer at the endpoint rather than by hiding a button.

None of that can be built, because nothing says how a person is identified. And
the answer depends on something nobody has asked the plant yet: whether it runs
Active Directory or any other single sign-on. That is the same shape as the CMMS
question, which ADR-012 handled by putting a swappable adapter in the way until
the answer arrives.

There is also a smaller question that has to be settled now because it is
written into the database: what a stored password looks like.

## Decision

### 1. Identity comes through an adapter, and the local one is passwords

`IdentityProvider` with one implementation: accounts held in this system, with
passwords. If the plant has SSO, that becomes a second implementation and the
sessions, the roles and every endpoint stay as they are.

### 2. A session is a row, not a token that carries its own claims

An opaque random token in an `HttpOnly`, `SameSite=Strict` cookie, with the
session state in PostgreSQL. Logging out, expiry and revocation are all writes
to that row.

### 3. Passwords are hashed with `scrypt` from the standard library

No new dependency. Parameters stored beside each hash.

### 4. Role is read from the session's user on every request

Not copied into the session, and not into the cookie.

### 5. Authorisation is a dependency on the route, and the test fires the route

`requires(Role.ENGINEER)` on the endpoint. The test that proves it calls the
endpoint as a technician and requires a 403.

## Reasons

1. **The adapter is ADR-012's pattern applied to the same kind of unknown.**
   Whether the plant has AD changes the login screen, the account lifecycle and
   the joiner-leaver process, and none of that changes what an endpoint needs to
   know - which is "who is this and what role do they hold". Waiting for the
   answer would block every endpoint in the system; guessing would build a login
   that gets thrown away.

2. **A session row rather than a signed token, because revocation is a safety
   requirement here.** A JWT is valid until it expires, so a technician who has
   left the site, or an engineer whose approval rights were withdrawn this
   morning, keeps them until the clock runs out. The usual fix - a denylist -
   is a session table with more moving parts. This system approves instructions
   that people carry out on machines; the ability to stop somebody *now* is
   worth more than a stateless check.

3. **`scrypt` because it is already installed.** ADR-008 forbids a dependency
   without a record, and this is a record, so argon2 was on the table. It loses
   on the same ground as everything else in this project: `hashlib.scrypt` is
   memory-hard, in the standard library, and needs no C extension in an image
   that already carries onnxruntime. The parameters live beside each hash so
   they can be raised later without invalidating existing accounts.

4. **Role on the user rather than on the session** so that changing somebody's
   role takes effect on their next request rather than at their next login. A
   role withdrawn this morning that keeps working until somebody logs out is the
   same failure as point 2, one level up.

   This does **not** contradict `Playbook.approver_role`, which records the role
   held at the moment of approval (ADR-024). Current role governs what may be
   done now; the recorded role is evidence of what was true then, and they are
   different questions.

5. **Point 5 is what makes invariant 6 real.** A check in the frontend is a
   check that is absent from the system. The endpoint is where the decision has
   to be, and the test has to be a request rather than a call to an internal
   function, or it proves the function works and not that the route uses it.

## Consequences

- **Every endpoint from here on requires a session**, including the document
  fetch ADR-019 describes. There is no anonymous route except the login itself
  and a health check.
- **Seeding sample accounts becomes part of the demo**, because ADR-024 forbids
  turning authentication off for one. Those accounts have real roles and real
  passwords, and the seed script has to be something an operator can rerun on
  the plant's machine.
- Passwords mean a password reset path, and there is not one. For a handful of
  accounts on one node, an engineer setting a password directly is the whole
  procedure; if the plant has SSO the question disappears with the adapter.
- **The access log grows without bound.** ADR-019 requires every read logged and
  ADR-019 also refuses cleanup jobs. That is a deliberate pair on a system
  holding single-digit gigabytes, and it is the operator's decision if it ever
  matters - the same procedure as the document volume filling up.
- No rate limiting on login. On a single node behind the plant's own network the
  threat is not credential stuffing, and adding a counter without a threat to
  aim it at is the kind of security theatre that makes real controls harder to
  see. It becomes a real question the day anything is exposed beyond the plant
  network.

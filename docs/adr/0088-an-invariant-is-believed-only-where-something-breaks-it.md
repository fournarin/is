# ADR-088: An invariant is believed only where something breaks it

Written on 2026-09-20, for slice 19.3
([#108](https://github.com/fournarin/is/issues/108)), which
[ADR-086](0086-what-this-term-does-not-do.md) names as one of the three slices
this term still builds.

## Context

[`docs/invariants.md`](../invariants.md) brought the fifteen numbered invariants
into the repository, each with an **Enforced by** column naming the contract,
constraint or script that holds it. That column was written by reading the code.

Reading was not enough, twice in one day. The page's first version claimed every
entry had been checked, and for invariants 4 and 13 the check had confirmed only
that the named file existed
(entry 31 of [decisions-to-defend](../decisions-to-defend.md), and ADR-084,
which is reserved for that fix and arrives with #105). The re-check that
followed was itself partial: of the fifteen, only invariant 4 was confirmed by
running anything.

The deeper problem is that the mechanisms themselves cannot report their own
health. Three of them fail silently in the same shape:

- An `.importlinter` contract whose `source_modules` list is emptied by a rename
  passes. So does one that works.
- A CI script whose glob stops matching prints success over nothing. So does one
  run against clean documentation.
- A database constraint that was dropped by a migration refuses nothing. The
  test suite that never attempts the violation stays green.

In each case a live gate and a dead gate produce the same observation. Nothing
distinguishes them except an attempt to violate the rule, and the whole argument
for having fifteen numbered invariants is that twenty-five decision records
promise things that otherwise fail silently.

`tests/test_llm_isolation_check.py` already worked this way for invariant 15 -
a compose file written to `tmp_path` with `api` on the model network, and a
requirement that the checker reports it. That was one invariant of fifteen.

## Decision

**A mechanism is evidence only where something has been seen to break against
it.** Each invariant gets a test that commits the violation on purpose and
requires the mechanism to refuse, and `docs/invariants.md` names that test per
row, beside the mechanism.

Three consequences follow from taking that seriously.

### 1. The two kinds of gate are tested in two shapes

A mechanism inside the code - a validator, a constraint, a trigger, a refusal in
a service - is tested by attempting the violation through the narrowest path
that reaches it and asserting the refusal. Where the mechanism is a database
constraint rather than a Python rule, the attempt is made in raw SQL: going
through the repository would test the repository again, and the claim being
checked is that the state is unreachable *whoever* writes it, including a
migration or somebody with `psql` open during an incident.

A CI script or an import-linter contract is tested by building a tree that
contains the violation and running the gate against it. That requires the gate
to take its root as a parameter; `check_doc_links.py` and
`check_config_is_read.py` gain one here, and
[#105](https://github.com/fournarin/is/issues/105) gives
`check_no_wall_clock.py` the same seam for the same reason.

### 2. A mirrored contract, not a paraphrased one

An import-linter contract cannot be broken inside `src/pdm` without breaking the
build, so the violation is planted in a tree built in `tmp_path`. The contract
that tree is checked against is **read out of the real `.importlinter`**, with
one substitution: the root package name, `pdm` to `probe`, so the fixture does
not shadow the installed package.

The alternative - writing a contract of the same shape into the test - would
test import-linter rather than this repository's rules, and would keep passing
after somebody edited `.importlinter`. Reading the real file means a deleted
contract raises, a renamed module raises, and each parametrised case asserts
that the package it plants into is still on the contract's `source_modules`
list.

### 3. A row with no test says which issue brings one

The table names an issue where a test does not exist yet, rather than leaving an
empty cell. Two rows are in that state (4 and 14) and two more have a test for
part of what they claim (11 and 13); all four are
[#105](https://github.com/fournarin/is/issues/105) and
[#107](https://github.com/fournarin/is/issues/107). An empty cell reads as
"nobody got to it"; a cell naming an issue reads as "this is known, and here is
where it is tracked", and the difference matters to a reader deciding how much
of the page to trust.

**A gate that guards no invariant gets the same treatment**, for the same
reason: a gate that passes on a coincidence is worse than no gate, because it is
believed. `check_doc_links.py` and `check_config_is_read.py` are tested here.

### What this does not do

It does not tighten `check_config_is_read.py`. That gate counts a field as read
if its name appears anywhere outside the schema, which accepts a function
parameter no configured value reaches. The decision is to **plant that false
pass as a test written to pass** rather than to close it: the obvious tightening
is a data-flow claim that would be wrong in the other direction, refusing a
value read once and passed down as a keyword argument. Entry 39 of
[decisions-to-defend](../decisions-to-defend.md) carries the argument.

It also does not cover the CP-SAT planner. Invariant 10 covers `dispatch()` and
not `schedule()`, and rather than leave that as a sentence, a test plants
`import psycopg` in a mirrored `dispatch/solver.py` and requires the contract to
stay green. The boundary is asserted in both directions, so widening the
contract fails a test and forces the page to be updated with it.

## Consequences

**The Enforced by column changes meaning.** It was a reader's belief about what
a file does; beside a test that breaks the rule, it becomes a claim somebody can
re-run. "How do you know this is still true" is answered by a command rather
than by a re-reading, which is the difference this term's remaining weeks can
actually bank.

**Tests of a gate are slower than tests of a function.** The import-contract
cases each run `lint-imports` in a subprocess, because every fixture tree is
called `probe` and a second one imported in the same process would be served
from `sys.modules` as the first. Twelve cases cost a few seconds. That is the
price of testing the tool rather than a copy of it.

**A false pass written as a passing test is a strange object**, and it is
deliberate. `test_a_parameter_of_the_same_name_is_counted_as_a_read` asserts
that the gate is green on something it should arguably refuse. It documents the
limitation where a limitation cannot be skimmed past, and it fails the day
somebody tightens the gate - which is precisely the moment the docstring beside
it would otherwise have gone stale.

**Three rows still depend on another pull request.** Invariants 4, 13 and 14 get
their tests in #105. Until that lands, the page's second table has three rows
pointing at an issue, and the claim "every invariant has evidence" is not yet
true. Saying which three is the honest version of that, and it is why this
record exists separately from ADR-084 rather than inside it.

## Revisits

- **ADR-084**, reserved and arriving with
  [#105](https://github.com/fournarin/is/issues/105), fixes the mechanisms
  behind invariants 4 and 13 and brings their tests. This record is what asks
  every other row for the same evidence. It is cited here without a link
  because it is not in this branch; `docs/adr/README.md` records the
  reservation.
- [ADR-085](0085-what-the-unattended-loop-may-merge-and-a-check-that-can-stop-it.md)
  §2 puts `docs/invariants.md` among the paths the unattended loop may not merge
  on its own. This slice changes that page, so its pull request is labelled
  `human-review` and a person merges it.
- [ADR-086](0086-what-this-term-does-not-do.md) names this slice as one of the
  three the term still builds, and this record is the shape it took.

# ADR-105: What a draft must keep

Written on 2026-09-29, from a red-team pass over drafting and approval after
ADR-103. Builds on ADR-095 (a step carries the approver's Thai) and ADR-099
(what a procedure is).

## How this was found

Each case below was written first as a test describing what must happen,
and run against the code as it stood. Six failed, in
`tests/llm/test_red_team_drafting.py` and `tests/playbooks/test_steps_in_thai.py`.
The cases are shapes real manuals have; none was in either answer key, which
is why every measurement still read "no unsafe draft".

## Decision

1. **A safety notice on the page leads the draft.** Upper-case WARNING,
   CAUTION or DANGER notices that no step already contains are drafted as
   steps of their own, verbatim, citing their page, **before** step 1. Before
   this, only numbered steps were read, and a notice printed above or below them
   was dropped from a draft that still read as complete. They lead rather than
   keep their place on the page because a caution printed after the list (do not
   reuse the O-ring) is needed during the steps, not after them. The last step
   now also ends at a notice, so a notice is not swallowed into it.
2. **A procedure whose last step does not finish a sentence is not a repair.**
   A page that ends inside a step has lost the rest of the procedure, and
   drafting what remains hands over a repair without its last steps.
3. **Numbering out of order is not a procedure.** If the number after the
   last step appears before it ("1, 2, 4, 3"), the list was scrambled by
   extraction or is two lists interleaved; reading it as 1, 2, 3 merged step 4
   into step 2.
4. **A unit travels with its figure into the Thai.** The ADR-095 check compared
   figures only, so "3 Nm" rendered as "3 มม." or as a bare "3" passed.
   `contracts.wording.quantities` reads each figure written with a unit, in
   English or Thai spelling (Nm / นิวตันเมตร, mm / มม., °C / องศา, s / วินาที,
   rpm / รอบต่อนาที and others), and every quantity the step states must appear
   in its rendering with the same unit. A figure the manual writes without a unit
   is still checked by `figures` alone.

## Not done

- A notice is represented as a step, not as a field of its own. It reaches the
  technician first and goes through the same approval and Thai rendering, but a
  `cautions` field on `Playbook` would let a screen show it differently. That is
  a contract change and is left for a record of its own.
- Lower-case "Warning:" and notices printed only as pictograms are not detected.
- Units are checked in the Thai rendering, not in an engineer's edit of the
  English (ADR-064 lets a reviewer change the words; the figure there is already
  the manual's).
- The figure-on-the-wrong-line case (a hex key size of 3 used as a torque, noted
  in the report) is still caught only by the reviewer.

## Measured

Every set run again with the reranker on 2026-09-29, and every figure is what
it was under ADR-103: evaluation set dev 8/9 and 8/9, test 12/12 and 6/12;
real manuals 8/9 and 7/9; original corpus 5/5 and 5/5; no unsafe draft on any.
None of the manuals in either answer key prints a WARNING, CAUTION or DANGER
notice, so the first decision is exercised by the red-team tests alone.

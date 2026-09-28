# ADR-100: A procedure that runs over a page is drafted whole

Written on 2026-09-28.

## Context

The evaluation set's secondary cable replacement (EV-104) puts steps 1 to 4 on
page 9, ends them "Continued on page 10", and puts steps 5 to 7 on page 10. The
drafter read one page, so the draft stopped at step 4: the cable was out, and
nothing said to fit the new one, torque its clamps or check for leaks. A
procedure missing its last steps is a wrong procedure. It reads as complete and
the reviewer has to notice the gap.

## Decision

1. **Authoring pulls the neighbouring page in.** When a relevant page says
   "continued on page N" or "continued on the next page", page N is added to
   the evidence at the relevant page's score. A page that says it continues
   onto a relevant page is added the same way. The continuation often shares
   no words with the question, so it may score below the relevance floor and
   is still half the procedure.
2. **The drafter joins the steps.** Chosen on the first page, it reads that
   page's steps, removes the "continued" sentence, and joins on the next page's
   steps, numbered on from where the first stopped. Chosen on the second page,
   it starts from the page that continues onto it. **Each step cites the page
   it was read from**, so provenance stays per step (principle 2) and the
   drafting gate checks each step against its own page.
3. Tools, duration and skill are read from either page, because the footer of
   a split procedure sits on the last one.

## Consequences

Only the two phrasings above are recognised. A manual that says "cont'd" or
leaves the continuation implicit will still be drafted from one page, and the
reviewer sees a procedure that stops early. The phrasing to add is the one the
plant's manuals use.

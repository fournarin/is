# ADR-121: Drafting starts by itself, and a draft must be about the symptom

Written on 2026-10-01, from the owner's second trial (`docs/results/owner-trial.md`,
run 2, rows 4 and 6). Settles what ADR-040 and `Drafting.run` left open: where
the drafting question comes from.

## What the trial found

1. **Drafting did not look automatic.** A technician opened a job with no steps.
   An engineer then had to notice the gap, open it, and type a question before
   anything was drafted. The owner asked whether the engineer has to know more
   than the technician. The engineer is meant to check, not to author. The
   screen made them do both.
2. **A typed question drafted the wrong fault.** For SYM-002, the safety
   interlock reporting the door open, the owner typed "85 องศา". The gaps screen
   hint asked for figures. The belt-motor page answers "85 degrees" well. Its six
   steps were filed as a repair for the interlock, citing a page that is about
   something else. That is the output principle 5 calls the worst this system can
   produce, and a reviewer was its only defence.

Measured on the evaluation set, with the reranker, with each symptom asked another
symptom's question of the same model (`scripts/measure_rag.py evalset --rerank
--mismatched`): **22 unsafe drafts in 42 questions**. The relevance gate (ADR-097)
tests a page against the question, and a wrong question has relevant pages.

## Decision

1. **The trigger loop asks for a draft by itself** the first time a ticket is
   issued for a symptom with no approved steps on that machine model. The
   question is the rule's own title. It asks only if nothing has ever been
   queued or filed for the pair. After a draft has come back - approved,
   dismissed, sent back or "not found" - asking again is the engineer's
   decision, or every new Finding of an unanswered symptom would ask again. The
   ask is a row on the authoring queue: worker-runtime still has no route to the
   model (ADR-003).
2. **Every drafting job carries the symptom's own description**, the rule's
   title, beside the question. Drafting keeps a page only if it is relevant to
   the description as well as to the question, at the same floor (ADR-097). The
   test is skipped when the two are the same text, which is the automatic case.
3. **The gaps screen fills the question with the title** and says that the
   steps must be about this symptom. The old hint asked for figures, and that is
   how "85 องศา" was typed. The button reads "ขอร่างใหม่", because the first ask
   is the system's.
4. Both doors - the engineer's button and the loop - go through
   `pdm.playbooks.asking.ask`, so the rules about asking twice (ADR-040, ADR-080)
   hold whichever is used.

## What it costs, measured

`scripts/measure_rag.py evalset --rerank`, with the symptom checks added in this
record (see `docs/results/rag-evaluation.md`):

| run | dev en | dev th | test en | test th | unsafe |
|---|---:|---:|---:|---:|---:|
| question only (as before) | 8/9 | 8/9 | 12/12 | 6/12 | 0 |
| plus the description, in the other language | 8/9 | 8/9 | 9/12 | 6/12 | 0 |
| another symptom's question, no description | 0/9 | 2/9 | 0/12 | 1/12 | 22 |
| another symptom's question, with its own description | 2/9 | 2/9 | 2/12 | 2/12 | **0** |

With the description, a wrong question drafts nothing unsafe: 22 unsafe drafts
become 0, and the questions that found the wrong page say "not found" instead.
The "outcome" column is low in those two rows because the right page cannot be
found from the wrong question; that is the point of the row.

A description in a different language from the page loses three correct English
drafts on the test split (EV-104, EV-105, EV-134): the reranker scores
Thai-to-English below the floor more often. Those three become "not found -
see the manual", which is the safe failure. No floor was tuned for this, because
the dev split shows no cost to tune against (ADR-096).

## Consequences

- The automatic question is the rule's Thai title, so automatic drafts carry the
  Thai-question weakness measured on the test split (6/12, 0 unsafe). A plant
  whose manuals are in English gets better automatic drafts by titling its rules
  in the manual's words. That is a field in `rules.yaml`, not code.
- An engineer who types a better question than the title can still be refused
  when the title and the page are in different languages; the draft then says
  "not found", and the page can be read directly.

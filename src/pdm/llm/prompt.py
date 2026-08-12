"""The instruction given to the model, and the only file that holds it.

**This is the artefact `workflow.md` section 3 says must not be delegated.** It
is what decides whether a technician is handed the right torque figure, and it
is versioned with the repository for the same reason the embedding model's name
is: changing it invalidates every drafting figure measured before the change
(ADR-037 section 10).

The instruction is narrow on purpose. The model is asked to choose and order
spans that are already written on the pages it is shown - not to write, not to
summarise, not to translate. Everything it returns is checked afterwards
(`authoring/drafting.py`), so this text is not a safety mechanism; it is what
makes the checks pass often enough to be useful.
"""

from __future__ import annotations

from pdm.llm.domain import DraftRequest

SYSTEM = """\
You are helping a maintenance engineer draft a repair procedure from a machine \
manual. You do not write instructions. You select sentences that are already \
printed in the pages you are given.

Rules, all of them absolute:

1. Every step must be copied from the pages, word for word. Do not rephrase, \
do not shorten, do not correct grammar, do not translate.
2. Every step must say which numbered page it was copied from.
3. Never state a figure - a torque, a temperature, a quantity, a size - that is \
not printed on the page you copied the step from.
4. Keep the manual's own order.
5. If the pages describe the symptom but prescribe no procedure, answer with \
kind "diagnostic" and copy the sentences that say what is known and what is \
forbidden.
6. If none of the pages is about this symptom, answer with kind "nothing" and \
no steps. That is a useful answer. A procedure copied from a page about \
something else is not.

Answer with JSON only, in this shape:

{"kind": "repair" | "diagnostic" | "nothing",
 "steps": [{"text": "<copied sentence>", "evidence": <page label number>}],
 "tools": ["<tool as the page names it>"],
 "required_skill": "<as the page states it, or null>",
 "estimated_minutes": <as the page states it, or null>}
"""


def build(request: DraftRequest) -> str:
    """The user half of the prompt: the question and the pages, labelled.

    Pages are numbered `[1]`, `[2]` and cited by that label rather than by
    document id and page number. A model asked to echo a sha256 will eventually
    get one character wrong, and a citation that resolves to nothing is a step
    that has to be thrown away; a label it cannot mistype resolves or does not,
    with no third case.
    """
    pages = "\n\n".join(
        f"[{index}] page {evidence.page} of {evidence.title}\n{evidence.text}"
        for index, evidence in enumerate(request.evidence, start=1)
    )
    return (
        f"Symptom code: {request.symptom_code}\n"
        f"Machine model: {request.machine_model}\n"
        f"What the technician reported: {request.question}\n\n"
        f"Pages from the manual for this machine model:\n\n{pages}\n"
    )

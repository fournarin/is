"""What a drafting backend is shown and what it may return (ADR-037).

Deliberately free of everything else in the system. A backend sees pages of text
and returns spans of them; it never sees a `Chunk`, a connection or a config
object, so the two implementations - one that runs in process with no model at
all, one that talks to a GPU over HTTP - have the same surface and the same
things to get wrong.

Nothing here has an approval, a status or a revision. A backend cannot produce a
`Playbook`; it produces a proposal, which `authoring/` checks and turns into a
draft (ADR-003: nothing reaches a technician unreviewed).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import DocumentId, MachineModel, SymptomCode

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# A numeric literal: digits, optional thousands separators, optional decimal
# part. "5-60" is two figures rather than one, because a hyphen between numbers
# is a range in a manual and never a subtraction.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> frozenset[Decimal]:
    """Every numeric literal in the text, normalised for comparison.

    `1,200` and `1200` are one figure; so are `42` and `42.0`. Nothing here tries
    to tell a torque value from a part number: `TP-1` yields 1, and that is
    deliberate. The check runs in one direction only - is this figure present in
    the evidence - so counting more things as figures can only make it stricter
    on the step, never looser. Telling them apart would need exactly the
    judgement the gate exists to avoid making.
    """
    found: set[Decimal] = set()
    for token in _FIGURE.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")).normalize())
        except InvalidOperation:  # pragma: no cover - the pattern cannot produce one
            continue
    return frozenset(found)


# (document, page). A citation in this system is a page of a document, because
# that is what a technician can open and what `PlaybookStep` records (ADR-034).
EvidenceRef = tuple[str, int]


class Evidence(BaseModel):
    """One page of one manual, as a drafting backend sees it.

    A page rather than a chunk. Chunk boundaries are an artefact of how the text
    was cut up for the index (ADR-034), and a procedure that runs across two of
    them would otherwise reach the backend as two unrelated fragments - with the
    tools and the duration, which sit at the foot of the page, in whichever
    fragment happened to catch them.
    """

    model_config = _FROZEN

    document_id: DocumentId
    page: int = Field(ge=1)
    text: str = Field(min_length=1)
    title: str = Field(min_length=1)
    machine_model: MachineModel
    # How far the two halves of retrieval agreed on this page (ADR-035). Carried
    # through to `PlaybookStep.confidence`, which is why a backend is not asked
    # to report a confidence of its own (ADR-037 section 6).
    score: float = Field(ge=0.0, le=1.0)

    @property
    def ref(self) -> EvidenceRef:
        return (self.document_id, self.page)


class DraftRequest(BaseModel):
    """One symptom, one machine model, and the pages retrieval offered.

    The question is included because it is what retrieval was asked, and a
    backend choosing between two plausible pages needs to know which one was
    asked for - page 4 answers "motor above 85 degrees" and page 5, which
    repeats its torque figure, does not.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel
    question: str = Field(min_length=1)
    evidence: tuple[Evidence, ...] = ()

    def offered(self, ref: EvidenceRef) -> Evidence | None:
        for evidence in self.evidence:
            if evidence.ref == ref:
                return evidence
        return None


class ProposalKind(StrEnum):
    """Which of ADR-033's three categories the backend thinks it is looking at."""

    # The evidence contains instructions to carry out.
    REPAIR = "repair"
    # The manual documents the symptom and prescribes nothing, so what is owed is
    # a fault-finding playbook rather than a repair one (ADR-009).
    DIAGNOSTIC = "diagnostic"
    # Nothing here can become a step. Said out loud rather than returned as an
    # empty list, so that "the manual is silent" is distinguishable from "the
    # backend fell over" (principle 5).
    NOTHING = "nothing"


class ProposedStep(BaseModel):
    """One step a backend suggests, and the page it says it came from.

    The citation is not optional and has no "unknown" value. A step whose source
    the backend cannot name is a step nobody can check after an accident, which
    is the whole of principle 2.
    """

    model_config = _FROZEN

    text: str = Field(min_length=1)
    cites: EvidenceRef


class Proposal(BaseModel):
    """Everything a backend returns. Checked before any of it is believed."""

    model_config = _FROZEN

    kind: ProposalKind
    steps: tuple[ProposedStep, ...] = ()

    tools: tuple[str, ...] = ()
    # Raw labels as the page spells them - "robot mechanical", "45". Mapping them
    # onto the vocabulary in plant.yaml is `authoring/`'s job, because a backend
    # that could invent a skill label could assign work to nobody (invariant 13).
    required_skill: str | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)


class Drafter(Protocol):
    """The port. Two implementations, chosen by configuration (ADR-037 §9).

    `propose` is the whole of it. Anything wider - "improve this draft", "explain
    this step" - is a second way for generated text to reach a playbook, and
    ADR-003 allows exactly one.
    """

    def propose(self, request: DraftRequest) -> Proposal: ...

"""Everything that has to be true before a person is asked to review a draft.

Invariant 5 lives here: **the figures in a step are a subset of the figures in
the page it cites** (design.md section 12, defined in ADR-037 section 2). So does
the check that makes it nearly redundant today - that a step is a span of the
page it cites - and the rule that decides what happens when either fails: the
draft is withheld whole, never trimmed (ADR-037 section 4).

Pure, no I/O. `service.py` fetches the evidence and calls in here; nothing in
this module knows a database exists.

The gate cannot tell whether a step is *right*. The corpus contains the case
that proves it: the belt-motor page carries a 10 Nm guard-bolt torque one line
away from the 42 Nm mount torque, so a draft that swaps them cites evidence
genuinely containing both and is wrong. That is the reviewer's job, and the
report has to say so rather than let the clean gate result imply otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    DocumentId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    SkillId,
    SymptomCode,
)
from pdm.llm.domain import DraftRequest, Evidence, EvidenceRef, Proposal, ProposalKind

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# A numeric literal: digits, optional thousands separators, optional decimal
# part. "5-60" is two figures rather than one, because a hyphen between numbers
# is a range in a manual and never a subtraction.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")

# A step as the manual numbers it. Stripped before comparison so that a backend
# returning "2. Remove the belt guard." and one returning "Remove the belt
# guard." are the same step rather than one of them being a fabrication.
_LEADING_NUMBER = re.compile(r"^\s*\d{1,2}[.)]\s+")


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


def _comparable(text: str) -> str:
    """Whitespace collapsed, step number removed, case folded.

    Case is folded because a step is still traceable when its first letter
    changed; line breaks are collapsed because they are where the PDF wrapped,
    which is a property of the page's layout and not of what it says.
    """
    return " ".join(_LEADING_NUMBER.sub("", text).split()).casefold()


class DraftOutcome(StrEnum):
    """What came of asking for a draft. Four answers, all of them results."""

    REPAIR = "repair"
    DIAGNOSTIC = "diagnostic"
    # The corpus is silent on this symptom. Principle 5's answer, and the one
    # ADR-033 built a symptom into the corpus to keep reachable.
    NOT_FOUND = "not_found"
    # A backend produced something that did not survive the checks. Kept apart
    # from NOT_FOUND on purpose: one is a gap in the manuals that somebody should
    # fill, the other is a model somebody should stop trusting, and filing them
    # together would send a symptom whose manual page already exists to the queue
    # of symptoms nobody has written a playbook for.
    WITHHELD = "withheld"


class RejectionReason(StrEnum):
    NOT_IN_EVIDENCE = "not_in_evidence"
    FIGURE_NOT_IN_EVIDENCE = "figure_not_in_evidence"
    EVIDENCE_NOT_OFFERED = "evidence_not_offered"
    WRONG_MACHINE_MODEL = "wrong_machine_model"


class RejectedStep(BaseModel):
    """A step that did not survive, kept so the reviewer sees why.

    The text is kept verbatim. A rejected step is the evidence that a backend is
    fabricating, and a summary of it - "one step failed the figure check" - is
    not something anybody can act on.
    """

    model_config = _FROZEN

    text: str
    cites: EvidenceRef
    reason: RejectionReason
    figures_not_in_evidence: tuple[str, ...] = ()


class PlaybookDraft(BaseModel):
    """A proposal that passed every check, waiting for a person.

    Not a `Playbook`. The contract requires an estimated duration and a required
    skill, and a manual that states neither would force one to be invented here -
    a figure with the authority of the manual and the provenance of nothing
    (ADR-037 section 8). The draft carries what the page said and no more;
    `into_playbook` refuses until the gaps are filled.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel

    steps: tuple[PlaybookStep, ...] = Field(min_length=1)
    tools: tuple[str, ...] = ()

    proposed_skill: SkillId | None = None
    proposed_minutes: int | None = Field(default=None, gt=0)

    # Pages from another model's manual that retrieval offered. Never cited by a
    # step (ADR-015), and never dropped either: the reviewer is entitled to see
    # that the neighbouring model has a page on this symptom, labelled as such.
    cross_model_candidates: tuple[Evidence, ...] = ()

    @property
    def primary(self) -> tuple[DocumentId, int]:
        """The document and page most of the steps came from.

        `Playbook` records one primary source alongside the per-step provenance;
        where the steps disagree, the majority is the honest answer and the
        minority is exactly what the review screen highlights (ADR-015).
        """
        counted: dict[tuple[DocumentId, int], int] = {}
        for step in self.steps:
            counted[(step.source_doc, step.page)] = counted.get((step.source_doc, step.page), 0) + 1
        return max(counted, key=lambda ref: (counted[ref], -ref[1]))

    def into_playbook(
        self,
        *,
        required_skill: SkillId | None = None,
        estimated_minutes: int | None = None,
    ) -> Playbook:
        """The draft as a `Playbook` row, still `draft` and still unapproved.

        Arguments override what the page proposed, which is what the review
        screen will pass when the engineer corrects a value. Passing nothing uses
        the page's own figures, and raises where the page gave none rather than
        choosing for it.
        """
        skill = required_skill or self.proposed_skill
        minutes = estimated_minutes or self.proposed_minutes
        if skill is None:
            raise ValueError(
                f"{self.symptom_code} has no required_skill: the evidence stated none and none "
                "was supplied. A skill outside the vocabulary in plant.yaml cannot be assigned "
                "to anybody (invariant 13)."
            )
        if minutes is None:
            raise ValueError(
                f"{self.symptom_code} has no estimated_minutes: the evidence stated none and "
                "none was supplied. The scheduler computes with this figure, so a guess here "
                "would carry the authority of the manual and the provenance of nothing."
            )

        source_doc, page = self.primary
        return Playbook(
            symptom_code=self.symptom_code,
            machine_model=self.machine_model,
            steps=self.steps,
            tools=self.tools,
            estimated_minutes=minutes,
            required_skill=skill,
            source_doc=source_doc,
            page=page,
            status=PlaybookStatus.DRAFT,
        )


class DraftResult(BaseModel):
    """The whole answer, including the answers that are not a draft."""

    model_config = _FROZEN

    outcome: DraftOutcome
    symptom_code: SymptomCode
    machine_model: MachineModel

    draft: PlaybookDraft | None = None
    rejected: tuple[RejectedStep, ...] = ()
    # One sentence for the review queue. Every ticket carries its reason
    # (ADR-005); so does every refusal to write one.
    reason: str = Field(min_length=1)


def _check(
    step_text: str,
    ref: EvidenceRef,
    request_evidence: Evidence | None,
    machine_model: MachineModel,
    *,
    require_containment: bool,
) -> RejectedStep | None:
    if request_evidence is None:
        return RejectedStep(text=step_text, cites=ref, reason=RejectionReason.EVIDENCE_NOT_OFFERED)
    if request_evidence.machine_model != machine_model:
        return RejectedStep(text=step_text, cites=ref, reason=RejectionReason.WRONG_MACHINE_MODEL)

    missing = sorted(figures(step_text) - figures(request_evidence.text))
    if missing:
        return RejectedStep(
            text=step_text,
            cites=ref,
            reason=RejectionReason.FIGURE_NOT_IN_EVIDENCE,
            figures_not_in_evidence=tuple(str(figure) for figure in missing),
        )

    if require_containment and _comparable(step_text) not in _comparable(request_evidence.text):
        return RejectedStep(text=step_text, cites=ref, reason=RejectionReason.NOT_IN_EVIDENCE)
    return None


def _skill_from(label: str | None, skills: Iterable[str]) -> tuple[SkillId | None, str | None]:
    """The page's skill label mapped onto the vocabulary, or nothing.

    "robot mechanical" on the page is `robot_mechanical` in plant.yaml. Anything
    the vocabulary does not contain is dropped and reported: a playbook holding a
    skill nobody has is a playbook dispatch can never assign, and it would look
    complete while being unassignable (invariant 13, ADR-027).
    """
    if label is None:
        return (None, None)
    candidate = "_".join(label.strip().casefold().split())
    if candidate in set(skills):
        return (SkillId(candidate), None)
    return (None, label.strip())


def assemble(
    request: DraftRequest,
    proposal: Proposal,
    *,
    skills: Iterable[str] = (),
    cross_model: Sequence[Evidence] = (),
    require_containment: bool = True,
) -> DraftResult:
    """Check a backend's proposal and turn what survives into a draft.

    `require_containment` is the one switch, and today nothing turns it off.
    ADR-037 section 3 explains why it exists anyway: the manuals are English and
    the technicians read Thai, and the day a step is translated, containment
    cannot hold while the figure subset still must. The tests use it to drive the
    figure gate on its own, which is the only way to prove that gate can fail
    while every real backend passes it by construction.
    """
    if proposal.kind is ProposalKind.NOTHING or not proposal.steps:
        return DraftResult(
            outcome=DraftOutcome.NOT_FOUND,
            symptom_code=request.symptom_code,
            machine_model=request.machine_model,
            reason=(
                f"nothing in the corpus documents {request.symptom_code} for "
                f"{request.machine_model}"
                if not request.evidence
                else (
                    f"{len(request.evidence)} page(s) were retrieved for "
                    f"{request.symptom_code} and none of them states anything that can become "
                    "a step"
                )
            ),
        )

    rejected = [
        rejection
        for step in proposal.steps
        if (
            rejection := _check(
                step.text,
                step.cites,
                request.offered(step.cites),
                request.machine_model,
                require_containment=require_containment,
            )
        )
        is not None
    ]
    if rejected:
        # Withheld whole (ADR-037 section 4). Offering the steps that passed
        # would hand the reviewer a procedure with a hole in it that reads as
        # complete, and on the belt procedure the missing step is the one that
        # sets the tension the first three prepared for.
        return DraftResult(
            outcome=DraftOutcome.WITHHELD,
            symptom_code=request.symptom_code,
            machine_model=request.machine_model,
            rejected=tuple(rejected),
            reason=(
                f"{len(rejected)} of {len(proposal.steps)} proposed steps failed the checks in "
                f"ADR-037 ({', '.join(sorted({step.reason.value for step in rejected}))}), so the "
                "whole draft is withheld"
            ),
        )

    steps = tuple(
        PlaybookStep(
            text=_LEADING_NUMBER.sub("", step.text).strip(),
            source_doc=DocumentId(step.cites[0]),
            page=step.cites[1],
            # ADR-037 section 6: how far the two halves of retrieval agreed on
            # the page this step came from, not a number the backend reported
            # about itself.
            confidence=_offered_score(request, step.cites),
        )
        for step in proposal.steps
    )

    skill, unknown_skill = _skill_from(proposal.required_skill, skills)
    pages = sorted({(step.source_doc, step.page) for step in steps})
    notes = [
        f"{len(steps)} step(s) from "
        + ", ".join(f"page {page}" for _, page in pages)
        + f" of the {request.machine_model} manual"
    ]
    if unknown_skill is not None:
        notes.append(
            f"the page asks for skill '{unknown_skill}', which is not in the vocabulary in "
            "plant.yaml - the reviewer has to choose one"
        )
    if proposal.estimated_minutes is None:
        notes.append("the page states no duration - the reviewer has to supply one")
    if cross_model:
        notes.append(
            f"{len(cross_model)} page(s) from another model's manual were retrieved and are "
            "shown beside the draft, never cited by it"
        )

    return DraftResult(
        outcome=(
            DraftOutcome.REPAIR if proposal.kind is ProposalKind.REPAIR else DraftOutcome.DIAGNOSTIC
        ),
        symptom_code=request.symptom_code,
        machine_model=request.machine_model,
        draft=PlaybookDraft(
            symptom_code=request.symptom_code,
            machine_model=request.machine_model,
            steps=steps,
            tools=proposal.tools,
            proposed_skill=skill,
            proposed_minutes=proposal.estimated_minutes,
            cross_model_candidates=tuple(cross_model),
        ),
        reason="; ".join(notes),
    )


def _offered_score(request: DraftRequest, ref: EvidenceRef) -> float:
    evidence = request.offered(ref)
    # Unreachable once the checks above have run: a step citing a page that was
    # never offered is rejected before this is called.
    return evidence.score if evidence is not None else 0.0

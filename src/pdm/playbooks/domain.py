"""What the store holds besides the playbooks themselves. Pure, no I/O.

`Playbook` is a contract and lives in `contracts/`; this module holds the two
things around it that only this layer needs - a proposal waiting for a person,
and what a runtime lookup answers when there is nothing approved to give
(ADR-038).
"""

from __future__ import annotations

from datetime import datetime
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
    UserId,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ProposalOrigin(StrEnum):
    """Who is asking for a change. One queue holds both (design.md 4)."""

    DRAFTED = "drafted"
    TECHNICIAN = "technician"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    # Looked at and turned down. Kept rather than deleted, because in aggregate
    # dismissals are the only signal that a backend has started fabricating, and
    # because "why does this symptom still have no playbook" is otherwise
    # unanswerable (ADR-038).
    DISMISSED = "dismissed"
    # Wrong, and worth another attempt: the reviewer's note becomes the question
    # a fresh drafting job is asked. A separate status rather than a dismissal
    # with a particular note, because the two answer different questions about a
    # symptom that still has nothing to serve - nobody wants a playbook for it,
    # against the drafts so far being wrong (ADR-064).
    SENT_BACK = "sent_back"


class StepEdit(BaseModel):
    """One step the approver rewrote, before and after.

    Stored on the proposal rather than only in the approved playbook, because
    the playbook table is overwritten on the next approval (ADR-018) and the
    question this answers - *what did a person change, and which person* - is
    asked about an approval that happened months ago.
    """

    model_config = _FROZEN

    index: int = Field(ge=0)
    before: str = Field(min_length=1)
    after: str = Field(min_length=1)


def edits_between(
    steps: tuple[PlaybookStep, ...], rewritten: tuple[str, ...]
) -> tuple[StepEdit, ...]:
    """What changed between the drafted steps and the approver's text.

    Pure, and separate from the store for the usual reason (invariant 10): the
    edit rate in the report is counted from these rows, and how a difference is
    decided should be testable without a database.

    Position for position. A reviewer may reword a step; they may not add one,
    drop one or reorder them, so the two lists are the same length and index `i`
    means the same instruction in both. ADR-064 gives the reason: a shorter
    procedure that still reads as complete is the failure ADR-037 section 4
    refused to allow the drafter, and there is no argument for allowing it to
    the person the drafter is checked by.
    """
    if len(rewritten) != len(steps):
        raise ValueError(
            f"{len(rewritten)} rewritten step(s) against {len(steps)} drafted: a reviewer "
            "rewords steps, and adding or dropping one means sending the draft back (ADR-064)"
        )
    return tuple(
        StepEdit(index=index, before=step.text, after=text)
        for index, (step, text) in enumerate(zip(steps, rewritten, strict=True))
        if text != step.text
    )


def apply_edits(
    steps: tuple[PlaybookStep, ...], edits: tuple[StepEdit, ...]
) -> tuple[PlaybookStep, ...]:
    """The steps as approved: the reviewer's words, the drafter's provenance.

    `source_doc`, `page` and `confidence` are carried across untouched and are
    not editable through any path. A step whose citation a person may retype is
    a step whose citation says what somebody wished the manual said, and
    invariant 4 - every step in an approved playbook carries its source - would
    be true of the field and false of the fact (ADR-015, ADR-064).
    """
    rewritten = {edit.index: edit.after for edit in edits}
    return tuple(
        step.model_copy(update={"text": rewritten[index]}) if index in rewritten else step
        for index, step in enumerate(steps)
    )


class Proposal(BaseModel):
    """Something waiting for an engineer: a draft, or an objection.

    Carries the outcome and the rejected steps as well as the steps themselves,
    so a withheld draft is a row in the queue rather than a silence. "The drafter
    produced nothing usable and here is what it tried" is what tells a reviewer
    whether to fix the manual or to stop trusting the model (ADR-037).
    """

    model_config = _FROZEN

    proposal_id: int
    symptom_code: SymptomCode
    machine_model: MachineModel

    origin: ProposalOrigin
    # The drafting outcome, or `objection` when a technician raised it. A string
    # rather than an enum shared with `authoring/`: `playbooks/` must not import
    # the build-time side, and a copied vocabulary of five words is cheaper than
    # a shared module that would invert that dependency.
    outcome: str

    steps: tuple[PlaybookStep, ...] = ()
    tools: tuple[str, ...] = ()
    proposed_skill: SkillId | None = None
    proposed_minutes: int | None = Field(default=None, gt=0)

    rejected: tuple[dict[str, object], ...] = ()
    reason: str = Field(min_length=1)

    created_at: datetime
    created_by: UserId | None = None

    status: ProposalStatus = ProposalStatus.PENDING
    decided_by: UserId | None = None
    decided_at: datetime | None = None
    decision_note: str | None = None

    # When somebody who may review it last opened the detail, and how long from
    # that open to the decision. Never rendered: a visible clock pressures a
    # person reviewing safety-critical text into hurrying, which buys a better
    # number and a worse review (ADR-064).
    opened_at: datetime | None = None
    review_seconds: int | None = Field(default=None, ge=0)
    edits: tuple[StepEdit, ...] = ()

    @property
    def can_be_applied(self) -> bool:
        """A proposal with no steps is a report, not a replacement."""
        return self.status is ProposalStatus.PENDING and bool(self.steps)


class Served(BaseModel):
    """What a runtime lookup gives back, warning included.

    The warning is a field rather than something the caller infers from the
    status, because `needs_review` playbooks are still served (ADR-018) and the
    screen has to say why. A caller that had to remember to check the status is a
    caller that will render a superseded procedure as though nothing had changed.
    """

    model_config = _FROZEN

    playbook: Playbook
    warning: str | None = None

    @property
    def is_current(self) -> bool:
        return self.playbook.status is PlaybookStatus.APPROVED


class PendingForPair(BaseModel):
    """How many proposals are waiting for one pair, and how long the oldest has.

    The count is what the overview shows beside a machine model; the oldest is
    what says whether the queue is being worked. Both are read from the rows
    already in `playbook_proposal` - the review queue is the aggregate, and a
    second table holding a running total would be a number that can disagree
    with the rows behind it.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel
    waiting: int = Field(ge=1)
    oldest: datetime


def primary_source(steps: tuple[PlaybookStep, ...]) -> tuple[DocumentId, int]:
    """The document and page most of the steps came from.

    `Playbook` records one primary source beside the per-step provenance, and the
    majority is the honest answer to which manual this procedure is filed under.
    Taking the first step's citation instead files a playbook under whatever a
    cross-reference happened to point at - "isolate the cell following the
    procedure in the safety bulletin" is a perfectly ordinary first step, and it
    is not the manual the repair came from.
    """
    counted: dict[tuple[DocumentId, int], int] = {}
    for step in steps:
        counted[(step.source_doc, step.page)] = counted.get((step.source_doc, step.page), 0) + 1
    # Ties go to the earlier page, so the same steps always file the same way.
    return max(counted, key=lambda ref: (counted[ref], -ref[1]))


def cited_documents(steps: tuple[PlaybookStep, ...], source_doc: DocumentId) -> tuple[str, ...]:
    """Every manual this playbook depends on, for the withdrawal cascade.

    The primary document is included even when no step cites it, because it is
    what the playbook is filed under and replacing it is exactly the event the
    cascade exists for (ADR-018).
    """
    return tuple(sorted({source_doc, *(step.source_doc for step in steps)}))

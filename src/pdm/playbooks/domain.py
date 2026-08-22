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

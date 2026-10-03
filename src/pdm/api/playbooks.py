"""The review queue and the approval endpoint (ADR-038, invariant 6).

This is where invariant 6 lives: *only an engineer may approve, checked at the
endpoint rather than by hiding a button*. `requires(Role.ENGINEER, ...)` refuses
with a 403 and writes the attempt to the access log either way, so an operator
who found the URL is refused and recorded rather than refused and forgotten.

The service refuses a non-engineer as well, because the worker and the seed
script never pass through here. Two checks for one rule is not duplication; a
rule enforced in one of two entry points is a rule with a way round it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.api.deps import Db, Jobs, Plant, requires
from pdm.api.work_orders import Orders
from pdm.contracts import MachineModel, PlaybookStep, Role, SkillId, SymptomCode
from pdm.platform.auth.domain import Account
from pdm.platform.jobs import JobKind
from pdm.playbooks import asking
from pdm.playbooks.domain import Proposal
from pdm.playbooks.repo import NothingToApply
from pdm.playbooks.service import NotADraft, NotAnEngineer, PlaybookStore

router = APIRouter(tags=["playbooks"])

_MAY_REVIEW = (Role.ENGINEER, Role.SUPERVISOR)


def store(request: Request) -> PlaybookStore:
    playbook_store: PlaybookStore = request.app.state.playbooks
    return playbook_store


Store = Annotated[PlaybookStore, Depends(store)]


class ProposalSummary(BaseModel):
    """One line of the review queue.

    The steps are not in it. A queue that carried every step of every proposal
    would be a screen that loads slowly and is read carelessly; what a reviewer
    picks from the list is the symptom, where it came from and how old it is.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: int
    symptom_code: SymptomCode
    # The symptom as the plant names it (ADR-126): the third trial's engineer
    # saw only "SYM-014" and could not check the draft was about the right fault.
    symptom_title: str | None = None
    machine_model: MachineModel
    origin: str
    outcome: str
    steps: int
    rejected: int
    reason: str
    created_at: datetime
    created_by: str | None

    @classmethod
    def of(cls, proposal: Proposal) -> ProposalSummary:
        return cls(
            proposal_id=proposal.proposal_id,
            symptom_code=proposal.symptom_code,
            machine_model=proposal.machine_model,
            origin=proposal.origin.value,
            outcome=proposal.outcome,
            steps=len(proposal.steps),
            rejected=len(proposal.rejected),
            reason=proposal.reason,
            created_at=proposal.created_at,
            created_by=proposal.created_by,
        )


class ProposalDetail(BaseModel):
    """Everything a person needs to decide, including what was refused.

    `rejected` is shown rather than logged. A draft that lost three steps to the
    figure gate is a different thing from one that never had them, and the
    reviewer is the only one who can tell whether the manual is wrong or the
    backend is (ADR-037).

    **`opened_at` and `review_seconds` are deliberately not on it.** The numbers
    are recorded and they matter for the report; a screen that could read them
    is a screen that can show a clock, and a visible timer pressures somebody
    reviewing safety-critical text into hurrying - which buys a better number
    and a worse review. Not serialising them is what makes "no timer on screen"
    a property of the API rather than a promise about the markup (ADR-064).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: int
    symptom_code: SymptomCode
    symptom_title: str | None = None
    machine_model: MachineModel
    origin: str
    outcome: str
    status: str
    reason: str
    steps: tuple[PlaybookStep, ...]
    tools: tuple[str, ...]
    proposed_skill: SkillId | None
    proposed_minutes: int | None
    rejected: tuple[dict[str, object], ...]
    created_at: datetime
    created_by: str | None


class Approval(BaseModel):
    """What the engineer fills in where the manual stated nothing."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    # "Edit and approve": the reviewer's wording for every step, position for
    # position, or nothing at all. Text only - the citation on each step is
    # carried across from the draft and is not editable through this or any
    # other path, because a step whose source a person may retype is a step that
    # says what somebody wished the manual said (ADR-064, invariant 4).
    steps: tuple[str, ...] | None = None
    # The approver's Thai for each step, position for position; blank for none
    # (ADR-095).
    thai_steps: tuple[str, ...] | None = None
    required_skill: SkillId | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    # ADR-025: a two-person job consumes twice the shift's capacity, and the
    # default of one is what makes load_ratio read low. Nothing drafts it, so the
    # approver is the only person who can say.
    required_technicians: int | None = Field(default=None, ge=1, le=4)
    note: str | None = None

    @field_validator("steps")
    @classmethod
    def _no_empty_step(cls, value: tuple[str, ...] | None) -> tuple[str, ...] | None:
        """A blank step is not an edit, and the screen's textarea can produce one.

        Deleting a step is a change to the shape of the procedure, which the
        approval path does not do: what it means is that the draft is wrong, and
        the button for that is "send back" (ADR-064).
        """
        if value is not None and any(not text.strip() for text in value):
            raise ValueError("a step cannot be blank; deleting a step means sending the draft back")
        return value


class DraftRequested(BaseModel):
    """Ask the authoring worker for a draft of one symptom."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symptom_code: SymptomCode
    machine_model: MachineModel
    # What retrieval is asked, in the requester's words. On the job rather than
    # derived from the symptom code, because a drafting result is reproducible
    # only if what produced it was recorded (ADR-039 section 7) - and because
    # SYM-014 retrieves nothing while "belt motor running above 85 degrees"
    # retrieves the page.
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", which retrieves nothing and then files a
        `not_found` proposal reading as "the manuals do not answer this" - a
        statement about the corpus made on the strength of a typo (ADR-040)."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("a drafting question cannot be only whitespace")
        return stripped


class SentBack(BaseModel):
    """What is wrong with the draft, which is also the next drafting question."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    note: str = Field(min_length=1)


class Dismissal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    # Required, and not just non-empty by convention: the dismissals are what
    # answer "why does this symptom still have no playbook" (ADR-038 §6).
    note: str = Field(min_length=1)


@router.post("/playbooks/drafts", status_code=status.HTTP_202_ACCEPTED)
def request_draft(
    requested: DraftRequested,
    conn: Db,
    jobs: Jobs,
    config: Plant,
    account: Annotated[Account, Depends(requires(Role.ENGINEER, action="request_draft"))],
) -> dict[str, Any]:
    """Queue a drafting job. 202, because nothing has been drafted yet.

    An engineer only. Not because drafting is dangerous - nothing it produces
    reaches a technician without an approval that is also engineer-only - but
    because the worker behind it holds the one GPU (ADR-029), and a queue anybody
    can fill is a queue the person who has to empty it does not control.

    Asking twice for something already coming, or already waiting for review, is
    answered with what is coming (ADR-040, ADR-080); `pdm.playbooks.asking`
    holds both rules, because the trigger loop asks through it too (ADR-121).
    The rule's own description of the symptom travels with the job, so drafting
    can refuse pages that answer the typed question and not the fault.
    """
    asked = asking.ask(
        conn,
        jobs,
        symptom_code=requested.symptom_code,
        machine_model=requested.machine_model,
        question=requested.question,
        symptom=config.wording().symptom(requested.symptom_code),
    )
    if asked.awaiting_review is not None:
        return {
            "proposal": asked.awaiting_review,
            "symptom_code": requested.symptom_code,
            "awaiting_review": True,
        }
    assert asked.job is not None
    return {
        "job": asked.job,
        "symptom_code": requested.symptom_code,
        "status": "queued",
        "queued_already": asked.queued_already,
    }


@router.get("/playbooks/queue", response_model=list[ProposalSummary])
def review_queue(
    conn: Db,
    playbooks: Store,
    config: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_REVIEW, action="list_review_queue"))],
    # Bounded on both sides. Unbounded it reaches LIMIT %s, where a negative
    # number is a PostgreSQL error the caller sees as a 500 and a large one is a
    # screen nobody reads.
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ProposalSummary]:
    """One list, both origins, oldest first (design.md 4).

    A supervisor may look. Only an engineer may approve, which is the next
    handler and a different check - seeing the queue is not authority over its
    contents, and a supervisor who cannot see it cannot ask why it is not moving.
    """
    wording = config.wording()
    return [
        ProposalSummary.of(item).model_copy(
            update={"symptom_title": wording.symptom(item.symptom_code)}
        )
        for item in playbooks.review_queue(conn, limit=limit)
    ]


@router.get("/playbooks/queue/{proposal_id}", response_model=ProposalDetail)
def proposal_detail(
    proposal_id: int,
    conn: Db,
    playbooks: Store,
    config: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_REVIEW, action="read_proposal"))],
) -> ProposalDetail:
    """One proposal, and the note that somebody has just opened it.

    The open is recorded here rather than by the screen sending a timestamp,
    which is what makes "how long does a review take" a figure the report can
    quote (ADR-064). It is a write on a GET, deliberately: the alternative is a
    clock in the browser, and a clock in the browser is both a number this
    system cannot vouch for and a timer somebody reviewing safety-critical text
    can see.
    """
    from pdm.playbooks import repo

    found = repo.proposal(conn, proposal_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"no proposal {proposal_id}")
    playbooks.opened(conn, proposal_id)
    return ProposalDetail(
        proposal_id=found.proposal_id,
        symptom_code=found.symptom_code,
        symptom_title=config.wording().symptom(found.symptom_code),
        machine_model=found.machine_model,
        origin=found.origin.value,
        outcome=found.outcome,
        status=found.status.value,
        reason=found.reason,
        steps=found.steps,
        tools=found.tools,
        proposed_skill=found.proposed_skill,
        proposed_minutes=found.proposed_minutes,
        rejected=found.rejected,
        created_at=found.created_at,
        created_by=found.created_by,
    )


@router.post("/playbooks/queue/{proposal_id}/approve", status_code=status.HTTP_200_OK)
def approve(
    proposal_id: int,
    approval: Approval,
    conn: Db,
    playbooks: Store,
    work_orders: Orders,
    config: Plant,
    account: Annotated[Account, Depends(requires(Role.ENGINEER, action="approve_playbook"))],
) -> dict[str, Any]:
    """Invariant 6. Anybody else gets a 403 from the dependency above.

    The role written onto the row is the one the account holds **now**, read at
    this moment and frozen there: ADR-024's distinction between "what may this
    person do today" and "what were they when they signed it".
    """
    try:
        playbook = playbooks.approve(
            conn,
            proposal_id,
            approver=account.user,
            approver_role=account.role,
            required_skill=approval.required_skill,
            estimated_minutes=approval.estimated_minutes,
            required_technicians=approval.required_technicians,
            note=approval.note,
            rewritten_steps=approval.steps,
            thai_steps=approval.thai_steps,
        )
        # The orders already waiting on this symptom get the steps now, rather
        # than a technician being told none exist (ADR-102).
        work_orders.adopt(
            conn,
            playbook,
            machine_ids=config.machines_of(playbook.machine_model),
        )
    except NothingToApply as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except NotAnEngineer as error:  # pragma: no cover - the dependency refuses first
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error
    except ValueError as error:
        # The proposal states no skill or no duration and the approver supplied
        # neither. A 422 rather than a 500: the request is answerable, and the
        # answer is "tell me which".
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    return {
        "symptom_code": playbook.symptom_code,
        "machine_model": playbook.machine_model,
        "revision": playbook.revision,
        "status": playbook.status.value,
        "approved_by": playbook.approved_by,
    }


@router.post("/playbooks/queue/{proposal_id}/send-back", status_code=status.HTTP_200_OK)
def send_back(
    proposal_id: int,
    sending_back: SentBack,
    conn: Db,
    jobs: Jobs,
    playbooks: Store,
    config: Plant,
    account: Annotated[Account, Depends(requires(Role.ENGINEER, action="send_back_proposal"))],
) -> dict[str, Any]:
    """Refuse the draft and ask for another, in one transaction.

    The refusal and the job that answers it commit together, which is ADR-017's
    argument in the small: a run that recorded the refusal and lost the request
    would leave a symptom with nothing to serve and nothing coming, and nobody
    would know to press the button again.

    The reviewer's note becomes the question. "SYM-014" retrieves nothing while
    "the belt tension procedure, not the motor one" retrieves the page - and it
    is also the only thing that makes a second attempt different from the first
    (ADR-039 section 7, ADR-064).
    """
    try:
        decided = playbooks.send_back(
            conn,
            proposal_id,
            decided_by=account.user,
            decided_role=account.role,
            note=sending_back.note,
        )
    except NothingToApply as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except NotADraft as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    pair: dict[str, object] = {
        "symptom_code": decided.symptom_code,
        "machine_model": decided.machine_model,
    }
    # The same courtesy `request_draft` extends (ADR-040): a redraft already
    # queued for this pair is the answer to this one as well, and each press
    # costs a pass on the one GPU.
    #
    # The note is the question; the rule's description of the symptom goes with
    # it, so a note that reads like another fault cannot draft that fault's page
    # under this one (ADR-121).
    already = jobs.pending(conn, kind=JobKind.DRAFT, payload=pair)
    job = already or jobs.enqueue(
        conn,
        kind=JobKind.DRAFT,
        payload={
            **pair,
            "question": sending_back.note,
            "symptom": config.wording().symptom(decided.symptom_code),
        },
    )
    return {
        "proposal_id": decided.proposal_id,
        "status": decided.status.value,
        "job": job.id,
        "queued_already": already is not None,
    }


@router.post("/playbooks/queue/{proposal_id}/dismiss", status_code=status.HTTP_200_OK)
def dismiss(
    proposal_id: int,
    dismissal: Dismissal,
    conn: Db,
    playbooks: Store,
    account: Annotated[Account, Depends(requires(Role.ENGINEER, action="dismiss_proposal"))],
) -> dict[str, Any]:
    try:
        decided = playbooks.dismiss(
            conn,
            proposal_id,
            decided_by=account.user,
            decided_role=account.role,
            note=dismissal.note,
        )
    except NothingToApply as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    except ValueError as error:
        # A note of nothing but spaces clears the schema's min_length and is not
        # a reason. 422 rather than the 500 an uncaught ValueError produces.
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error

    return {"proposal_id": decided.proposal_id, "status": decided.status.value}

"""The four contracts that describe work: Signal, Finding, Playbook, WorkOrder.

Every model is frozen. Layer 3 must be a pure function of its inputs
(design.md 7, invariant 10), and a pure function that receives mutable objects
is one accidental in-place edit away from producing different output for the
same input. Changes are made with model_copy(update=...), which makes each one
visible at the call site.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from pdm.contracts.enums import (
    AssigneeRole,
    BlockedReason,
    FindingKind,
    FindingStatus,
    PlaybookStatus,
    Role,
    Severity,
    StepKind,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.contracts.ids import (
    ComponentLabel,
    DocumentId,
    FindingRef,
    MachineId,
    MachineModel,
    PlaybookRef,
    PMTaskRef,
    RuleId,
    SkillId,
    SymptomCode,
    UserId,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


def _names_a_document(value: DocumentId) -> DocumentId:
    """Invariant 4's other half, which `Playbook`'s validator never looked at.

    `page` was enforced by `Field(ge=1)` and `source_doc` by nothing at all, so
    `source_doc=""` constructed without error and produced a step that cites a
    page of no document. Nothing in the system can reach that state today -
    provenance comes from the drafter, and a reviewer can neither add a step nor
    edit its source (ADR-064) - which is the difference between an invariant
    that holds and one that is enforced (ADR-084).
    """
    if not value.strip():
        raise ValueError(
            "a step citing a page of no document cannot be checked against the manual "
            "it came from, and after an accident nobody can say what was instructed "
            "(invariant 4, ADR-015)"
        )
    return value


# Where invariant 4 is enforced: on the field, so that it holds on every path
# into a playbook rather than only on approval. A draft step with no source is
# also wrong, and the drafter is the only thing that can still fix it - by the
# time a reviewer sees it, the provenance is not theirs to supply (ADR-084 §1).
AttributedDocument = Annotated[DocumentId, AfterValidator(_names_a_document)]


class Signal(BaseModel):
    """One measurement. Identical whether it came from the synthetic generator,
    a replay file or a live OPC UA connection (ADR-002).

    `timestamp` is *source* time: when the value was measured at the plant. It is
    not the clock the system makes decisions on, and the two will disagree once a
    live source is connected (ADR-028).
    """

    model_config = _FROZEN

    timestamp: datetime
    machine_id: MachineId
    metric_name: str
    value: float
    unit: str


class Finding(BaseModel):
    """Something worth a technician's attention, detected or predicted.

    The suppression key is (machine_id, rule_id): while an open or acknowledged
    Finding exists for that pair, a repeat firing raises occurrence_count and
    moves last_seen_at rather than creating a new record (ADR-023).
    """

    model_config = _FROZEN

    machine_id: MachineId
    # Declared by the rule, never inferred. A rule that cannot say which part it
    # watches uses UNKNOWN_COMPONENT and layer 2 serves a diagnostic playbook
    # instead of a repair one (ADR-009, ADR-016).
    component: ComponentLabel
    symptom_code: SymptomCode
    severity: Severity
    rule_id: RuleId
    detected_at: datetime

    # What made the system raise this: which value, how far past the threshold,
    # for how long. Without it the alert cannot be explained to a technician,
    # and an alert that cannot be explained gets ignored (principle 3).
    evidence: dict[str, object]

    kind: FindingKind = FindingKind.DETECTED
    eta: datetime | None = None
    eta_confidence: timedelta | None = None

    status: FindingStatus = FindingStatus.OPEN
    occurrence_count: int = Field(default=1, ge=1)
    last_seen_at: datetime | None = None
    superseded_by: FindingRef | None = None

    @model_validator(mode="after")
    def _predicted_findings_carry_an_eta(self) -> Finding:
        """A prediction without a horizon is just an opinion.

        ui.md 2.2 forbids dropping the confidence interval for tidiness: "in
        about 6 hours" reads as more trustworthy than "in about 6 hours, give or
        take 2", and the second one is the truth. Enforcing both fields here
        means the screen cannot be asked to render a prediction it has no
        interval for.
        """
        if self.kind is FindingKind.PREDICTED and (self.eta is None or self.eta_confidence is None):
            raise ValueError("a predicted Finding needs both eta and eta_confidence (ADR-020)")
        if self.kind is FindingKind.DETECTED and self.eta is not None:
            raise ValueError(
                "a detected Finding has already crossed the threshold; eta is meaningless"
            )
        return self


class IsolationPoint(BaseModel):
    """One energy-isolating device a step names: a breaker, a valve (ADR-135).

    A separate object confirmed one at a time and in order, never a phrase in
    the step's text (OSHA 1910.147, REQ-H-03).
    """

    model_config = _FROZEN

    point_id: str = Field(min_length=1)
    # Where it is, as the engineer wrote it: "เบรกเกอร์ CP-3 ที่ตู้ควบคุมหุ่นยนต์".
    label: str = Field(min_length=1)
    energy: str = Field(pattern="^(electrical|pneumatic|hydraulic|mechanical|thermal|gravity)$")


class PlaybookStep(BaseModel):
    """One instruction, carrying its own source.

    Provenance is per step rather than per playbook because authoring is tuned
    for recall (ADR-015), which raises the chance of a draft mixing steps from
    two documents. At document level a mixed playbook looks ordinary; at step
    level it reports itself, and the review screen can highlight the odd one.
    """

    model_config = _FROZEN

    text: str = Field(min_length=1)
    source_doc: AttributedDocument
    page: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)
    # The step in Thai, written or checked by the engineer who approved it
    # (ADR-095). `text` stays the manual's own words, because that is what the
    # page citation proves; this is what a technician reads first.
    text_th: str | None = Field(default=None, min_length=1)

    # What the step does to the machine's energy, marked by the approving
    # engineer and never inferred from the text (ADR-135, REQ-H-02, REQ-H-03).
    kind: StepKind = StepKind.NORMAL
    # ISO 7010 codes ("W012" electricity, "W017" hot surface) for the signs.
    hazards: tuple[Annotated[str, Field(pattern=r"^[WMPEF]\d{3}$")], ...] = ()
    # The devices an isolation, verify or restore step works through, in order.
    isolation_points: tuple[IsolationPoint, ...] = ()
    # A hazard that passes with time - a surface cooling, a bus discharging.
    wait_minutes: int | None = Field(default=None, ge=1, le=24 * 60)

    @model_validator(mode="after")
    def _energy_steps_name_their_points(self) -> PlaybookStep:
        energy = (StepKind.ISOLATION, StepKind.VERIFY, StepKind.RESTORE)
        if self.kind in energy and not self.isolation_points:
            raise ValueError(f"a {self.kind.value} step must name the points it works through")
        if self.kind not in energy and self.isolation_points:
            raise ValueError("only isolation, verify and restore steps name isolation points")
        return self


class Playbook(BaseModel):
    """How to repair one symptom on one machine model.

    One row per (symptom_code, machine_model). No version chain: approval
    overwrites and increments revision. History lives in
    WorkOrder.playbook_snapshot, which is where it is actually needed (ADR-018).
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel

    steps: tuple[PlaybookStep, ...]
    tools: tuple[str, ...] = ()
    # The approver's Thai for each tool, position for position; "" leaves that
    # tool as the manual wrote it, and an empty tuple means none were rendered
    # (ADR-130). The same figure check as the steps' Thai guards it.
    tools_th: tuple[str, ...] = ()
    parts: tuple[str, ...] = ()

    estimated_minutes: int = Field(gt=0)
    required_skill: SkillId
    # A two-person job consumes twice the shift capacity. Omitting this makes
    # load_ratio read low and the gate release more work than there are people
    # for (ADR-025).
    required_technicians: int = Field(default=1, ge=1)

    # The playbook's primary document. Individual steps may cite others, and
    # when they do, the review screen flags it.
    source_doc: AttributedDocument
    page: int = Field(ge=1)

    revision: int = Field(default=1, ge=1)
    status: PlaybookStatus = PlaybookStatus.DRAFT
    approved_by: UserId | None = None
    approved_at: datetime | None = None
    # The role held at the moment of approval, not the approver's current role
    # (ADR-024).
    approver_role: Role | None = None

    @model_validator(mode="after")
    def _approved_playbooks_are_fully_attributed(self) -> Playbook:
        """Invariant 4, enforced where it cannot be forgotten.

        An approved playbook is an instruction somebody will carry out on a
        machine. If a step cannot say where it came from, nobody can check it
        after an accident, and the traceability the whole design is built on
        (principle 2) is gone for that job.
        """
        if self.status is not PlaybookStatus.APPROVED:
            return self
        if not self.steps:
            raise ValueError("an approved playbook with no steps has nothing to approve")
        if self.approved_by is None or self.approved_at is None or self.approver_role is None:
            raise ValueError("an approved playbook must record who approved it, when, and as what")
        if self.approver_role is not Role.ENGINEER:
            raise ValueError(
                f"only an engineer may approve a playbook, not {self.approver_role} (ADR-024)"
            )
        return self


class Assignee(BaseModel):
    model_config = _FROZEN

    user: UserId
    role: AssigneeRole = AssigneeRole.PRIMARY


class WorkSegment(BaseModel):
    """One continuous stretch of one person working on one order."""

    model_config = _FROZEN

    user: UserId
    started_at: datetime
    ended_at: datetime | None = None

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> WorkSegment:
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("a work segment cannot end before it starts")
        return self

    @property
    def duration(self) -> timedelta:
        """Zero while the segment is still open."""
        if self.ended_at is None:
            return timedelta(0)
        return self.ended_at - self.started_at


class WorkOrder(BaseModel):
    """A job for a technician, from any of the three sources.

    The scheduler-facing fields (machine_id, severity, finding_kind, eta) are
    copied onto the order when it is created and are deliberately a snapshot.
    Layer 3 reads them here and never reads a Finding, which is what lets it
    keep the rule that it must not import layer 1 (ADR-030). finding_ref remains
    for tracing back - the technician screen reads "seen N times" through it -
    but the scheduler never follows it.
    """

    model_config = _FROZEN

    origin: WorkOrderOrigin
    machine_id: MachineId
    severity: Severity

    finding_ref: FindingRef | None = None
    pm_task_ref: PMTaskRef | None = None

    playbook_ref: PlaybookRef | None = None
    # Frozen copy of the steps, their provenance and the approval, taken when
    # the order was issued. Never edited for the life of the order: it is the
    # only evidence of what the system actually instructed (invariant 2).
    playbook_snapshot: tuple[PlaybookStep, ...] = ()
    snapshot_approved_by: UserId | None = None
    snapshot_approved_at: datetime | None = None
    # Set when the playbook this was built from is awaiting review - a manual
    # replaced, a technician's objection filed. ADR-018 serves such a playbook
    # anyway, because a technician with an out-of-date procedure is better off
    # than one with none; that is only true while they can tell which they have,
    # and the ticket is where somebody is standing at a machine (ADR-041).
    playbook_warning: str | None = None

    finding_kind: FindingKind | None = None
    eta: datetime | None = None
    eta_confidence: timedelta | None = None

    # ── what the scheduler computes with (ADR-041) ──────────────────────
    # Copied from the playbook when the order is created, for the reason
    # machine_id and severity are: load_ratio is the sum of
    # estimated_minutes x required_technicians over the shift's capacity
    # (design.md 13.2), and dispatch() may not read a table to find them
    # (invariant 10).
    #
    # A snapshot, deliberately. An order priced at forty-five minutes stays
    # priced at forty-five when the playbook is re-approved at sixty, because
    # the shift was planned on the first number.
    estimated_minutes: int = Field(gt=0)
    # None means "any technician". There is no honest default: guessing
    # robot_mechanical for an electrical fault sends the wrong person, and a
    # guess is worse than an absence because the absence is visible (ADR-041).
    required_skill: SkillId | None = None
    required_technicians: int = Field(default=1, ge=1)
    # True when the duration came from policy.yaml rather than from a manual.
    # Unlabelled, a coarse guess is indistinguishable from a figure somebody
    # measured, and nobody can then say how much of the schedule rests on
    # guesses (design.md 3.2).
    estimate_is_fallback: bool = False

    # Why this job exists, written at creation and never changed. Distinct from
    # priority_reason, which is why it is ranked where it is and belongs to
    # layer 3: a technician looking at a job asks the first question and a
    # supervisor looking at the queue asks the second, and one field answers
    # whichever was asked last (ADR-005, ADR-041).
    reason: str = Field(min_length=1)

    priority_score: float = 0.0
    # Never empty: a system that cannot say why this job comes first gets
    # overruled and then abandoned (ADR-005).
    priority_reason: str = ""

    status: WorkOrderStatus = WorkOrderStatus.QUEUED
    assignees: tuple[Assignee, ...] = ()
    work_segments: tuple[WorkSegment, ...] = ()
    handover_note: str | None = None

    blocked_minutes: int = Field(default=0, ge=0)
    blocked_reason: tuple[BlockedReason, ...] = ()
    outcome: WorkOutcome | None = None
    technician_feedback: str | None = None
    # Who reported it, on a manual order (ADR-077, ADR-122). The reason sentence
    # names them too; this is what lets the reporter find it again.
    reported_by: UserId | None = None

    @property
    def actual_minutes(self) -> int:
        """Sum of the work segments, not close time minus start time (ADR-025).

        A property rather than a stored field, so the two can never disagree. An
        order started at 15:00 and finished at 09:00 the next day would otherwise
        record eighteen hours and destroy the estimate for that symptom from a
        single row.
        """
        total = sum((segment.duration for segment in self.work_segments), timedelta(0))
        return int(total.total_seconds() // 60)

    @property
    def repair_minutes(self) -> int:
        """What Loop 1 may learn from: worked time with waiting removed.

        Waiting for a part is not repair time. Feeding it back would inflate the
        estimate every cycle until load_ratio reads the shift as permanently
        full (feedback_loops.md 3).
        """
        return max(0, self.actual_minutes - self.blocked_minutes)

    @model_validator(mode="after")
    def _a_playbook_backed_order_is_not_a_fallback(self) -> WorkOrder:
        """The two cannot both be true, and the confusion would be invisible.

        `estimate_is_fallback` exists so that a coarse number can be told from a
        manual's figure. An order carrying a playbook *and* claiming a fallback
        estimate says both at once, and whichever a reader believes, the other
        was written by something that was not paying attention.
        """
        if self.estimate_is_fallback and self.playbook_ref is not None:
            raise ValueError(
                "an order bound to a playbook takes its estimate from that playbook; "
                "estimate_is_fallback describes an order that has none (ADR-041)"
            )
        return self

    @model_validator(mode="after")
    def _origin_matches_its_reference(self) -> WorkOrder:
        if self.origin is WorkOrderOrigin.CONDITION and self.finding_ref is None:
            raise ValueError("a condition work order must reference the Finding it came from")
        if self.origin is WorkOrderOrigin.SCHEDULED and self.pm_task_ref is None:
            raise ValueError("a scheduled work order must reference its PM task")
        return self

    @model_validator(mode="after")
    def _handover_is_explained(self) -> WorkOrder:
        """ADR-025: the note is a small burden that saves the next person a lot.

        Without it the afternoon technician finds an open order and no idea how
        far the morning got, so they start again from step one.
        """
        if self.status is WorkOrderStatus.HANDED_OVER and not self.handover_note:
            raise ValueError("handing over a job requires a note saying how far it got (ADR-025)")
        return self

    @model_validator(mode="after")
    def _closed_orders_say_how_they_ended(self) -> WorkOrder:
        if self.status is WorkOrderStatus.CLOSED and self.outcome is None:
            raise ValueError("a closed work order must record an outcome")
        return self

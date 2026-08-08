"""The four contracts that describe work: Signal, Finding, Playbook, WorkOrder.

Every model is frozen. Layer 3 must be a pure function of its inputs
(design.md 7, invariant 10), and a pure function that receives mutable objects
is one accidental in-place edit away from producing different output for the
same input. Changes are made with model_copy(update=...), which makes each one
visible at the call site.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts.enums import (
    AssigneeRole,
    BlockedReason,
    FindingKind,
    FindingStatus,
    PlaybookStatus,
    Role,
    Severity,
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


class PlaybookStep(BaseModel):
    """One instruction, carrying its own source.

    Provenance is per step rather than per playbook because authoring is tuned
    for recall (ADR-015), which raises the chance of a draft mixing steps from
    two documents. At document level a mixed playbook looks ordinary; at step
    level it reports itself, and the review screen can highlight the odd one.
    """

    model_config = _FROZEN

    text: str = Field(min_length=1)
    source_doc: DocumentId
    page: int = Field(ge=1)
    confidence: float = Field(ge=0.0, le=1.0)


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
    parts: tuple[str, ...] = ()

    estimated_minutes: int = Field(gt=0)
    required_skill: SkillId
    # A two-person job consumes twice the shift capacity. Omitting this makes
    # load_ratio read low and the gate release more work than there are people
    # for (ADR-025).
    required_technicians: int = Field(default=1, ge=1)

    # The playbook's primary document. Individual steps may cite others, and
    # when they do, the review screen flags it.
    source_doc: DocumentId
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

    finding_kind: FindingKind | None = None
    eta: datetime | None = None
    eta_confidence: timedelta | None = None

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

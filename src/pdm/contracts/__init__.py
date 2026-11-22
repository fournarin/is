"""The eight data contracts every other module connects through.

Four describe work (Signal, Finding, Playbook, WorkOrder) and four describe
resources and places (Line/Station, Skill labels, Technician/Shift, PMTask).
The second group exists because layer 3 - the core of this project - needs all
of it and none of it had a contract before (ADR-027).

This package is a leaf: it must never import another pdm module. Without that
rule the dependency graph becomes a mesh and none of the other import rules can
be expressed (ADR-030). .importlinter enforces it.

Every model is frozen. Layer 3 must be a pure function of its inputs
(invariant 10), and purity does not survive callers that can edit what they were
given.
"""

from pdm.contracts.enums import (
    AssigneeRole,
    BlockedReason,
    FindingKind,
    FindingStatus,
    LockState,
    PlaybookStatus,
    Role,
    Severity,
    StepKind,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.contracts.ids import (
    UNKNOWN_COMPONENT,
    ComponentLabel,
    DocumentId,
    FindingRef,
    LineId,
    MachineId,
    MachineModel,
    PlaybookRef,
    PMTaskRef,
    RuleId,
    ShiftId,
    SkillId,
    StationId,
    SymptomCode,
    UserId,
    WorkOrderRef,
)
from pdm.contracts.resources import (
    PM_SYMPTOM_PREFIX,
    Line,
    PMTask,
    ShiftAssignment,
    ShiftDefinition,
    ShiftWindow,
    Station,
    Technician,
    shift_at,
    shift_capacity_minutes,
)
from pdm.contracts.work import (
    Assignee,
    Finding,
    IsolationPoint,
    Playbook,
    PlaybookStep,
    Signal,
    WorkOrder,
    WorkSegment,
)

__all__ = [
    "PM_SYMPTOM_PREFIX",
    "UNKNOWN_COMPONENT",
    "Assignee",
    "AssigneeRole",
    "BlockedReason",
    "ComponentLabel",
    "DocumentId",
    "Finding",
    "FindingKind",
    "FindingRef",
    "FindingStatus",
    "IsolationPoint",
    "Line",
    "LineId",
    "LockState",
    "MachineId",
    "MachineModel",
    "PMTask",
    "PMTaskRef",
    "Playbook",
    "PlaybookRef",
    "PlaybookStatus",
    "PlaybookStep",
    "Role",
    "RuleId",
    "Severity",
    "ShiftAssignment",
    "ShiftDefinition",
    "ShiftId",
    "ShiftWindow",
    "Signal",
    "SkillId",
    "Station",
    "StationId",
    "StepKind",
    "SymptomCode",
    "Technician",
    "UserId",
    "WorkOrder",
    "WorkOrderOrigin",
    "WorkOrderRef",
    "WorkOrderStatus",
    "WorkOutcome",
    "WorkSegment",
    "shift_at",
    "shift_capacity_minutes",
]

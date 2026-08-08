"""Closed value sets shared by the contracts.

Every member here traces to a document. Where a set was implied rather than
enumerated, the docstring says so, because an invented value is indistinguishable
from a decided one once it is in the code.
"""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """How urgent the work is.

    Ordered, because the load gate admits "high severity only" above 0.8
    (ADR-011) and that phrase needs a threshold to compare against. The scale
    itself is not fixed by any ADR; four levels is the smallest set that still
    lets the gate distinguish "urgent" from "everything else" without collapsing
    into a boolean.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.LOW: 0,
    Severity.MEDIUM: 1,
    Severity.HIGH: 2,
    Severity.CRITICAL: 3,
}


class FindingKind(StrEnum):
    """Whether a threshold has been crossed or is expected to be (ADR-020).

    The distinction reaches the technician's screen: "over threshold for 20
    minutes" and "expected to reach threshold in about 6 hours" lead to
    different decisions, so they must not be displayed alike (ui.md 2.2).
    """

    DETECTED = "detected"
    PREDICTED = "predicted"


class FindingStatus(StrEnum):
    """Finding lifecycle (ADR-023).

    Without a lifecycle a single overheating motor raises a Finding on every
    reading, becomes a hundred work orders within an hour, and the load gate
    then holds back everything. The system destroys itself in its first hour on
    real data.
    """

    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    # A predicted Finding whose ETA plus grace passed without the event.
    EXPIRED = "expired"
    # A predicted Finding replaced by a detected one for the same machine and
    # component. Also the moment Loop 3 learns how wrong the ETA was.
    SUPERSEDED = "superseded"


class PlaybookStatus(StrEnum):
    """draft / approved / needs_review (ADR-018).

    The line that matters is "has anyone taken responsibility for this content":
    needs_review is still served with a warning banner, draft is never served,
    not even when there is nothing else to give the technician (ADR-013).
    """

    DRAFT = "draft"
    APPROVED = "approved"
    NEEDS_REVIEW = "needs_review"


class WorkOrderOrigin(StrEnum):
    """Where the work came from (ADR-010).

    Without scheduled and manual work there is nothing to release when the shift
    is quiet, so the behaviour the advisor asked for would be structurally
    impossible rather than merely unimplemented.
    """

    CONDITION = "condition"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class WorkOrderStatus(StrEnum):
    """Work order lifecycle.

    Derived rather than quoted: no ADR enumerates this set. HANDED_OVER is
    required by ADR-025, and the rest follow the technician screens in ui.md
    (a queue, a start button, a close button) plus the load gate holding orders
    back (ADR-011). Worth confirming before layer 3 is built on it.
    """

    # Created and waiting. Includes orders the load gate is holding back.
    QUEUED = "queued"
    # Assigned to technicians but not started.
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    # Shift ended before completion. Requires handover_note (ADR-025).
    HANDED_OVER = "handed_over"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class WorkOutcome(StrEnum):
    """How the job ended (ui.md 2.5).

    NO_PROBLEM_FOUND is not a fourth option for completeness. It is the only
    false-alarm signal the system will ever receive, and Loop 2 - tuning rule
    thresholds - does not exist without it (feedback_loops.md 4).
    """

    FIXED = "fixed"
    TEMPORARY_FIX = "temporary_fix"
    NOT_FIXED = "not_fixed"
    NO_PROBLEM_FOUND = "no_problem_found"


class BlockedReason(StrEnum):
    """Why repair time was not repair time (ui.md 2.5).

    Subtracted before actual duration feeds back into estimates. Without it,
    waiting for a part inflates the estimate for that symptom, load_ratio then
    reads the shift as permanently full, and the gate holds back work it should
    release (feedback_loops.md 3).
    """

    WAITING_PARTS = "waiting_parts"
    WAITING_LINE_STOP = "waiting_line_stop"
    WAITING_HELP = "waiting_help"


class AssigneeRole(StrEnum):
    """Skills are matched against the primary; helpers still consume capacity.

    A two-person job of 60 minutes costs the shift 120 person-minutes. Counting
    it as 60 makes load_ratio read low and the gate release more work than there
    are people for (ADR-025).
    """

    PRIMARY = "primary"
    HELPER = "helper"


class Role(StrEnum):
    """Who may do what (ADR-024).

    ADR-024 says "five roles" but its table names four. Rather than invent a
    fifth, only the four with defined authority exist here; if a fifth was
    intended, it needs a new ADR before it appears in code.

    Recorded on Playbook.approver_role as the role held *at the moment of
    approval*, not the person's current role: people move, but the evidence that
    the approval was authorised must not change with them.
    """

    TECHNICIAN = "technician"
    ENGINEER = "engineer"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"

"""WorkOrder lifecycle: creation, playbook binding, completion, shift handover.

Three sources of work and one shape of ticket (ADR-010). Everything the scheduler
computes with is copied onto the order here - machine, severity, ETA, duration,
skill - so that layer 3 can rank it without reading a Finding or a playbook, and
so `dispatch()` stays a pure function of its inputs (ADR-030, ADR-041,
invariant 10).
"""

from pdm.work.domain import NoEstimateAvailable, playbook_ref_for, reason_for
from pdm.work.service import Issued, WorkOrders

__all__ = [
    "Issued",
    "NoEstimateAvailable",
    "WorkOrders",
    "playbook_ref_for",
    "reason_for",
]

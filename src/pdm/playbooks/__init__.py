"""Playbook store and the runtime serving order (layer 2).

One row per (symptom_code, machine_model); no version chain. History lives in
WorkOrder.playbook_snapshot instead (ADR-018). Draft playbooks are never served
at runtime, not even when there is nothing else to give the technician - which
this layer achieves by keeping them in a different table altogether, so there is
no draft row for a serving query to reach (ADR-038).
"""

from pdm.playbooks.domain import (
    Proposal,
    ProposalOrigin,
    ProposalStatus,
    Served,
    StepEdit,
)
from pdm.playbooks.service import NotADraft, NotAnEngineer, PlaybookStore

__all__ = [
    "NotADraft",
    "NotAnEngineer",
    "PlaybookStore",
    "Proposal",
    "ProposalOrigin",
    "ProposalStatus",
    "Served",
    "StepEdit",
]

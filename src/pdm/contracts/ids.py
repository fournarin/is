"""Identifier aliases used across the contracts.

These are plain strings at runtime. They exist so that a signature reads
`station_for(machine: MachineId) -> StationId` instead of `str -> str`, which is
the difference between a reviewer spotting a swapped argument and not.

Several of them are *labels declared in config*, not entities in the database
(ADR-016 for ComponentLabel, ADR-027 for SkillId). Nothing here validates that a
label exists; that check belongs to the config loader, which refuses to boot on
an unknown one (invariants 7 and 13). Putting it here instead would mean the
contracts package needing to read config, and it must stay a leaf (ADR-030).
"""

from __future__ import annotations

from typing import NewType

MachineId = NewType("MachineId", str)
MachineModel = NewType("MachineModel", str)

# Where a machine sits on the line. Resolved from config, never stored on a
# Signal or a Finding, because the mapping changes when the line is rearranged
# and old records must keep meaning what they meant (ADR-027).
StationId = NewType("StationId", str)
LineId = NewType("LineId", str)

ShiftId = NewType("ShiftId", str)

# A label from the list declared per machine model in config. Rules name the
# component they watch; nothing infers it (ADR-009, ADR-016).
ComponentLabel = NewType("ComponentLabel", str)

# Keys a playbook is looked up by, together with MachineModel.
SymptomCode = NewType("SymptomCode", str)

RuleId = NewType("RuleId", str)

# One label from the single list that both Playbook.required_skill and
# Technician.skills draw from. Two separate vocabularies would fail to match
# silently, which is the failure ADR-027 exists to prevent.
SkillId = NewType("SkillId", str)

UserId = NewType("UserId", str)

# sha256 of the file contents, which is also its name on disk (ADR-019).
DocumentId = NewType("DocumentId", str)

FindingRef = NewType("FindingRef", str)
PlaybookRef = NewType("PlaybookRef", str)
PMTaskRef = NewType("PMTaskRef", str)
WorkOrderRef = NewType("WorkOrderRef", str)

# The component label used when a rule cannot say which part it is watching.
# Layer 2 then serves a diagnostic playbook rather than a repair one (ADR-009).
UNKNOWN_COMPONENT = ComponentLabel("unknown")

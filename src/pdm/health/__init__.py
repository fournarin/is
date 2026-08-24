"""Machine health: a standing per-machine reading, and never a source of work.

Health answers "which machines deserve attention, and why" for a person deciding
what to look at. The priority score answers "which job comes first" for a round
deciding who goes where. They are kept apart on purpose: health is partly
computed from the same facts the score is, so folding it in would double-count
them, and a supervisor and a scheduler are not asking the same question
(ADR-072 section 4).

Two contributions, reported as two and never blended into one number: **what this
machine has done before**, from closed work orders and PM tasks, and **what it is
saying now**, from open Findings. A single figure would tell a supervisor nothing
they can act on and would hide which of the two moved (ADR-072 section 2).

Nothing here creates work. ADR-010's three origins stand, and `.importlinter`
holds the rule rather than this docstring: `pdm.health` cannot reach `pdm.work`,
`pdm.dispatch` or `pdm.triggers`, and `pdm.dispatch` cannot reach here
(ADR-076 section 7).
"""

from pdm.health.domain import (
    AGE_AGAINST_ITS_CLASS_IS_ABSENT,
    ClosedRepair,
    CurrentContribution,
    HistoryContribution,
    MachineHealth,
    assess,
    by_history,
    by_now,
)

__all__ = [
    "AGE_AGAINST_ITS_CLASS_IS_ABSENT",
    "ClosedRepair",
    "CurrentContribution",
    "HistoryContribution",
    "MachineHealth",
    "assess",
    "by_history",
    "by_now",
]

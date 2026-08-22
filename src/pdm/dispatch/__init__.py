"""Layer 3: load gate, scoring, assignment and explanation.

Must stay a pure function. No database queries inside the algorithm. This is a
precondition for both the simulator and feedback Loop 6 (design.md 7, ADR-022).
"""

from pdm.dispatch.domain import (
    Band,
    Placement,
    Queued,
    Round,
    Terms,
    Withheld,
    capacity_left,
    committed,
    dispatch,
    downtime_or_unknown,
    downtime_units,
    load_ratio,
)
from pdm.dispatch.explain import Answer, Explainer, Reason
from pdm.dispatch.solver import schedule

__all__ = [
    "Answer",
    "Band",
    "Explainer",
    "Placement",
    "Queued",
    "Reason",
    "Round",
    "Terms",
    "Withheld",
    "capacity_left",
    "committed",
    "dispatch",
    "downtime_or_unknown",
    "downtime_units",
    "load_ratio",
    "schedule",
]

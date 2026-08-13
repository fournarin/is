"""Layer 1: rules and trend extrapolation over signals (ADR-004, ADR-020).

Signals in, `Finding` out, with the lifecycle ADR-023 requires: one live record
per (machine, rule), a cooldown after resolution, suppression that follows the
rule rather than the machine, and a prediction superseded by the detection it
foresaw.

The evaluation itself is a pure function and everything it needs is passed to it
(ADR-042), because the case that has to be tested exhaustively is a safety rule
firing while the machine it watches is under repair.
"""

from pdm.triggers.domain import Debounce, Decision, Outcome, breaches, evaluate
from pdm.triggers.service import Observation, Raised, Triggers

__all__ = [
    "Debounce",
    "Decision",
    "Observation",
    "Outcome",
    "Raised",
    "Triggers",
    "breaches",
    "evaluate",
]

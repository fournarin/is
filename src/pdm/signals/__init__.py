"""Three SignalSource implementations: synthetic, replay and live (ADR-002).

The rest of the system talks only to the Signal contract and never learns
which source is behind it.

Only the synthetic one exists so far, and it is the one everything else is
tested against. It is also the only source with ground truth, which is what
makes prediction measurable before any plant data arrives (ADR-020, ADR-032).
"""

from pdm.signals.domain import (
    LINE_A_TWELVE_HOURS,
    Channel,
    Exponential,
    GroundTruth,
    LinearDrift,
    Scenario,
    SignalSource,
    Spike,
    Steady,
    Step,
    SyntheticSource,
)

__all__ = [
    "LINE_A_TWELVE_HOURS",
    "Channel",
    "Exponential",
    "GroundTruth",
    "LinearDrift",
    "Scenario",
    "SignalSource",
    "Spike",
    "Steady",
    "Step",
    "SyntheticSource",
]

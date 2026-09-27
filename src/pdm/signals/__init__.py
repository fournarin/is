"""Three SignalSource implementations: synthetic, replay and live (ADR-002).

The rest of the system talks only to the Signal contract and never learns
which source is behind it.

Two exist. The synthetic one is what everything else is tested against, and
the only source with ground truth, which is what makes prediction measurable
before any plant data arrives (ADR-020, ADR-032). The replay one reads a CSV
export of plant readings, which is the shortest path from the plant to this
system (ADR-091). The live one, OPC UA, is not built.
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
from pdm.signals.feed import Feed
from pdm.signals.replay import ReplayFileError, ReplaySource

__all__ = [
    "LINE_A_TWELVE_HOURS",
    "Channel",
    "Exponential",
    "Feed",
    "GroundTruth",
    "LinearDrift",
    "ReplayFileError",
    "ReplaySource",
    "Scenario",
    "SignalSource",
    "Spike",
    "Steady",
    "Step",
    "SyntheticSource",
]

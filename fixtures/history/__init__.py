"""A synthetic maintenance history that carries its own answer key (ADR-072 §5).

The same pattern as `fixtures/corpus` (ADR-033) and `SyntheticSource` (ADR-032):
the generator knows which machines it degraded and between which moments, so
"did the health ranking put the machines that were actually failing near the
top" is a question with a number for an answer, before any plant data arrives.

What it writes is closed `WorkOrder` rows and `PMTask` rows - the shape this
system already produces when a technician finishes a job - rather than a new
`MachineHistory` contract. ADR-076 section 1 is why: the CMMS export that will
eventually feed this has not been seen, and a contract shaped to a guess would
have the authority of one of the eight.

This package lives outside `src/pdm` on purpose and nothing under `src/` may
import it. A synthetic failure record sitting in the same store as real ones is
a row somebody would read and believe.

**Every parameter in the plan below is invented.** Nothing here is a measurement
of any plant, and `docs/results/health.md` says so where the numbers are read.
"""

from fixtures.history.generator import (
    LINE_A_ONE_YEAR,
    DegradationEpisode,
    HistoryPlan,
    MachinePlan,
    SyntheticHistory,
)

__all__ = [
    "LINE_A_ONE_YEAR",
    "DegradationEpisode",
    "HistoryPlan",
    "MachinePlan",
    "SyntheticHistory",
]

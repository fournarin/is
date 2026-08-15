"""Discrete-event simulator of the production line and the technician roster.

Models line topology and buffers, not just a work queue (ADR-021).
May import only contracts, dispatch/domain, work/domain and platform/clock.

Phase 2's deliverable is a table comparing dispatch policies on the same
scenarios, and this is the instrument that produces it. Two properties make that
table worth printing: a run is reproducible from (scenario, seed), and a stopped
machine is costed at the station it stands at, so a bottleneck with no buffer and
a station with twenty units of cover are not the same job.

The policies themselves live outside this package and arrive through the `Policy`
protocol. A simulator that imported the scheduler it was measuring could not
measure anything else, and the comparison would be circular.
"""

from pdm.sim.domain import (
    Event,
    EventKind,
    Outage,
    Placement,
    Policy,
    ProductionLine,
    RoundState,
    SimRun,
    Ticket,
    TicketRecord,
)
from pdm.sim.engine import run
from pdm.sim.scenario import ArrivalWindow, Failure, SimScenario, failures_for, offered_load
from pdm.sim.scenarios import LINE_A_ONE_SHIFT

__all__ = [
    "LINE_A_ONE_SHIFT",
    "ArrivalWindow",
    "Event",
    "EventKind",
    "Failure",
    "Outage",
    "Placement",
    "Policy",
    "ProductionLine",
    "RoundState",
    "SimRun",
    "SimScenario",
    "Ticket",
    "TicketRecord",
    "failures_for",
    "offered_load",
    "run",
]

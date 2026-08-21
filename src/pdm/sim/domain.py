"""The line, the seam and the log: everything the engine computes with.

Pure, and pure in the strict sense the import rules enforce: no database, no
filesystem, no clock. Slice 7.3 runs hundreds of scenarios inside one CI job, and
anything here that touched the world outside the process would make that run slow
where it is now fast and flaky where it is now reproducible.

Three things live here.

**The line.** `ProductionLine` is ADR-021 in code: stations in sequence, the
buffer each one carries, and what a stopped machine costs given both. The
alternative - a constant per line - is what the record exists to refuse, because
it makes a bottleneck with no buffer and a station with twenty units of cover
look like the same job.

**The seam.** `Policy` is the protocol slice 7.2's baselines and an adapter over
`dispatch()` both plug into. The engine takes one as an argument and imports
none: a simulator that reached into `pdm.dispatch` could not measure a policy
that lives anywhere else, and the comparison would be circular.

What a policy is shown is deliberately less than the engine knows. `Ticket`
carries the work order and when it was raised; the true repair time stays in the
engine. A policy able to read it would be able to schedule against the future,
and its advantage in the report would be an artefact of the instrument.

**The log.** Frozen events in one ordered tuple, so two runs can be compared with
`==`. Reproducibility is the precondition of every number slice 7.3 produces
(ADR-032 argues the same for signals), and the cheapest way to hold it is to make
the whole outcome one comparable value.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    Line,
    LineId,
    MachineId,
    Severity,
    ShiftId,
    Station,
    StationId,
    Technician,
    UserId,
    WorkOrder,
)
from pdm.platform.config import Config

_FROZEN = ConfigDict(frozen=True, extra="forbid")


# ── the line ───────────────────────────────────────────────────────────────


class ProductionLine(BaseModel):
    """Stations in sequence, and what stopping one of them costs (ADR-021).

    Built from `plant.yaml` rather than from a description of its own, so a
    layout change moves the simulator and the scheduler together. When the real
    buffer map arrives it changes values in that file and nothing here.
    """

    model_config = _FROZEN

    line: Line
    # Ascending seq. A line is a sequence; reading stations in file order would
    # be right by accident until somebody appends a station.
    stations: tuple[Station, ...]

    @classmethod
    def from_config(cls, config: Config, line_id: LineId) -> ProductionLine:
        line = config.lines[line_id]
        stations = tuple(
            sorted(
                (station for station in config.stations.values() if station.line_id == line_id),
                key=lambda station: station.seq,
            )
        )
        return cls(line=line, stations=stations)

    @property
    def units_per_minute(self) -> float:
        """Production rate, from the takt. The unit conversion is the easiest
        thing here to get wrong by a factor of sixty."""
        return 60.0 / self.line.takt_seconds

    @property
    def machine_ids(self) -> tuple[MachineId, ...]:
        return tuple(machine_id for station in self.stations for machine_id in station.machine_ids)

    def station_of(self, machine_id: MachineId) -> Station:
        """Raises rather than returning None.

        A machine that resolves to nothing would be costed at zero, so a whole
        station's downtime would read as free with nothing reporting it. Config
        validation makes this lookup unable to miss for any machine a rule can
        fire on (invariant 13); anything else is a scenario naming a machine
        that does not exist.
        """
        for station in self.stations:
            if machine_id in station.machine_ids:
                return station
        raise KeyError(f"no station on {self.line.line_id} holds machine {machine_id}")

    def units_lost(self, station: Station, down_minutes: float) -> float:
        """ADR-021: rate x max(0, downtime - buffer) x bottleneck multiplier.

        `down_minutes` rather than two datetimes, so an outage still open when
        the run ends can be costed against the part of it that happened.
        """
        if down_minutes < 0:
            raise ValueError(f"an outage cannot last a negative {down_minutes} minutes")
        uncovered = max(0.0, down_minutes - station.buffer_minutes(self.line))
        return self.units_per_minute * uncovered * station.bottleneck_multiplier


# ── what a policy is shown, and what it may answer ─────────────────────────


class Ticket(BaseModel):
    """One job, as the policy sees it.

    The work order carries everything layer 3 schedules with - machine,
    severity, estimated minutes, crew size - because ADR-041 put it there
    precisely so a scheduler would not have to look anything up. What is absent
    is the true repair time: the engine knows it and the policy must not.
    """

    model_config = _FROZEN

    ref: str = Field(min_length=1)
    order: WorkOrder
    created_at: datetime


class Placement(BaseModel):
    """One decision: this ticket, these people, starting now.

    `priority_reason` is carried through to the event log unchanged. It is not
    used by the engine; it is here so a policy that can explain itself (ADR-005)
    does not have to throw the explanation away to be measured.
    """

    model_config = _FROZEN

    ref: str = Field(min_length=1)
    users: tuple[UserId, ...] = ()
    priority_score: float = 0.0
    priority_reason: str = ""


class RoundState(BaseModel):
    """The world at one dispatch round.

    Shaped so that an adapter over `dispatch()` needs no translation of its own:
    the queue, the roster, who is unavailable, the shift's capacity and what each
    technician has left are all here, which is exactly that function's argument
    list (ADR-045, invariant 10).

    `in_progress` is offered and must not be re-ranked. Work already under way
    consumes capacity, and a technician walking to a machine must not watch the
    queue reshuffle behind them (design.md 6.2).
    """

    model_config = _FROZEN

    now: datetime
    shift_id: ShiftId
    on_date: date

    pending: tuple[Ticket, ...] = ()
    in_progress: tuple[Ticket, ...] = ()

    technicians: tuple[Technician, ...] = ()
    busy: frozenset[UserId] = frozenset()

    capacity_minutes: int = Field(default=0, ge=0)
    # Per technician, what is left of their availability. Person-minutes, the
    # same unit as the other side of load_ratio (ADR-027, design.md 13.2).
    remaining_minutes: tuple[tuple[UserId, int], ...] = ()


@runtime_checkable
class Policy(Protocol):
    """What the engine asks at every round.

    Deliberately smaller than `dispatch()`. A baseline that orders by arrival
    time has no weights, no gate and no config, and a protocol shaped around the
    thing being compared *to* would have made the two baselines in slice 7.2
    implementations of an interface built for their competitor.
    """

    name: str

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        """Placements to start now. Returning () is a legitimate answer: it is
        what a load gate holding work back looks like from here."""
        ...


# ── the log ────────────────────────────────────────────────────────────────


class EventKind(StrEnum):
    """What happened. Five kinds, because five are enough to replay a run."""

    # A machine stopped and a ticket was raised for it, in the same instant.
    FAILED = "failed"
    # A round ran. Logged only when there was work to decide about, so a quiet
    # eight-hour shift does not produce ninety-six events saying nothing.
    ROUND = "round"
    STARTED = "started"
    REPAIRED = "repaired"
    ENDED = "ended"


class Event(BaseModel):
    """One line of the log.

    `seq` breaks ties between events sharing a timestamp. Without it two runs
    could hold the same events in a different order and compare unequal, and the
    reproducibility test would be measuring dictionary iteration.
    """

    model_config = _FROZEN

    at: datetime
    seq: int = Field(ge=0)
    kind: EventKind
    machine_id: MachineId | None = None
    station_id: StationId | None = None
    ticket_ref: str | None = None
    users: tuple[UserId, ...] = ()
    minutes: float | None = None
    note: str = ""


class Outage(BaseModel):
    """One period with a machine stopped, and what it cost.

    A machine is down while any unfinished ticket names it, so a second failure
    during a repair extends this rather than opening a second one. Two overlapping
    outages would double-count the lost units, and the policy that let them
    overlap would be rewarded for it.

    `ended_at` is None for an outage still open when the run stopped. Those are
    costed to the end of the window: a policy that never reaches a machine must
    not come out looking free.
    """

    model_config = _FROZEN

    machine_id: MachineId
    station_id: StationId
    began_at: datetime
    ended_at: datetime | None
    down_minutes: float = Field(ge=0)
    units_lost: float = Field(ge=0)


class TicketRecord(BaseModel):
    """What became of one ticket. The row slice 7.3 aggregates.

    `estimated_minutes` and `repair_minutes` are both here on purpose. The first
    is what the scheduler planned with, the second is what the job actually took;
    keeping them apart is the same distinction ADR-006 draws between estimated
    and actual, and the gap between them is what makes a comparison of policies
    worth reading.
    """

    model_config = _FROZEN

    ref: str
    machine_id: MachineId
    station_id: StationId
    severity: Severity
    estimated_minutes: int
    estimate_is_fallback: bool
    required_skill: str | None
    repair_minutes: int
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    users: tuple[UserId, ...] = ()

    @property
    def response_minutes(self) -> float | None:
        """From the machine stopping to somebody starting on it. None while
        nobody has."""
        if self.started_at is None:
            return None
        return (self.started_at - self.created_at).total_seconds() / 60.0


class SimRun(BaseModel):
    """One scenario, one policy, one seed, and everything that happened.

    Comparable with `==`: two runs of the same inputs are the same value. That is
    what the reproducibility test asserts, and it is cheaper to hold than a
    convention that every field happens to be deterministic.
    """

    model_config = _FROZEN

    scenario: str
    policy: str
    seed: int
    started_at: datetime
    ended_at: datetime

    events: tuple[Event, ...] = ()
    outages: tuple[Outage, ...] = ()
    tickets: tuple[TicketRecord, ...] = ()

    @property
    def units_lost(self) -> float:
        """The number the comparison is about. Production, not minutes: an hour
        at the bottleneck and an hour behind a full buffer are not the same
        loss, which is the whole of ADR-021."""
        return sum(outage.units_lost for outage in self.outages)

    @property
    def downtime_minutes(self) -> float:
        return sum(outage.down_minutes for outage in self.outages)

    @property
    def tickets_raised(self) -> int:
        return len(self.tickets)

    @property
    def tickets_finished(self) -> int:
        return sum(1 for ticket in self.tickets if ticket.finished_at is not None)

    @property
    def tickets_unfinished(self) -> int:
        """Work still open when the shift ended. Reported rather than dropped:
        a policy that finishes little by starting little would otherwise score
        well on every other measure here."""
        return self.tickets_raised - self.tickets_finished

    @property
    def mean_response_minutes(self) -> float | None:
        """Over the tickets somebody started. None when nobody started any -
        which is a real outcome and not a zero."""
        waits = [
            ticket.response_minutes
            for ticket in self.tickets
            if ticket.response_minutes is not None
        ]
        return sum(waits) / len(waits) if waits else None

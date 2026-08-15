"""The event loop: failures arrive, rounds decide, repairs finish, the line pays.

A discrete-event loop rather than a tick-by-tick one. Nothing happens between
events, so nothing is computed between them, and a scenario covering a twelve
hour shift costs the same microseconds as one covering twelve minutes - which is
what makes the hundreds of scenarios slice 7.3 needs affordable inside one CI
job (design.md 7, the same argument `SimulatedClock` was built on).

**Time comes from the Clock port** (ADR-028), even here where it would have been
easier to keep an integer. `SimulatedClock` refuses to move backwards, which is
the one bug in an event loop that produces plausible output: an event popped out
of order gives a negative outage, and a negative outage is a policy rewarded for
a failure it never fixed.

**The engine is the only thing that knows what a repair will take.** The policy
is handed `Ticket`s carrying the estimate; the truth stays here. A simulator
whose policies could read the future would report an advantage that belongs to
the instrument.

**A policy that describes an impossible shift is stopped, not tolerated.** A
ticket nobody raised, somebody not on the roster, a technician in two places, a
crew of the wrong size: each of those would produce a schedule no shift could
have run, and the comparison would be over fiction.
"""

from __future__ import annotations

import heapq
from datetime import datetime, timedelta

from pdm.contracts import (
    Finding,
    FindingRef,
    MachineId,
    Severity,
    Technician,
    UserId,
    WorkOrder,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import Config
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
from pdm.sim.scenario import Failure, SimScenario, failures_for
from pdm.work.domain import from_finding

# Order between events sharing a timestamp. A repair finishing frees somebody
# for the round happening in the same instant, and a failure in that instant is
# work that round may place - so both come first, and the round sees the world
# after they happened rather than before.
_REPAIRED, _FAILED, _ROUND, _ENDED = 0, 1, 2, 3


class _Job:
    """A ticket, plus what the engine knows and the policy does not."""

    def __init__(self, ticket: Ticket, failure: Failure) -> None:
        self.ticket = ticket
        self.failure = failure
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.users: tuple[UserId, ...] = ()


def run(
    scenario: SimScenario,
    *,
    policy: Policy,
    config: Config,
    seed: int = 0,
    failures: tuple[Failure, ...] | None = None,
) -> SimRun:
    """Play one scenario against one policy and report what happened.

    `failures` is normally left alone: the same (scenario, seed) generates the
    same set, which is what lets 7.3 compare policies on identical work. Passing
    a set explicitly is for cases built by hand, where the answer is known by
    arithmetic rather than by running the thing being tested.
    """
    line = ProductionLine.from_config(config, scenario.line_id)
    arrivals = failures_for(scenario, config, seed=seed) if failures is None else failures
    clock = SimulatedClock(scenario.starts_at)
    # The work module takes the table keyed by plain strings, as its production
    # caller does; MachineModel is a NewType over str and the two dict types are
    # not interchangeable to a type checker.
    fallback = {str(model): table for model, table in config.policy.fallback_minutes.items()}

    events: list[Event] = []
    jobs: dict[str, _Job] = {}
    pending: list[str] = []
    in_progress: list[str] = []
    busy: dict[UserId, str] = {}
    consumed: dict[UserId, int] = {technician.user: 0 for technician in scenario.technicians}
    down_since: dict[MachineId, datetime] = {}
    outages: list[Outage] = []

    queue: list[tuple[datetime, int, int, str]] = []
    counter = 0

    def schedule(at: datetime, priority: int, payload: str) -> None:
        nonlocal counter
        heapq.heappush(queue, (at, priority, counter, payload))
        counter += 1

    def log(
        kind: EventKind,
        *,
        machine_id: MachineId | None = None,
        ticket_ref: str | None = None,
        users: tuple[UserId, ...] = (),
        minutes: float | None = None,
        note: str = "",
    ) -> None:
        events.append(
            Event(
                at=clock.now(),
                seq=len(events),
                kind=kind,
                machine_id=machine_id,
                station_id=None if machine_id is None else line.station_of(machine_id).station_id,
                ticket_ref=ticket_ref,
                users=users,
                minutes=minutes,
                note=note,
            )
        )

    def close_outage(machine_id: MachineId, at: datetime | None) -> None:
        """Called when the last unfinished ticket on a machine is done, and once
        more at the end of the run for whatever is still open."""
        began = down_since.pop(machine_id)
        ended = at
        until = at if at is not None else scenario.ends_at
        minutes = (until - began).total_seconds() / 60.0
        station = line.station_of(machine_id)
        outages.append(
            Outage(
                machine_id=machine_id,
                station_id=station.station_id,
                began_at=began,
                ended_at=ended,
                down_minutes=minutes,
                units_lost=line.units_lost(station, minutes),
            )
        )

    for index, failure in enumerate(arrivals):
        if not scenario.starts_at <= failure.at < scenario.ends_at:
            raise ValueError(
                f"failure on {failure.machine_id} at {failure.at} falls outside the run "
                f"{scenario.starts_at} - {scenario.ends_at}"
            )
        schedule(failure.at, _FAILED, str(index))

    round_at = scenario.starts_at
    while round_at < scenario.ends_at:
        schedule(round_at, _ROUND, "")
        round_at += scenario.round_interval
    schedule(scenario.ends_at, _ENDED, "")

    while queue:
        at, priority, _, payload = heapq.heappop(queue)
        clock.advance_to(at)

        if priority == _ENDED:
            break

        if priority == _FAILED:
            failure = arrivals[int(payload)]
            ref = f"WO-{int(payload) + 1:04d}"
            job = _Job(
                ticket=Ticket(
                    ref=ref,
                    order=_order_for(failure, ref, config, fallback),
                    created_at=clock.now(),
                ),
                failure=failure,
            )
            jobs[ref] = job
            pending.append(ref)
            down_since.setdefault(failure.machine_id, clock.now())
            log(
                EventKind.FAILED,
                machine_id=failure.machine_id,
                ticket_ref=ref,
                note=f"{failure.symptom_code} ({failure.severity.value})",
            )

        elif priority == _REPAIRED:
            job = jobs[payload]
            job.finished_at = clock.now()
            in_progress.remove(payload)
            for user in job.users:
                del busy[user]
                consumed[user] += job.failure.repair_minutes
            machine_id = job.failure.machine_id
            if not any(jobs[ref].failure.machine_id == machine_id for ref in pending + in_progress):
                close_outage(machine_id, clock.now())
            log(
                EventKind.REPAIRED,
                machine_id=machine_id,
                ticket_ref=payload,
                users=job.users,
                minutes=float(job.failure.repair_minutes),
            )

        elif priority == _ROUND and pending:
            state = _state(scenario, clock.now(), jobs, pending, in_progress, busy, consumed)
            placements = policy.choose(state)
            _check(placements, state, scenario.technicians)
            for placement in placements:
                job = jobs[placement.ref]
                job.started_at = clock.now()
                job.users = placement.users
                pending.remove(placement.ref)
                in_progress.append(placement.ref)
                for user in placement.users:
                    busy[user] = placement.ref
                schedule(
                    clock.now() + timedelta(minutes=job.failure.repair_minutes),
                    _REPAIRED,
                    placement.ref,
                )
                log(
                    EventKind.STARTED,
                    machine_id=job.failure.machine_id,
                    ticket_ref=placement.ref,
                    users=placement.users,
                    note=placement.priority_reason,
                )
            log(
                EventKind.ROUND,
                note=f"{len(placements)} placed, {len(pending)} pending",
            )

    clock.advance_to(scenario.ends_at)
    for machine_id in sorted(down_since):
        close_outage(machine_id, None)
    log(EventKind.ENDED, note=f"{len(pending)} pending, {len(in_progress)} in progress")

    return SimRun(
        scenario=scenario.name,
        policy=policy.name,
        seed=seed,
        started_at=scenario.starts_at,
        ended_at=scenario.ends_at,
        events=tuple(events),
        outages=tuple(sorted(outages, key=lambda outage: (outage.began_at, outage.machine_id))),
        tickets=tuple(_record(job, line) for job in jobs.values()),
    )


def _order_for(
    failure: Failure,
    ref: str,
    config: Config,
    fallback_minutes: dict[str, dict[Severity, int]],
) -> WorkOrder:
    """Priced by the work module, not by the simulator.

    The estimate a policy schedules against has to be the estimate a real ticket
    would have carried, or the comparison measures the difference between two
    pricing rules rather than between two policies. There is no playbook here -
    the simulator has no manual to draft one from - so this takes the
    `fallback_minutes` path, labelled as coarse exactly as a real one would be
    (ADR-041).
    """
    finding = Finding(
        machine_id=failure.machine_id,
        component=failure.component,
        symptom_code=failure.symptom_code,
        severity=failure.severity,
        rule_id=failure.rule_id,
        detected_at=failure.at,
        evidence={"simulated": True, "window": failure.window},
    )
    return from_finding(
        finding,
        FindingRef(f"SIM-{ref}"),
        playbook=None,
        machine_model=config.model_of(failure.machine_id),
        fallback_minutes=fallback_minutes,
    )


def _state(
    scenario: SimScenario,
    now: datetime,
    jobs: dict[str, _Job],
    pending: list[str],
    in_progress: list[str],
    busy: dict[UserId, str],
    consumed: dict[UserId, int],
) -> RoundState:
    """What the policy is shown at one round.

    `remaining_minutes` counts a job when it finishes, not while it runs, so a
    technician halfway through a repair still shows the minutes that job will
    consume. Work in flight is not hidden by that: it is offered as
    `in_progress`, which is where a policy computing committed minutes reads it
    from, and where `dispatch()` already reads it from (ADR-045).
    """
    available = {
        assignment.technician: assignment.available_minutes for assignment in scenario.assignments
    }
    return RoundState(
        now=now,
        shift_id=scenario.shift_id,
        on_date=scenario.on_date,
        pending=tuple(jobs[ref].ticket for ref in pending),
        in_progress=tuple(jobs[ref].ticket for ref in in_progress),
        technicians=scenario.technicians,
        busy=frozenset(busy),
        capacity_minutes=scenario.capacity_minutes,
        remaining_minutes=tuple(
            (technician.user, max(0, available.get(technician.user, 0) - consumed[technician.user]))
            for technician in scenario.technicians
        ),
    )


def _check(
    placements: tuple[Placement, ...],
    state: RoundState,
    technicians: tuple[Technician, ...],
) -> None:
    """Refuse a schedule no shift could have run.

    Each of these is a mistake a policy can make silently, and each one makes the
    run it appears in worthless rather than merely wrong: capacity that never
    existed, or work that was never raised, would show up in the report as an
    improvement.
    """
    roster = {technician.user for technician in technicians if technician.active}
    waiting = {ticket.ref: ticket for ticket in state.pending}
    taken: dict[UserId, str] = {user: "another job" for user in state.busy}

    for placement in placements:
        ticket = waiting.pop(placement.ref, None)
        if ticket is None:
            raise ValueError(
                f"policy placed {placement.ref}, which is not waiting at "
                f"{state.now:%Y-%m-%d %H:%M} - it was already placed, or never raised"
            )
        crew = ticket.order.required_technicians
        if len(placement.users) != crew:
            people = "one technician" if crew == 1 else f"{crew} technicians"
            raise ValueError(
                f"{placement.ref} needs {people} and was given {len(placement.users)}; "
                f"a crew of the wrong size prices the shift wrongly (ADR-025)"
            )
        for user in placement.users:
            if user not in roster:
                raise ValueError(f"policy placed {user}, who is not on the roster")
            if user in taken:
                raise ValueError(
                    f"policy placed {user} on {placement.ref} while they are on "
                    f"{taken[user]}; nobody is in two places"
                )
            taken[user] = placement.ref


def _record(job: _Job, line: ProductionLine) -> TicketRecord:
    order = job.ticket.order
    return TicketRecord(
        ref=job.ticket.ref,
        machine_id=job.failure.machine_id,
        station_id=line.station_of(job.failure.machine_id).station_id,
        severity=order.severity,
        estimated_minutes=order.estimated_minutes,
        estimate_is_fallback=order.estimate_is_fallback,
        required_skill=order.required_skill,
        repair_minutes=job.failure.repair_minutes,
        created_at=job.ticket.created_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        users=job.users,
    )

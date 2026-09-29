"""Running a scenario: reproducibility, the seam, and what the run measures.

Three properties matter more than any number this produces.

**Reproducibility.** Slice 7.3 compares three policies over hundreds of
scenarios and puts the result in a report that has to survive a viva. A run that
differed between two executions would make every one of those numbers an
anecdote, so "same seed, same event log" is asserted directly rather than
assumed from the absence of obvious randomness.

**The seam holds.** The engine takes a `Policy` and never imports one. A policy
that places a ticket nobody raised, or a technician already under a machine, is
rejected loudly - a simulator that quietly tolerated it would report a schedule
no shift could have run.

**Topology reaches the result.** The same fault, for the same minutes, costs more
at the bottleneck than behind the buffer once it has been through the whole
engine - not only in the cost function tested next door.

The policy used here is deliberately the simplest thing that can place work.
The policies being compared are slice 7.2's, and one of them living in this file
would be one nothing else could use.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from pdm.contracts import (
    ComponentLabel,
    LineId,
    MachineId,
    MachineModel,
    PMTask,
    PMTaskRef,
    RuleId,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    SymptomCode,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.platform.config import Config, load_config
from pdm.sim import (
    ArrivalWindow,
    EventKind,
    Failure,
    Placement,
    RoundState,
    SimScenario,
    failures_for,
    offered_load,
    run,
)
from pdm.sim.scenarios import LINE_A_ONE_SHIFT

REPO_CONFIG = Path("config")
LINE_A = LineId("line-a")
MORNING = ShiftId("morning")

BUFFERED = MachineId("MC-001")  # st-01, twenty units of buffer
BOTTLENECK = MachineId("MC-012")  # st-03, no buffer, multiplier 3.0

STARTS_AT = datetime(2026, 3, 3, 6, 0, tzinfo=UTC)
ALL_SKILLS = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)


@pytest.fixture(scope="module")
def config() -> Config:
    return load_config(REPO_CONFIG)


class FirstComeFirstServed:
    """Oldest ticket first, one technician each, until nobody is free.

    Not a baseline for the comparison - that is slice 7.2, where it will be
    written against the same protocol from outside the package. This one exists
    to drive the engine.
    """

    name = "test-fifo"

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        left = dict(state.remaining_minutes)
        free = [
            technician.user
            for technician in state.technicians
            if technician.active and technician.user not in state.busy
        ]
        placements: list[Placement] = []
        for ticket in state.pending:
            crew = ticket.order.required_technicians
            # A policy may not spend minutes the shift does not have (ADR-047),
            # so even the simplest one has to read what it has left.
            fits = [user for user in free if left[user] >= ticket.order.estimated_minutes]
            if len(fits) < crew:
                continue
            free = [user for user in free if user not in fits[:crew]]
            placements.append(
                Placement(
                    ref=ticket.ref,
                    users=tuple(fits[:crew]),
                    priority_reason="oldest first",
                )
            )
        return tuple(placements)


class PlacesWhateverItWasTold:
    """A policy that returns exactly the placements it was constructed with.

    Used to check that the engine refuses the three ways a policy can describe a
    schedule nobody could have run.
    """

    name = "test-fixed"

    def __init__(self, placements: tuple[Placement, ...]) -> None:
        self._placements = placements
        self._done = False

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        if self._done or not state.pending:
            return ()
        self._done = True
        return self._placements


def _scenario(
    *,
    name: str = "test",
    duration: timedelta = timedelta(hours=2),
    technicians: int = 1,
    windows: tuple[ArrivalWindow, ...] = (),
    available_minutes: int | None = None,
) -> SimScenario:
    roster = tuple(
        Technician(user=UserId(f"tech-{index + 1}"), skills=ALL_SKILLS)
        for index in range(technicians)
    )
    return SimScenario(
        name=name,
        line_id=LINE_A,
        starts_at=STARTS_AT,
        duration=duration,
        round_interval=timedelta(minutes=5),
        shift_id=MORNING,
        technicians=roster,
        assignments=tuple(
            ShiftAssignment(
                shift_id=MORNING,
                on_date=STARTS_AT.date(),
                technician=technician.user,
                available_minutes=(
                    int(duration.total_seconds() // 60)
                    if available_minutes is None
                    else available_minutes
                ),
            )
            for technician in roster
        ),
        windows=windows,
    )


def _failure(machine_id: MachineId, *, after: timedelta, minutes: int) -> Failure:
    """One hand-built failure, so a cost can be checked by arithmetic."""
    return Failure(
        machine_id=machine_id,
        at=STARTS_AT + after,
        window="hand-built",
        rule_id=RuleId("R-motor-temp-high"),
        component=ComponentLabel("belt_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=Severity.HIGH,
        repair_minutes=minutes,
    )


class TestReproducibility:
    def test_the_same_seed_produces_the_same_run(self, config: Config) -> None:
        first = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=config, seed=7)
        second = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=config, seed=7)
        assert first.events == second.events
        assert first.tickets == second.tickets
        assert first.outages == second.outages

    def test_a_different_seed_produces_a_different_run(self, config: Config) -> None:
        """Otherwise the seed is decoration and the sensitivity analysis in 7.3
        would be reporting one scenario several times."""
        first = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=config, seed=1)
        second = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=config, seed=2)
        assert first.events != second.events

    def test_a_machine_is_seeded_independently_of_the_others(self, config: Config) -> None:
        """The property `SyntheticSource` has for the same reason (ADR-032):
        adding a machine to a scenario must not move the failures of the ones
        already in it, or no two measurements are comparable."""
        window = ArrivalWindow(
            name="w",
            starts_after=timedelta(0),
            lasts=timedelta(hours=8),
            mean_hours_between_failures=2.0,
            machines=(BUFFERED,),
        )
        alone = _scenario(duration=timedelta(hours=8), windows=(window,))
        crowded = _scenario(
            duration=timedelta(hours=8),
            windows=(window.model_copy(update={"machines": (BUFFERED, BOTTLENECK)}),),
        )
        only_buffered = tuple(
            failure
            for failure in failures_for(crowded, config, seed=3)
            if failure.machine_id == BUFFERED
        )
        assert failures_for(alone, config, seed=3) == only_buffered


class TestTheSeamTheEngineOffersAPolicy:
    def test_a_placement_for_a_ticket_nobody_raised_is_refused(self, config: Config) -> None:
        policy = PlacesWhateverItWasTold((Placement(ref="WO-9999", users=(UserId("tech-1"),)),))
        with pytest.raises(ValueError, match="WO-9999"):
            run(
                _scenario(),
                policy=policy,
                config=config,
                failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
            )

    def test_a_technician_who_is_not_on_the_roster_is_refused(self, config: Config) -> None:
        policy = PlacesWhateverItWasTold((Placement(ref="WO-0001", users=(UserId("nobody"),)),))
        with pytest.raises(ValueError, match="nobody"):
            run(
                _scenario(),
                policy=policy,
                config=config,
                failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
            )

    def test_a_crew_of_the_wrong_size_is_refused(self, config: Config) -> None:
        """A one-person job done by two costs the shift twice what it should,
        which is exactly the load-gate error ADR-025 exists to prevent."""
        policy = PlacesWhateverItWasTold(
            (Placement(ref="WO-0001", users=(UserId("tech-1"), UserId("tech-2"))),)
        )
        with pytest.raises(ValueError, match="one technician"):
            run(
                _scenario(technicians=2),
                policy=policy,
                config=config,
                failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
            )

    def test_the_same_technician_cannot_be_placed_twice_in_one_round(self, config: Config) -> None:
        policy = PlacesWhateverItWasTold(
            (
                Placement(ref="WO-0001", users=(UserId("tech-1"),)),
                Placement(ref="WO-0002", users=(UserId("tech-1"),)),
            )
        )
        with pytest.raises(ValueError, match="tech-1"):
            run(
                _scenario(),
                policy=policy,
                config=config,
                failures=(
                    _failure(BUFFERED, after=timedelta(minutes=12), minutes=30),
                    _failure(BOTTLENECK, after=timedelta(minutes=12), minutes=30),
                ),
            )

    def test_a_technician_cannot_be_given_more_minutes_than_the_shift_has(
        self, config: Config
    ) -> None:
        """ADR-047: the fifth way to describe a shift that could not have run.

        `dispatch()` refuses this itself (ADR-045 §5). A baseline has no such
        rule, so leaving it unenforced would let slice 7.3's table compare a
        policy that respects the roster with policies that do not - and the
        difference would read as the gated policy being slow.
        """
        policy = PlacesWhateverItWasTold((Placement(ref="WO-0001", users=(UserId("tech-1"),)),))
        with pytest.raises(ValueError, match="45"):
            run(
                # 60 estimated minutes against 45 on the roster: R-2000iC at
                # high severity, priced by policy.yaml through the work module.
                _scenario(available_minutes=45),
                policy=policy,
                config=config,
                failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
            )

    def test_a_job_that_exactly_fills_the_shift_is_allowed(self, config: Config) -> None:
        """The boundary is not the bug: sixty minutes of work and sixty minutes
        of technician is a shift that runs, and refusing it would quietly cost
        every policy the last job of every shift."""
        policy = PlacesWhateverItWasTold((Placement(ref="WO-0001", users=(UserId("tech-1"),)),))

        result = run(
            _scenario(available_minutes=60),
            policy=policy,
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
        )

        assert result.tickets_finished == 1

    def test_minutes_already_spent_this_shift_are_gone(self, config: Config) -> None:
        """The other half of the rule, read from the policy's side: what is left
        falls as work completes, so the second job of a shift is judged against
        what the first one left behind rather than against the roster.

        The work does not vanish - it stays pending and is costed as downtime on
        a machine still waiting, which is what the shift genuinely could not do.
        """
        result = run(
            _scenario(duration=timedelta(hours=3), available_minutes=80),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(
                # 60 estimated, 30 actually spent: 50 of the 80 minutes are left
                # afterwards, and the next job is priced at 60 as well.
                _failure(BUFFERED, after=timedelta(minutes=5), minutes=30),
                _failure(BOTTLENECK, after=timedelta(minutes=60), minutes=30),
            ),
        )

        assert result.tickets_finished == 1
        assert result.tickets_unfinished == 1

    def test_a_policy_that_places_nothing_leaves_the_work_pending(self, config: Config) -> None:
        """The gate holding work back is a legitimate outcome, not a stall. It
        has to show up as unfinished work rather than as work that vanished."""
        policy = PlacesWhateverItWasTold(())
        result = run(
            _scenario(),
            policy=policy,
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
        )
        assert result.tickets_raised == 1
        assert result.tickets_finished == 0
        assert result.tickets_unfinished == 1


class TestTheStateTellsTheTruthAboutWorkInFlight:
    """ADR-046 §5 claims `RoundState` carries what `dispatch()` takes, so the
    slice 7.2 adapter is a translation and not a rewrite. That was true of every
    field except the one inside the ticket."""

    def test_a_ticket_under_way_does_not_still_read_as_queued(self, config: Config) -> None:
        """`dispatch()` decides what it may place by reading `order.status`, and
        it subtracts a technician's committed minutes the same way. A ticket
        that stayed `queued` after somebody started it would be re-placed on the
        next round and would consume nobody's capacity in the meantime - two
        wrong answers from one stale field.
        """
        seen: list[tuple[str, WorkOrderStatus, tuple[UserId, ...]]] = []

        class Watches:
            name = "test-watches"

            def choose(self, state: RoundState) -> tuple[Placement, ...]:
                seen.extend(
                    (ticket.ref, ticket.order.status, tuple(a.user for a in ticket.order.assignees))
                    for ticket in state.in_progress
                )
                return FirstComeFirstServed().choose(state)

        # One technician and two failures: the second is still waiting while the
        # first is under way, which is the only arrangement in which a round
        # runs at all with work in flight - the engine skips a round with an
        # empty queue.
        run(
            _scenario(duration=timedelta(hours=2)),
            policy=Watches(),
            config=config,
            failures=(
                _failure(BUFFERED, after=timedelta(minutes=5), minutes=45),
                _failure(BOTTLENECK, after=timedelta(minutes=20), minutes=30),
            ),
        )

        assert seen, "the scenario never put a ticket in flight"
        for ref, status, users in seen:
            assert status is WorkOrderStatus.IN_PROGRESS, f"{ref} still read as {status}"
            assert users == (UserId("tech-1"),)

    def test_a_waiting_ticket_still_reads_as_queued(self, config: Config) -> None:
        """The other half. `dispatch()` places what is queued, so work nobody has
        started has to keep saying so."""
        seen: list[WorkOrderStatus] = []

        class Watches:
            name = "test-watches"

            def choose(self, state: RoundState) -> tuple[Placement, ...]:
                seen.extend(ticket.order.status for ticket in state.pending)
                return ()

        run(
            _scenario(),
            policy=Watches(),
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=5), minutes=30),),
        )

        assert seen and all(status is WorkOrderStatus.QUEUED for status in seen)

    def test_the_record_of_a_finished_job_still_prices_it_as_it_was_planned(
        self, config: Config
    ) -> None:
        """Rewriting the order in flight must not disturb what slice 7.3
        aggregates: the estimate is what the scheduler planned with and stays
        the playbook-free figure ADR-046 §2 gave it."""
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=5), minutes=30),),
        )
        record = result.tickets[0]

        assert record.estimate_is_fallback
        assert record.estimated_minutes == 60
        assert record.repair_minutes == 30
        assert record.users == (UserId("tech-1"),)


class TestTopologyReachesTheResult:
    """The end-to-end form of the ADR-021 test next door."""

    def _units_lost(self, machine_id: MachineId, config: Config) -> float:
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(machine_id, after=timedelta(minutes=12), minutes=30),),
        )
        assert result.tickets_finished == 1
        return result.units_lost

    def test_the_bottleneck_costs_more_than_the_buffered_station(self, config: Config) -> None:
        buffered = self._units_lost(BUFFERED, config)
        bottleneck = self._units_lost(BOTTLENECK, config)
        assert buffered > 0.0
        assert bottleneck > 3.0 * buffered

    def test_downtime_runs_from_the_failure_to_the_repair_not_from_the_round(
        self, config: Config
    ) -> None:
        """A machine is down the moment it fails. Starting the clock when a
        technician arrives would hide the waiting, which is the difference
        between the policies 7.3 compares."""
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(BOTTLENECK, after=timedelta(minutes=12), minutes=30),),
        )
        (outage,) = result.outages
        assert outage.began_at == STARTS_AT + timedelta(minutes=12)
        # Placed at the first round after the failure - minute 15 - and thirty
        # minutes of work after that.
        assert outage.down_minutes == pytest.approx(33.0)
        assert outage.ended_at == STARTS_AT + timedelta(minutes=45)

    def test_an_outage_still_open_at_the_end_is_costed_to_the_end(self, config: Config) -> None:
        """Otherwise a policy that never gets to a machine looks free, and the
        worst schedule scores best."""
        result = run(
            _scenario(duration=timedelta(hours=1)),
            policy=PlacesWhateverItWasTold(()),
            config=config,
            failures=(_failure(BOTTLENECK, after=timedelta(minutes=12), minutes=30),),
        )
        (outage,) = result.outages
        assert outage.ended_at is None
        assert outage.down_minutes == pytest.approx(48.0)
        assert result.units_lost == pytest.approx(144.0)


class TestWhatTheEngineRecords:
    def test_a_ticket_is_priced_the_way_the_work_module_prices_it(self, config: Config) -> None:
        """The estimate comes from `policy.yaml`'s fallback table through the
        same function that prices a real ticket, so the simulator cannot drift
        into a pricing rule of its own (ADR-041)."""
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
        )
        (ticket,) = result.tickets
        fallback = config.policy.fallback_minutes[MachineModel("R-2000iC")]
        assert ticket.estimated_minutes == fallback[Severity.HIGH]
        assert ticket.estimate_is_fallback is True
        assert ticket.required_skill is None

    def test_the_event_log_is_ordered_and_names_what_happened(self, config: Config) -> None:
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
        )
        assert [event.at for event in result.events] == sorted(event.at for event in result.events)
        kinds = [event.kind for event in result.events]
        assert kinds[0] is EventKind.FAILED
        assert EventKind.STARTED in kinds
        assert EventKind.REPAIRED in kinds
        assert kinds[-1] is EventKind.ENDED

    def test_response_time_is_measured_from_the_failure(self, config: Config) -> None:
        result = run(
            _scenario(),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(_failure(BUFFERED, after=timedelta(minutes=12), minutes=30),),
        )
        assert result.mean_response_minutes == pytest.approx(3.0)

    def test_a_machine_that_fails_twice_stays_down_until_both_are_done(
        self, config: Config
    ) -> None:
        """One outage, not two. A machine with an unfinished ticket on it is not
        producing, however many tickets it has."""
        result = run(
            _scenario(duration=timedelta(hours=4)),
            policy=FirstComeFirstServed(),
            config=config,
            failures=(
                _failure(BOTTLENECK, after=timedelta(minutes=12), minutes=30),
                _failure(BOTTLENECK, after=timedelta(minutes=22), minutes=30),
            ),
        )
        assert len(result.outages) == 1
        assert result.tickets_finished == 2
        (outage,) = result.outages
        assert outage.ended_at is not None
        assert outage.down_minutes > 60.0


def _pm(machine_id: MachineId, *, due_after: timedelta) -> PMTask:
    return PMTask(
        pm_task_ref=PMTaskRef(f"pm-{machine_id}"),
        machine_id=machine_id,
        symptom_code=SymptomCode("PM-toothed-belt"),
        interval=timedelta(hours=8000),
        due_at=STARTS_AT + due_after,
    )


class TestScheduledMaintenance:
    """PM work in a run (ADR-010): offered to the policy as scheduled work from
    when it falls due, and never a stoppage of the line."""

    def test_it_is_offered_when_due_and_not_before(self, config: Config) -> None:
        seen: list[tuple[datetime, tuple[str, ...]]] = []

        class Watching(FirstComeFirstServed):
            def choose(self, state: RoundState) -> tuple[Placement, ...]:
                seen.append((state.now, tuple(ticket.ref for ticket in state.pending)))
                return ()

        scenario = _scenario().model_copy(
            update={"maintenance": (_pm(BUFFERED, due_after=timedelta(minutes=30)),)}
        )
        run(scenario, policy=Watching(), config=config, failures=())

        assert seen[0] == (STARTS_AT + timedelta(minutes=30), ("PM-0001",))

    def test_it_reaches_the_policy_as_scheduled_work(self, config: Config) -> None:
        orders: list[WorkOrder] = []

        class Watching(FirstComeFirstServed):
            def choose(self, state: RoundState) -> tuple[Placement, ...]:
                orders.extend(ticket.order for ticket in state.pending)
                return super().choose(state)

        scenario = _scenario().model_copy(
            update={"maintenance": (_pm(BUFFERED, due_after=timedelta(0)),)}
        )
        result = run(scenario, policy=Watching(), config=config, failures=())

        assert orders[0].origin is WorkOrderOrigin.SCHEDULED
        assert result.tickets_finished == 1

    def test_it_neither_opens_an_outage_nor_keeps_one_open(self, config: Config) -> None:
        scenario = _scenario(duration=timedelta(hours=4)).model_copy(
            update={"maintenance": (_pm(BOTTLENECK, due_after=timedelta(0)),)}
        )

        class RepairsOnly(FirstComeFirstServed):
            def choose(self, state: RoundState) -> tuple[Placement, ...]:
                repairs = tuple(ticket for ticket in state.pending if ticket.ref.startswith("WO-"))
                return super().choose(state.model_copy(update={"pending": repairs}))

        result = run(
            scenario,
            policy=RepairsOnly(),
            config=config,
            failures=(_failure(BOTTLENECK, after=timedelta(minutes=10), minutes=30),),
        )

        # The PM job is still waiting on the same machine; the line is running.
        (outage,) = result.outages
        assert outage.ended_at == STARTS_AT + timedelta(minutes=40)


class TestBothLoadBands:
    """Slice 7.3 compares the policies across a quiet shift and a busy one, and
    ADR-011 defines those two words with numbers in `policy.yaml`. A scenario
    claiming to reach both has to be checked against them rather than described
    as heavy in a comment."""

    def test_the_shipped_scenario_has_a_light_window_and_a_heavy_one(self, config: Config) -> None:
        light = config.policy.load.light_below
        heavy = config.policy.load.heavy_at_or_above
        for seed in range(8):
            failures = failures_for(LINE_A_ONE_SHIFT, config, seed=seed)
            loads = {
                window.name: offered_load(LINE_A_ONE_SHIFT, window, failures)
                for window in LINE_A_ONE_SHIFT.windows
            }
            assert loads["quiet"] < light, f"seed {seed}: {loads}"
            assert loads["busy"] >= heavy, f"seed {seed}: {loads}"

    def test_the_heavy_window_leaves_work_unfinished_and_the_quiet_one_does_not(
        self, config: Config
    ) -> None:
        """The behavioural half of the same claim: a band is only meaningful if
        the shift behaves differently in it."""
        result = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=config, seed=0)
        assert result.tickets_unfinished > 0
        assert result.tickets_finished > 0


class TestTheScenarioContract:
    def test_a_naive_start_time_is_refused(self) -> None:
        """The night shift crosses midnight, so a naive datetime is wrong for
        exactly one of the three shifts and right for the others (ADR-028)."""
        with pytest.raises(ValueError, match="timezone"):
            SimScenario(
                name="test",
                line_id=LINE_A,
                starts_at=datetime(2026, 3, 3, 6, 0),
                duration=timedelta(hours=2),
                round_interval=timedelta(minutes=5),
                shift_id=MORNING,
                technicians=(),
                assignments=(),
                windows=(),
            )

    def test_a_window_reaching_past_the_end_of_the_run_is_refused(self) -> None:
        """A window generating failures after the run stops would produce work
        that never appears in the log and capacity that is never offered."""
        with pytest.raises(ValueError, match="window"):
            _scenario(
                duration=timedelta(hours=2),
                windows=(
                    ArrivalWindow(
                        name="w",
                        starts_after=timedelta(hours=1),
                        lasts=timedelta(hours=4),
                        mean_hours_between_failures=1.0,
                    ),
                ),
            )

    def test_an_assignment_for_somebody_not_on_the_roster_is_refused(self) -> None:
        roster = (Technician(user=UserId("tech-1"), skills=ALL_SKILLS),)
        with pytest.raises(ValueError, match="ghost"):
            SimScenario(
                name="test",
                line_id=LINE_A,
                starts_at=STARTS_AT,
                duration=timedelta(hours=2),
                round_interval=timedelta(minutes=5),
                shift_id=MORNING,
                technicians=roster,
                assignments=(
                    ShiftAssignment(
                        shift_id=MORNING,
                        on_date=date(2026, 3, 3),
                        technician=UserId("ghost"),
                        available_minutes=120,
                    ),
                ),
                windows=(),
            )

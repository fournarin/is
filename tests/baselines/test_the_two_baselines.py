"""What a plant does today, and the two failures slice 7.3 measures the cost of.

A baseline is only worth having if it fails in a way somebody recognises. These
two do, and the tests naming those failures are the ones that matter:

  * `TestFirstComeFirstServed::test_a_routine_job_goes_ahead_of_a_critical_one`
    - the queue with nobody scheduling it. Anybody who has worked in a plant has
      seen this happen; the point of measuring it is to say how much it costs.
  * `TestThePriorityMatrix::test_the_bottleneck_and_the_buffered_station_rank_alike`
    - ADR-021's whole argument, from the other side. A matrix has no cell for a
      buffer, so thirty minutes at the station that stops the line and thirty
      minutes behind twenty units of stock are the same job to it.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from pdm.baselines import FirstComeFirstServed, PriorityMatrix
from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingRef,
    MachineId,
    RuleId,
    Severity,
    ShiftId,
    SkillId,
    SymptomCode,
    Technician,
    UserId,
)
from pdm.platform.config import load_config
from pdm.sim import RoundState, Ticket
from pdm.work.domain import from_finding

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MORNING = ShiftId("morning")
BUFFERED = MachineId("MC-001")  # st-01, twenty units of buffer
BOTTLENECK = MachineId("MC-012")  # st-03, no buffer, multiplier 3.0
ANA = UserId("tech-ana")
BEN = UserId("tech-ben")
ALL_SKILLS = frozenset(SkillId(name) for name in ("robot_mechanical", "electrical"))

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


def _ticket(
    ref: str,
    *,
    machine_id: MachineId = BUFFERED,
    severity: Severity = Severity.MEDIUM,
    age_minutes: int = 0,
    crew: int = 1,
) -> Ticket:
    """A ticket priced exactly as the work module would price it (ADR-046 §2)."""
    finding = Finding(
        machine_id=machine_id,
        component=ComponentLabel("belt_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=severity,
        rule_id=RuleId("R-motor-temp-high"),
        detected_at=NOW - timedelta(minutes=age_minutes),
        evidence={"test": True},
    )
    order = from_finding(
        finding,
        FindingRef(f"F-{ref}"),
        playbook=None,
        machine_model=CONFIG.model_of(machine_id),
        fallback_minutes=FALLBACK,
    )
    if crew != 1:
        order = order.model_copy(update={"required_technicians": crew})
    return Ticket(ref=ref, order=order, created_at=NOW - timedelta(minutes=age_minutes))


def _state(*tickets: Ticket, crew: int = 2, minutes: int = 480) -> RoundState:
    people = tuple(Technician(user=user, skills=ALL_SKILLS) for user in (ANA, BEN)[:crew])
    return RoundState(
        now=NOW,
        shift_id=MORNING,
        on_date=date(2026, 3, 3),
        pending=tickets,
        technicians=people,
        capacity_minutes=minutes * len(people),
        remaining_minutes=tuple((person.user, minutes) for person in people),
    )


class TestFirstComeFirstServed:
    def test_a_routine_job_goes_ahead_of_a_critical_one(self) -> None:
        """3A's defining failure, and the reason a plant that runs on a queue can
        have its most expensive fault behind six routine ones."""
        state = _state(
            _ticket("WO-1", severity=Severity.LOW, age_minutes=30),
            _ticket("WO-2", machine_id=BOTTLENECK, severity=Severity.CRITICAL, age_minutes=1),
        )

        placed = FirstComeFirstServed().choose(state)

        assert [one.ref for one in placed] == ["WO-1", "WO-2"]

    def test_severity_changes_nothing_at_all(self) -> None:
        """Not an oversight: 3A is what a queue does, and a queue does not read."""
        older = _ticket("WO-1", severity=Severity.LOW, age_minutes=30)
        newer = _ticket("WO-2", severity=Severity.CRITICAL, age_minutes=1)

        assert [one.ref for one in FirstComeFirstServed().choose(_state(older, newer))] == [
            "WO-1",
            "WO-2",
        ]
        assert [one.ref for one in FirstComeFirstServed().choose(_state(newer, older))] == [
            "WO-1",
            "WO-2",
        ]


class TestThePriorityMatrix:
    def test_the_bottleneck_and_the_buffered_station_rank_alike(self) -> None:
        """ADR-021 from the other side. The matrix has four severities and a
        line, and no cell at all for twenty units of stock standing between a
        stopped machine and a stopped line."""
        first = _ticket("WO-1", machine_id=BUFFERED, severity=Severity.HIGH, age_minutes=10)
        second = _ticket("WO-2", machine_id=BOTTLENECK, severity=Severity.HIGH, age_minutes=5)
        matrix = PriorityMatrix()

        assert matrix.cell(first) == matrix.cell(second)
        # So the only thing left to separate them is which arrived first, which
        # is 3A again wearing a different hat.
        assert [one.ref for one in matrix.choose(_state(first, second))] == ["WO-1", "WO-2"]

    def test_it_does_rank_by_severity_which_is_what_makes_it_better_than_fifo(self) -> None:
        state = _state(
            _ticket("WO-1", severity=Severity.LOW, age_minutes=30),
            _ticket("WO-2", severity=Severity.CRITICAL, age_minutes=1),
        )

        assert [one.ref for one in PriorityMatrix().choose(state)] == ["WO-2", "WO-1"]

    def test_a_line_that_matters_more_outranks_a_worse_fault_on_one_that_does_not(self) -> None:
        """The other half of the sheet. The table is supplied rather than read
        from config: it is the plant's own document, and a number for it in
        `plant.yaml` would look measured."""
        matrix = PriorityMatrix(importance_of=lambda machine: 3.0 if machine == BOTTLENECK else 1.0)
        state = _state(
            _ticket("WO-1", machine_id=BUFFERED, severity=Severity.CRITICAL, age_minutes=30),
            _ticket("WO-2", machine_id=BOTTLENECK, severity=Severity.HIGH, age_minutes=1),
        )

        # critical x 1 = 3 against high x 3 = 6.
        assert [one.ref for one in matrix.choose(state)] == ["WO-2", "WO-1"]


class TestBothObeyTheSamePhysics:
    """ADR-046 §5 and ADR-047: a placement that could not have happened is
    refused by the engine, so a baseline that ignored the roster would not be a
    worse policy - it would be an invalid run."""

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_nobody_is_given_minutes_the_shift_does_not_have(self, policy: object) -> None:
        state = _state(_ticket("WO-1"), crew=1, minutes=10)  # a 45-minute job

        assert policy.choose(state) == ()  # type: ignore[attr-defined]

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_a_busy_technician_is_not_given_a_second_machine(self, policy: object) -> None:
        state = _state(_ticket("WO-1"), crew=1).model_copy(update={"busy": frozenset({ANA})})

        assert policy.choose(state) == ()  # type: ignore[attr-defined]

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_a_two_person_job_with_one_person_free_is_not_half_placed(self, policy: object) -> None:
        state = _state(_ticket("WO-1", crew=2), crew=1)

        assert policy.choose(state) == ()  # type: ignore[attr-defined]

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_a_job_nobody_can_crew_does_not_stall_the_one_behind_it(self, policy: object) -> None:
        """Skipping rather than stopping. Both baselines would otherwise stall
        for ever on a job the shift can never do, and the comparison would be
        measuring the stall."""
        state = _state(
            _ticket("WO-1", crew=2, severity=Severity.CRITICAL, age_minutes=30),
            _ticket("WO-2", age_minutes=1),
            crew=1,
        )

        assert [one.ref for one in policy.choose(state)] == ["WO-2"]  # type: ignore[attr-defined]

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_the_same_state_gives_the_same_answer(self, policy: object) -> None:
        """Neither reads a clock or a connection, so twice is the same twice.
        Slice 7.3 compares event logs with `==`; a policy that varied would make
        every number in that table an anecdote."""
        state = _state(
            _ticket("WO-1", machine_id=BOTTLENECK, severity=Severity.HIGH, age_minutes=5),
            _ticket("WO-2", severity=Severity.HIGH, age_minutes=5),
        )

        assert policy.choose(state) == policy.choose(state)  # type: ignore[attr-defined]


class TestTheEngineAcceptsBoth:
    """The slice is only finished if the instrument can actually run them.

    `_check` refuses a placement describing a shift that could not have happened
    (ADR-046 §5, ADR-047), so a baseline that got the roster or the minutes wrong
    would not produce a worse number here - it would produce a `ValueError` and
    no number at all.
    """

    @pytest.mark.parametrize("policy", [FirstComeFirstServed(), PriorityMatrix()])
    def test_a_whole_shift_runs_and_repeats_exactly(self, policy: object) -> None:
        from pdm.sim import run
        from pdm.sim.scenarios import LINE_A_ONE_SHIFT

        first = run(LINE_A_ONE_SHIFT, policy=policy, config=CONFIG, seed=0)  # type: ignore[arg-type]
        second = run(LINE_A_ONE_SHIFT, policy=policy, config=CONFIG, seed=0)  # type: ignore[arg-type]

        assert first.events == second.events
        assert first.tickets_raised > 0
        assert first.tickets_finished > 0

    def test_the_two_do_not_produce_the_same_shift(self) -> None:
        """If they did, there would be nothing for slice 7.3 to report."""
        from pdm.sim import run
        from pdm.sim.scenarios import LINE_A_ONE_SHIFT

        fifo = run(LINE_A_ONE_SHIFT, policy=FirstComeFirstServed(), config=CONFIG, seed=0)
        matrix = run(LINE_A_ONE_SHIFT, policy=PriorityMatrix(), config=CONFIG, seed=0)

        assert fifo.events != matrix.events

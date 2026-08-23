"""The generator has to do what its answer key says it did (ADR-072 §5).

`fixtures/history` is a measuring instrument, and an instrument that is not
checked is a number with a decimal point on it. Two things are asserted: the same
seed gives the same history, and the machines the key names as degraded really do
fail more often inside the windows it names - because a measurement scored
against a key the generator did not honour would report the ranking's accuracy as
whatever the key happened to say.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fixtures.history import (
    LINE_A_ONE_YEAR,
    DegradationEpisode,
    HistoryPlan,
    MachinePlan,
    SyntheticHistory,
)
from pdm.contracts import MachineId, WorkOrderOrigin, WorkOrderStatus, WorkOutcome
from pdm.health import ClosedRepair

PLAN = LINE_A_ONE_YEAR


class TestItReproduces:
    def test_the_same_seed_twice_gives_the_same_history(self) -> None:
        first = SyntheticHistory(PLAN, seed=7).orders()
        again = SyntheticHistory(PLAN, seed=7).orders()
        assert first == again

    def test_different_seeds_give_different_histories(self) -> None:
        """Otherwise forty seeds would be one measurement reported forty times."""
        first = SyntheticHistory(PLAN, seed=7).orders()
        other = SyntheticHistory(PLAN, seed=8).orders()
        assert first != other

    def test_one_machines_stream_does_not_move_when_another_plan_changes(self) -> None:
        """Seeded per machine, so adding a machine does not rewrite the others."""
        shorter = PLAN.model_copy(update={"machines": PLAN.machines[:2]})
        whole = {
            ref: order
            for ref, order, _ in SyntheticHistory(PLAN, seed=3).orders()
            if order.machine_id == PLAN.machines[0].machine_id
        }
        part = {
            ref: order
            for ref, order, _ in SyntheticHistory(shorter, seed=3).orders()
            if order.machine_id == PLAN.machines[0].machine_id
        }
        assert whole == part


class TestTheKeyDescribesWhatWasGenerated:
    def test_the_key_names_exactly_the_machines_the_plan_degrades(self) -> None:
        assert PLAN.degraded == {MachineId("MC-012"), MachineId("MC-018")}
        assert {episode.machine_id for episode in PLAN.answer_key} == PLAN.degraded

    @pytest.mark.parametrize("seed", range(6))
    def test_a_degraded_machine_fails_faster_inside_its_own_window(self, seed: int) -> None:
        """The property the whole measurement rests on, checked per machine.

        Compared against that machine's own rate outside the window rather than
        against another machine's, so a seed where one machine simply drew badly
        cannot make this pass or fail for the wrong reason.
        """
        history = SyntheticHistory(PLAN, seed=seed)
        repairs = history.repairs()
        for episode in PLAN.answer_key:
            inside, outside = _rates_inside_and_outside(repairs, episode, PLAN)
            assert inside > outside, f"{episode.machine_id} at seed {seed}"

    def test_the_undegraded_machines_have_no_window_at_all(self) -> None:
        quiet = {machine.machine_id for machine in PLAN.machines if machine.degradation is None}
        assert quiet == {MachineId("MC-001"), MachineId("MC-004")}


class TestTheRowsAreTheShapeThisSystemWrites:
    def test_every_generated_order_is_closed_and_says_how_it_ended(self) -> None:
        for ref, order, closed_at in SyntheticHistory(PLAN, seed=1).orders():
            assert order.status is WorkOrderStatus.CLOSED
            assert order.outcome is not None
            # The reduction the health module reads has to accept it unchanged.
            ClosedRepair.from_order(ref, order, closed_at=closed_at)

    def test_pm_work_is_scheduled_work_and_is_never_counted_as_a_failure(self) -> None:
        repairs = SyntheticHistory(PLAN, seed=1).repairs()
        scheduled = [r for r in repairs if r.origin is WorkOrderOrigin.SCHEDULED]
        assert scheduled, "the plan is meant to generate PM work as well as faults"
        assert not any(repair.is_failure for repair in scheduled)

    def test_the_plan_generates_the_false_alarms_it_says_it_does(self) -> None:
        repairs = SyntheticHistory(PLAN, seed=1).repairs()
        alarms = [r for r in repairs if r.outcome is WorkOutcome.NO_PROBLEM_FOUND]
        assert {r.machine_id for r in alarms} == {MachineId("MC-004")}

    def test_the_standing_pm_task_is_overdue_only_where_the_plan_skipped_one(self) -> None:
        tasks = {task.machine_id: task for task in SyntheticHistory(PLAN, seed=1).pm_tasks()}
        assert tasks[MachineId("MC-001")].is_due(PLAN.ends_at)
        assert not tasks[MachineId("MC-012")].is_due(PLAN.ends_at)


class TestAKeyThatCouldNotBeTrueIsRefused:
    def test_an_episode_naming_another_machine_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="would score every ranking"):
            MachinePlan(
                machine_id=MachineId("MC-001"),
                baseline_per_100_days=1.0,
                degradation=DegradationEpisode(
                    machine_id=MachineId("MC-012"),
                    began_at=datetime(2026, 1, 1, tzinfo=UTC),
                    multiplier=2.0,
                ),
            )

    def test_an_episode_outside_the_span_it_is_the_key_for_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="outside the history"):
            HistoryPlan(
                name="bad",
                starts_at=datetime(2026, 1, 1, tzinfo=UTC),
                ends_at=datetime(2026, 6, 1, tzinfo=UTC),
                machines=(
                    MachinePlan(
                        machine_id=MachineId("MC-001"),
                        baseline_per_100_days=1.0,
                        degradation=DegradationEpisode(
                            machine_id=MachineId("MC-001"),
                            began_at=datetime(2025, 1, 1, tzinfo=UTC),
                            multiplier=2.0,
                        ),
                    ),
                ),
            )

    def test_an_episode_that_ends_before_it_begins_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="cannot end before it began"):
            DegradationEpisode(
                machine_id=MachineId("MC-001"),
                began_at=datetime(2026, 6, 1, tzinfo=UTC),
                ends_at=datetime(2026, 1, 1, tzinfo=UTC),
                multiplier=2.0,
            )

    def test_a_multiplier_that_degrades_nothing_is_refused(self) -> None:
        """A key naming a machine that was treated like the others would report
        the ranking as wrong about a machine nothing was done to."""
        with pytest.raises(ValidationError):
            DegradationEpisode(
                machine_id=MachineId("MC-001"),
                began_at=datetime(2026, 1, 1, tzinfo=UTC),
                multiplier=1.0,
            )


def _rates_inside_and_outside(
    repairs: tuple[ClosedRepair, ...],
    episode: DegradationEpisode,
    plan: HistoryPlan,
) -> tuple[float, float]:
    faults = [
        repair
        for repair in repairs
        if repair.machine_id == episode.machine_id and repair.is_failure
    ]
    inside_days = ((episode.ends_at or plan.ends_at) - episode.began_at).total_seconds() / 86_400.0
    outside_days = plan.span.total_seconds() / 86_400.0 - inside_days
    inside = [f for f in faults if episode.covers(f.closed_at)]
    outside = [f for f in faults if not episode.covers(f.closed_at)]
    return len(inside) / inside_days, len(outside) / max(outside_days, 1e-9)

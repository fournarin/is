"""The diagnosis has to reproduce, and its instruments have to be honest.

`scripts/diagnose_comparison.py` answers four questions by taking pieces out of
3C and running the same shifts again. That is only evidence if two things hold:
the whole thing is deterministic, and each instrument does what its name says.
The second is the part worth testing. An ablation that quietly failed to ablate
would produce a table saying "the gate costs nothing" for the most convincing
possible reason - that the gate was still there.

Kept to two seeds. The committed tables are twenty; what is checked here is the
machinery, not the figures, which would make every honest re-measurement a
failing test.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import datetime
from itertools import pairwise
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pdm.contracts import UserId  # noqa: E402
from pdm.platform.config import load_config  # noqa: E402
from pdm.sim import run  # noqa: E402
from pdm.sim.scenarios import LINE_A_ONE_SHIFT  # noqa: E402
from scripts.compare_policies import GateAndScore, compare, with_roster  # noqa: E402
from scripts.diagnose_comparison import (  # noqa: E402
    ROSTER_SWEEP,
    Diagnosis,
    FillTheRound,
    Instrumented,
    diagnose,
    measure,
    with_roster,
    with_weights,
    without_the_gate,
)

CONFIG = load_config(REPO / "config")
SEEDS = (0, 1)


@pytest.fixture(scope="module")
def found() -> Diagnosis:
    return diagnose(seeds=SEEDS, config=CONFIG)


class TestItReproduces:
    def test_the_same_seeds_twice_give_the_same_diagnosis(self, found: Diagnosis) -> None:
        assert found == diagnose(seeds=SEEDS, config=CONFIG)

    def test_the_shipped_3c_agrees_with_the_committed_comparison(self, found: Diagnosis) -> None:
        """The diagnosis must be diagnosing the table it claims to.

        Same scenario, same seeds, same cell - the shipped layout at arrival
        1.0 - reached through `compare()` rather than through this script's own
        `measure`. If these two ever disagree, one of the harnesses has drifted
        and every number in `diagnosis.md` is about a shift that is not the one
        in `comparison.csv`.
        """
        rows = compare(seeds=SEEDS, buffers=(None,), arrivals=(1.0,), config=CONFIG)
        theirs = [row for row in rows if row.policy.startswith("3C")]
        assert len(theirs) == len(SEEDS)
        assert sum(row.units_lost for row in theirs) / len(theirs) == pytest.approx(
            found.shipped.units_lost
        )


class TestTheAblationAblates:
    def test_the_gate_holds_nothing_while_it_is_removed(self) -> None:
        policy = GateAndScore(CONFIG)
        with without_the_gate():
            run(with_roster(LINE_A_ONE_SHIFT, 1), policy=policy, config=CONFIG, seed=0)
        assert policy.rounds, "the shift decided no rounds at all"
        assert policy.held == 0

    def test_the_gate_holds_something_when_it_is_not(self) -> None:
        """The other half, and the one that gives the test above its meaning: a
        shift where nothing was ever held would satisfy it for free. One
        technician, because since ADR-124 the shipped shift never holds."""
        policy = GateAndScore(CONFIG)
        run(with_roster(LINE_A_ONE_SHIFT, 1), policy=policy, config=CONFIG, seed=0)
        assert policy.held > 0

    def test_the_seam_is_restored_afterwards(self) -> None:
        with without_the_gate():
            pass
        policy = GateAndScore(CONFIG)
        run(with_roster(LINE_A_ONE_SHIFT, 1), policy=policy, config=CONFIG, seed=0)
        assert policy.held > 0


class TestFillTheRoundIsAFairInstrument:
    def test_nobody_starts_two_machines_at_once(self) -> None:
        """ADR-047. The generous adapter is only a fair comparison while it still
        describes a shift that could have happened."""
        result = run(LINE_A_ONE_SHIFT, policy=FillTheRound(CONFIG), config=CONFIG, seed=0)
        spans: dict[UserId, list[tuple[datetime, datetime | None]]] = defaultdict(list)
        for ticket in result.tickets:
            if ticket.started_at is None:
                continue
            for user in ticket.users:
                spans[user].append((ticket.started_at, ticket.finished_at))

        for person, worked in spans.items():
            worked.sort()
            for earlier, later in pairwise(worked):
                ended = earlier[1]
                assert ended is not None, f"{person} started another job without finishing one"
                assert ended <= later[0], f"{person} was on two machines at once"

    def test_it_starts_at_least_as_much_as_the_shipped_adapter(self) -> None:
        """It exists to be the generous version. If it ever started less, it
        would be pricing something other than the rule it lifts."""
        shipped = measure(lambda: GateAndScore(CONFIG), config=CONFIG, seeds=SEEDS)
        filled = measure(lambda: FillTheRound(CONFIG), config=CONFIG, seeds=SEEDS)
        assert filled.unfinished <= shipped.unfinished


class TestInstrumentingChangesNothing:
    def test_the_counted_run_is_the_same_run(self) -> None:
        """`Instrumented` subclasses the shipped adapter to count what it drops.
        If counting moved a single placement, the accounting would be of a
        policy nobody is comparing."""
        plain = run(LINE_A_ONE_SHIFT, policy=GateAndScore(CONFIG), config=CONFIG, seed=0)
        counted = run(LINE_A_ONE_SHIFT, policy=Instrumented(CONFIG), config=CONFIG, seed=0)
        assert plain.outages == counted.outages
        assert plain.tickets == counted.tickets

    def test_it_counts_the_drops_it_claims_to(self, found: Diagnosis) -> None:
        books = found.books
        assert books.rounds > 0
        assert books.placements_started <= books.placements_produced
        assert books.rounds_that_dropped_while_idle <= books.rounds_that_dropped
        assert books.rounds_that_held_while_idle <= books.rounds_that_held


class TestTheSweepsMoveOnlyWhatTheySay:
    def test_a_weight_variant_leaves_the_loaded_configuration_alone(self) -> None:
        """The sweeps build throwaway configurations. Issue #27 put tuning out
        of scope, and a sweep that mutated the loaded config would be tuning
        every measurement taken after it."""
        before = CONFIG.policy.weights.model_copy(deep=True)
        variant = with_weights(CONFIG, waiting=30.0, downtime=0.0)
        assert CONFIG.policy.weights == before
        assert variant.policy.weights.waiting == 30.0
        assert variant.policy.weights.downtime == 0.0

    def test_only_the_named_weight_moves(self) -> None:
        variant = with_weights(CONFIG, waiting=3.0)
        assert variant.policy.weights.severity == CONFIG.policy.weights.severity
        assert variant.policy.weights.downtime == CONFIG.policy.weights.downtime
        assert variant.policy.weights.skill_match == CONFIG.policy.weights.skill_match
        assert variant.policy.weights.eta_urgency == CONFIG.policy.weights.eta_urgency

    def test_the_shipped_weight_is_in_the_waiting_sweep(self, found: Diagnosis) -> None:
        """A sweep that stepped over the value the system actually runs on could
        not be read against the committed table."""
        weights = [weight for weight, _ in found.waiting_sweep]
        assert CONFIG.policy.weights.waiting in weights


class TestTheRosterAxis:
    def test_it_builds_the_roster_it_was_asked_for(self) -> None:
        bigger = with_roster(LINE_A_ONE_SHIFT, 8)
        assert len(bigger.technicians) == 8
        assert len(bigger.assignments) == 8
        assert {one.user for one in bigger.technicians} == {
            one.technician for one in bigger.assignments
        }

    def test_it_moves_headcount_and_nothing_else(self) -> None:
        """A roster sweep that also changed the arrivals or the minutes each
        person has would not be a roster sweep."""
        bigger = with_roster(LINE_A_ONE_SHIFT, 8)
        assert bigger.windows == LINE_A_ONE_SHIFT.windows
        assert bigger.duration == LINE_A_ONE_SHIFT.duration
        assert bigger.round_interval == LINE_A_ONE_SHIFT.round_interval
        assert {one.available_minutes for one in bigger.assignments} == {
            one.available_minutes for one in LINE_A_ONE_SHIFT.assignments
        }
        assert {one.skills for one in bigger.technicians} == {
            one.skills for one in LINE_A_ONE_SHIFT.technicians
        }

    def test_the_scenario_itself_is_left_alone(self) -> None:
        before = len(LINE_A_ONE_SHIFT.technicians)
        with_roster(LINE_A_ONE_SHIFT, 8)
        assert len(LINE_A_ONE_SHIFT.technicians) == before

    def test_the_shipped_roster_is_a_row_in_the_sweep(self) -> None:
        """Without it the table has no reference point and every figure in it
        would have to be read against a shift the system does not run."""
        assert len(LINE_A_ONE_SHIFT.technicians) in ROSTER_SWEEP

    def test_more_people_finish_more_work(self) -> None:
        """The axis has to bite, or a flat first column proves nothing."""
        thin = measure(
            lambda: GateAndScore(CONFIG),
            config=CONFIG,
            seeds=SEEDS,
            scenario=with_roster(LINE_A_ONE_SHIFT, 2),
        )
        thick = measure(
            lambda: GateAndScore(CONFIG),
            config=CONFIG,
            seeds=SEEDS,
            scenario=with_roster(LINE_A_ONE_SHIFT, 8),
        )
        assert thick.unfinished < thin.unfinished
        assert thick.response_minutes < thin.response_minutes


class TestTheMachineProfile:
    def test_it_accounts_for_every_ticket_the_run_raised(self, found: Diagnosis) -> None:
        raised = sum(one[2].tickets for one in found.machines)
        assert raised > 0
        assert all(one[2].tickets > 0 for one in found.machines)

    def test_waiting_and_repair_are_reported_separately(self, found: Diagnosis) -> None:
        """The split is the whole of section 4's argument: a station reached
        sooner whose downtime did not move is a different finding from a station
        nobody reached."""
        for _, under_fifo, under_gate in found.machines:
            assert under_fifo.waiting_minutes >= 0
            assert under_gate.waiting_minutes >= 0
            assert under_gate.repair_minutes > 0

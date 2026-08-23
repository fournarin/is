"""Loop 2 against rules of known outcome history (ADR-022, ADR-067).

The refusals are the point here even more than they were for Loop 1. This loop
proposes a number layer 1 then fires on, and every one of its six ways of saying
nothing means something a reviewer would act on differently: a safety-linked rule
it may never touch, a rule with too little history, a rule the evidence says is
fine, a rule that has never caught anything, two populations no threshold
separates, and a cap that cannot reach.

The arithmetic is checked against readings written out by hand rather than
against the module's own output. A test that agreed with the code would prove the
code is consistent with itself, and what has to be true here is stronger: that no
proposal ever silences an order where a technician found a fault.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from pdm.contracts import FindingKind, RuleId, WorkOrderRef, WorkOutcome
from pdm.work.thresholds import (
    NoProposal,
    NoProposalCause,
    RuleFiring,
    ThresholdProposal,
    propose,
)

RULE = RuleId("R-motor-temp-high")
FAN = RuleId("R-fan-rpm-low")

# The two constants of ADR-067, repeated here rather than read from policy.yaml:
# a test that takes its expectations from the file it is checking moves whenever
# that file does, and stops being able to say the file changed.
FLOOR = 10
CAP = 0.10


def _firing(
    ref: str,
    value: float,
    *,
    outcome: WorkOutcome = WorkOutcome.FIXED,
    kind: FindingKind = FindingKind.DETECTED,
) -> RuleFiring:
    return RuleFiring(
        work_order_ref=WorkOrderRef(ref),
        outcome=outcome,
        value=value,
        finding_kind=kind,
    )


def _alarms(values: list[float], *, start: int = 1) -> list[RuleFiring]:
    return [
        _firing(f"WO-{start + i:06d}", value, outcome=WorkOutcome.NO_PROBLEM_FOUND)
        for i, value in enumerate(values)
    ]


def _faults(values: list[float], *, start: int = 100) -> list[RuleFiring]:
    return [_firing(f"WO-{start + i:06d}", value) for i, value in enumerate(values)]


def _propose(
    firings: list[RuleFiring],
    *,
    rule_id: RuleId = RULE,
    comparison: str = "above",
    current_threshold: float = 85.0,
    safety_critical: bool = False,
    min_observations: int = FLOOR,
    max_change_ratio: float = CAP,
) -> ThresholdProposal | NoProposal:
    return propose(
        firings,
        rule_id=rule_id,
        comparison=comparison,
        current_threshold=current_threshold,
        safety_critical=safety_critical,
        min_observations=min_observations,
        max_change_ratio=max_change_ratio,
    )


class TestWhatIsProposed:
    def test_the_threshold_moves_to_the_worst_false_alarm_below_the_mildest_fault(self) -> None:
        """Six alarms between 85.4 and 87.0, four faults from 92 upwards.

        87.0 is the highest reading nobody found anything at, and it sits below
        92.0, so a rule firing strictly above 87.0 misses all six alarms and
        keeps all four faults. Worked out by hand: the cap allows 85 + 8.5 = 93.5,
        which is further than the evidence asks for, so nothing is capped.
        """
        firings = _alarms([85.4, 85.9, 86.2, 86.6, 86.8, 87.0]) + _faults([92.0, 95.5, 99.0, 104.0])

        result = _propose(firings)

        assert isinstance(result, ThresholdProposal)
        assert result.proposed_threshold == 87.0
        assert result.separating_threshold == 87.0
        assert result.capped is False
        assert result.observations == 10
        assert result.false_alarms == 6
        assert result.faults_found == 4
        assert len(result.would_not_have_fired) == 6
        assert len(result.still_fires_on) == 4

    def test_no_order_that_found_a_fault_is_ever_silenced(self) -> None:
        """The property the construction exists for, asserted directly.

        Every reading behind an order where somebody found something must still
        be strictly past the proposed threshold. If this fails, the loop has
        proposed that a real fault stop being alerted.
        """
        faults = _faults([92.0, 95.5, 99.0, 104.0])
        result = _propose(_alarms([85.4, 85.9, 86.2, 86.6, 86.8, 87.0]) + faults)

        assert isinstance(result, ThresholdProposal)
        for fault in faults:
            assert fault.value > result.proposed_threshold
        assert set(result.still_fires_on) == {fault.work_order_ref for fault in faults}

    def test_a_below_rule_moves_the_other_way(self) -> None:
        """`fan_rpm below 1200`: it fires when the reading is too low.

        The alarms read between 1150 and 1195 and the faults down at 900 and
        below, so the tightest threshold that keeps the faults is 1150 - the
        lowest alarm - and the cap allows 1200 - 120 = 1080, which is further
        down than 1150. Not capped, and the direction is inverted throughout.
        """
        firings = _alarms([1195.0, 1180.0, 1165.0, 1150.0, 1190.0, 1172.0]) + _faults(
            [900.0, 850.0, 700.0, 400.0]
        )

        result = _propose(firings, rule_id=FAN, comparison="below", current_threshold=1200.0)

        assert isinstance(result, ThresholdProposal)
        assert result.proposed_threshold == 1150.0
        assert result.capped is False
        assert len(result.would_not_have_fired) == 6

    def test_the_cap_holds_the_move_to_a_tenth_of_the_threshold(self) -> None:
        """The evidence separates at 97.0; ten percent of 85 reaches 93.5 only.

        93.5 still excludes the four alarms that read below it and keeps all the
        faults, so a capped proposal is a real proposal - a smaller one - and the
        record has to show both numbers, or a reviewer cannot tell the loop wanted
        to move further than one cycle allows.
        """
        firings = _alarms([86.0, 90.0, 93.0, 97.0, 94.5, 95.0]) + _faults(
            [110.0, 115.0, 120.0, 130.0]
        )

        result = _propose(firings)

        assert isinstance(result, ThresholdProposal)
        assert result.proposed_threshold == pytest.approx(93.5)
        assert result.separating_threshold == 97.0
        assert result.capped is True
        # 86.0, 90.0 and 93.0 are under 93.5; 94.5, 95.0 and 97.0 are not.
        assert len(result.would_not_have_fired) == 3
        assert "at most 10%" in result.reason

    def test_a_reading_exactly_at_the_proposal_stops_firing(self) -> None:
        """`breaches` is strictly above, never at, so the boundary is inclusive.

        A threshold set to the worst alarm's own reading excludes that alarm.
        Getting this wrong by one comparison would leave the alarm the proposal
        was built from still firing.
        """
        worst = 87.0
        firings = _alarms([85.4, 85.9, 86.2, 86.6, 86.8, worst]) + _faults(
            [92.0, 95.5, 99.0, 104.0]
        )

        result = _propose(firings)

        assert isinstance(result, ThresholdProposal)
        assert result.proposed_threshold == worst
        assert WorkOrderRef("WO-000006") in result.would_not_have_fired


class TestWhenNothingIsProposed:
    def test_a_safety_linked_rule_is_refused_whatever_the_count(self) -> None:
        """ADR-022, and it is checked before the floor for a reason.

        A safety rule with a hundred false alarms behind it must produce the same
        answer as one with none: not "not yet", but never.
        """
        firings = _alarms([1.0] * 40, start=1) + _faults([0.0] * 40)

        result = _propose(firings, comparison="below", current_threshold=1.0, safety_critical=True)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.SAFETY_CRITICAL
        assert "ADR-022" in result.reason

    def test_below_the_floor_nothing_is_proposed(self) -> None:
        """Nine orders where the separation is obvious. Still nothing."""
        firings = _alarms([85.4, 85.9, 86.2, 86.6, 87.0]) + _faults([92.0, 95.5, 99.0, 104.0])
        assert len(firings) == FLOOR - 1

        result = _propose(firings)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.BELOW_FLOOR
        assert result.observations == FLOOR - 1

    def test_the_floor_is_not_the_estimate_loops_floor(self) -> None:
        """ADR-066's five is not enough here, and ADR-067 says why.

        Written as a test rather than left to the ADR because the two numbers
        live in the same file and the tempting edit is to make them one.
        """
        firings = _alarms([85.4, 86.0, 87.0]) + _faults([92.0, 95.5, 99.0])
        assert len(firings) > 5

        result = _propose(firings)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.BELOW_FLOOR

    def test_no_false_alarms_is_an_answer_and_not_a_silence(self) -> None:
        """Ten orders, every one of them a real fault. Nothing says loosen it."""
        result = _propose(_faults([92.0, 95.5, 99.0, 104.0, 91.0, 93.0, 96.0, 97.0, 101.0, 110.0]))

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.NO_FALSE_ALARMS
        assert result.false_alarms == 0

    def test_a_rule_that_has_never_caught_anything_gets_no_proposal(self) -> None:
        """Twelve false alarms and not one fault - the case the loop refuses.

        A threshold past all twelve would silence the rule, and the honest answer
        is that nothing has ever shown this rule catching a fault, which is a
        better question for an engineer than a number (ADR-067).
        """
        result = _propose(_alarms([86.0, 87.0, 88.0, 89.0, 90.0, 91.0] * 2))

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.NO_CONFIRMED_FAULT
        assert result.faults_found == 0

    def test_overlapping_populations_produce_no_threshold(self) -> None:
        """Every false alarm read hotter than the mildest real fault.

        No threshold separates them. The proposal a percentage would have made
        here is the one that silences a fault, which is exactly what a
        percentage cannot see.
        """
        firings = _alarms([95.0, 97.0, 99.0, 101.0, 103.0, 105.0]) + _faults(
            [90.0, 91.0, 93.0, 94.0]
        )

        result = _propose(firings)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.NO_SEPARATING_THRESHOLD

    def test_a_cap_that_reaches_nothing_proposes_nothing(self) -> None:
        """The separation is at 97.0 and every alarm sits above 93.5.

        A proposal of 93.5 would exclude none of them, so it is not a smaller
        version of the answer - it is a threshold moved for nothing.
        """
        firings = _alarms([94.0, 95.0, 96.0, 96.5, 97.0, 96.8]) + _faults(
            [110.0, 115.0, 120.0, 130.0]
        )

        result = _propose(firings)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.CAP_EXCLUDES_NOTHING
        assert "separates at 97.0" in result.reason


class TestWhatIsNotEvidence:
    def test_a_predicted_finding_is_set_aside_and_counted(self) -> None:
        """A forecast that came to nothing is evidence about the trend fit.

        Six predicted false alarms are dropped from the set, which puts the rule
        below the floor - the proposal they would otherwise have carried is one
        made about the wrong number entirely (ADR-043, ADR-067 section 2).
        """
        firings = (
            _alarms([85.4, 85.9, 86.2, 86.6, 87.0])
            + _faults([92.0, 95.5, 99.0, 104.0])
            + [
                _firing(
                    f"WO-{200 + i:06d}",
                    86.0,
                    outcome=WorkOutcome.NO_PROBLEM_FOUND,
                    kind=FindingKind.PREDICTED,
                )
                for i in range(6)
            ]
        )

        result = _propose(firings)

        assert isinstance(result, NoProposal)
        assert result.cause is NoProposalCause.BELOW_FLOOR
        assert result.observations == 9
        assert result.excluded_predictions == 6

    def test_every_outcome_that_is_not_no_problem_found_is_a_fault(self) -> None:
        """A temporary fix and a job left unfixed are both readings to keep firing on.

        Only `no_problem_found` says the rule was wrong. "Not fixed" says the
        opposite: somebody went, found something, and could not finish it.
        """
        faults = [
            _firing("WO-000100", 92.0, outcome=WorkOutcome.TEMPORARY_FIX),
            _firing("WO-000101", 95.0, outcome=WorkOutcome.NOT_FIXED),
            _firing("WO-000102", 99.0, outcome=WorkOutcome.FIXED),
            _firing("WO-000103", 104.0, outcome=WorkOutcome.FIXED),
        ]
        result = _propose(_alarms([85.4, 85.9, 86.2, 86.6, 86.8, 87.0]) + faults)

        assert isinstance(result, ThresholdProposal)
        assert result.faults_found == 4
        assert result.proposed_threshold == 87.0


class TestWhatTheProposalCarries:
    def test_every_proposal_states_that_its_evidence_is_one_sided(self) -> None:
        """The caveat is on the record, not only in the ADR (ADR-067 section 6).

        It is read by somebody looking at a number rather than by somebody reading
        decision records, and this is the assertion that keeps it there.
        """
        result = _propose(
            _alarms([85.4, 85.9, 86.2, 86.6, 86.8, 87.0]) + _faults([92.0, 95.5, 99.0, 104.0])
        )

        assert isinstance(result, ThresholdProposal)
        assert "would have missed" in result.limitation
        assert "peak of the excursion" in result.limitation

    def test_the_reason_names_both_halves_of_the_trade(self) -> None:
        result = _propose(
            _alarms([85.4, 85.9, 86.2, 86.6, 86.8, 87.0]) + _faults([92.0, 95.5, 99.0, 104.0])
        )

        assert isinstance(result, ThresholdProposal)
        assert "found nothing wrong" in result.reason
        assert "still fires on all 4" in result.reason

    def test_a_comparison_that_is_neither_is_refused(self) -> None:
        with pytest.raises(ValueError, match="above or below"):
            _propose(_faults([1.0]), comparison="equals")


class TestNothingWritesAThreshold:
    def test_no_path_in_this_module_reaches_the_rules_file(self) -> None:
        """ADR-022's shape, checked structurally rather than by reading.

        `lint-imports` keeps a connection out of this module; this keeps the
        rules file out of it too. A loop that could import the config layer could
        be a loop that writes the threshold it just proposed.
        """
        source = (Path(__file__).parents[2] / "src/pdm/work/thresholds.py").read_text()

        assert "rules.yaml" not in source
        assert "platform.config" not in source
        assert "open(" not in source

    def test_the_rules_file_still_says_what_the_tests_assume(self) -> None:
        """The safety flag ADR-022's prohibition acts on has to exist.

        Not an assertion about the arithmetic: an assertion that the input the
        prohibition reads is still there. A rules file that lost `safety_critical`
        would leave `propose` reading a default of False for the interlock rule.
        """
        rules = yaml.safe_load((Path(__file__).parents[2] / "config/rules.yaml").read_text())
        interlock = next(r for r in rules["rules"] if r["rule_id"] == "R-safety-interlock-open")

        assert interlock["safety_critical"] is True

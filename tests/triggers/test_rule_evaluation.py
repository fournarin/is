"""What fires, what does not, and what must fire anyway (ADR-023, ADR-042).

No database and no clock: everything the engine needs is an argument, which is
why the combinations that matter are a line each. The one worth reading twice is
`TestSuppressionDuringRepair::test_a_higher_severity_rule_fires_anyway` - a
technician is inside the machine and the interlock alarm is the one that must
not be swallowed.

The rules here are the shipped ones from `config/rules.yaml`, not fixtures. A
test that invented its own thresholds would pass on a rule set nobody runs.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingStatus,
    MachineId,
    MachineModel,
    RuleId,
    Severity,
    Signal,
    SymptomCode,
)
from pdm.platform.config import load_config
from pdm.platform.config.schema import RuleConfig
from pdm.triggers.domain import Debounce, Decision, Outcome, breaches, evaluate

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-001")
INTERLOCK_MACHINE = MachineId("MC-012")

CONFIG = load_config(Path("config"))
RULES = list(CONFIG.rules.rules)


def _rule(rule_id: str) -> RuleConfig:
    for rule in RULES:
        if rule.rule_id == rule_id:
            return rule
    raise AssertionError(f"{rule_id} is not in config/rules.yaml")


MOTOR_TEMP = _rule("R-motor-temp-high")
INTERLOCK = _rule("R-safety-interlock-open")


def _signal(value: float, *, at: datetime = NOW, metric: str = "motor_temp_c") -> Signal:
    return Signal(
        timestamp=at,
        machine_id=MOTOR if metric != "interlock_closed" else INTERLOCK_MACHINE,
        metric_name=metric,
        value=value,
        unit="C" if metric == "motor_temp_c" else "",
    )


def _sustain(
    debounce: Debounce,
    *,
    seconds: int,
    metric: str = "motor_temp_c",
    rule: RuleConfig | None = None,
    value: float = 91.0,
    step: int = 60,
    now_offset: timedelta = timedelta(0),
    **kwargs: Any,
) -> list[Decision]:
    """Feed the excess forward in steps the rule cannot mistake for a gap.

    Sampling once and then again three minutes later is not two minutes of
    sustained excess - it is two readings with a hole between them, and the
    debounce now says so. Every test that wants a rule to fire has to actually
    hold the value there.
    """
    watched = rule or MOTOR_TEMP
    decisions: list[Decision] = []
    for elapsed in range(0, seconds + 1, step):
        at = NOW + timedelta(seconds=elapsed)
        decisions = evaluate(
            _signal(value, at=at, metric=metric),
            [watched],
            now=at + now_offset,
            debounce=debounce,
            **kwargs,
        )
    return decisions


def _open_finding(rule_id: str, machine: MachineId = MOTOR) -> Finding:
    return Finding(
        machine_id=machine,
        component=ComponentLabel("belt_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=Severity.HIGH,
        rule_id=RuleId(rule_id),
        detected_at=NOW,
        evidence={"value": 91.0},
        status=FindingStatus.OPEN,
    )


class TestTheThresholdItself:
    def test_a_value_past_the_threshold_breaches(self) -> None:
        assert breaches(_signal(91.0), MOTOR_TEMP) is True

    def test_a_value_exactly_at_the_threshold_does_not(self) -> None:
        """Strict on both sides. An interlock rule reading "below 1.0" firing on
        a healthy interlock sitting at 1.0 would fire for ever on a machine that
        is perfectly well (ADR-032)."""
        assert breaches(_signal(85.0), MOTOR_TEMP) is False

    def test_a_rule_watching_another_metric_is_not_consulted(self) -> None:
        decisions = evaluate(
            _signal(0.0, metric="hydraulic_pressure_bar"),
            RULES,
            now=NOW,
            debounce=Debounce(),
        )

        assert [decision.rule_id for decision in decisions] == []


class TestSustainedExcess:
    """`for_seconds` means continuously, which is the whole of the debounce."""

    def test_one_hot_sample_is_not_a_finding(self) -> None:
        decisions = evaluate(_signal(91.0), [MOTOR_TEMP], now=NOW, debounce=Debounce())

        assert [decision.outcome for decision in decisions] == [Outcome.QUIET]
        assert "of the 120s" in decisions[0].why

    def test_two_minutes_of_it_is(self) -> None:
        debounce = Debounce()
        evaluate(_signal(91.0), [MOTOR_TEMP], now=NOW, debounce=debounce)

        later = evaluate(
            _signal(92.0, at=NOW + timedelta(seconds=120)),
            [MOTOR_TEMP],
            now=NOW + timedelta(seconds=120),
            debounce=debounce,
        )

        assert later[0].outcome is Outcome.RAISE
        assert later[0].finding is not None

    def test_a_value_that_returns_to_normal_restarts_the_clock(self) -> None:
        """Otherwise a machine that crossed the threshold once at breakfast and
        once at lunch would look like two hours of sustained excess."""
        debounce = Debounce()
        evaluate(_signal(91.0), [MOTOR_TEMP], now=NOW, debounce=debounce)
        evaluate(
            _signal(70.0, at=NOW + timedelta(seconds=60)),
            [MOTOR_TEMP],
            now=NOW + timedelta(seconds=60),
            debounce=debounce,
        )

        decisions = evaluate(
            _signal(91.0, at=NOW + timedelta(seconds=180)),
            [MOTOR_TEMP],
            now=NOW + timedelta(seconds=180),
            debounce=debounce,
        )

        assert decisions[0].outcome is Outcome.QUIET

    def test_the_debounce_measures_source_time_not_decision_time(self) -> None:
        """ADR-028's two axes. The question is how long the machine has been
        hot, which is a fact about the plant, not about when we looked."""
        decisions = _sustain(Debounce(), seconds=180, now_offset=timedelta(hours=5))

        assert decisions[0].outcome is Outcome.RAISE


class TestInvariantEight:
    """One rule firing repeatedly is one Finding (ADR-023 section 2).

    Left alone, one overheating motor raises a Finding on every reading, becomes
    a hundred work orders within an hour, load_ratio passes 100%, and the gate
    holds back everything. The system destroys itself in its first hour on real
    data.
    """

    def test_a_hundred_firings_produce_one_raise_and_ninety_nine_repeats(self) -> None:
        debounce = Debounce()
        open_findings: dict[tuple[MachineId, RuleId], Finding] = {}
        outcomes = []

        for index in range(100):
            at = NOW + timedelta(seconds=120 + index * 60)
            decisions = evaluate(
                _signal(91.0 + index * 0.1, at=at),
                [MOTOR_TEMP],
                now=at,
                debounce=debounce,
                open_findings=open_findings,
            )
            outcome = decisions[0].outcome
            outcomes.append(outcome)
            if outcome is Outcome.RAISE:
                # What the service does with a RAISE: the record now exists, so
                # the next firing is a repeat.
                open_findings[(MOTOR, RuleId("R-motor-temp-high"))] = _open_finding(
                    "R-motor-temp-high"
                )

        assert outcomes.count(Outcome.RAISE) == 1
        # Two quiet ones first: the debounce starts at the first hot sample, so
        # two minutes of excess is reached on the third.
        assert outcomes.count(Outcome.QUIET) == 2
        assert outcomes.count(Outcome.REPEAT) == 97
        assert outcomes[0] is Outcome.QUIET

    def test_an_acknowledged_finding_suppresses_just_as_an_open_one_does(self) -> None:
        """A person having seen it does not mean it stopped happening."""
        acknowledged = _open_finding("R-motor-temp-high").model_copy(
            update={"status": FindingStatus.ACKNOWLEDGED}
        )

        decisions = _sustain(
            Debounce(),
            seconds=180,
            open_findings={(MOTOR, RuleId("R-motor-temp-high")): acknowledged},
        )

        assert decisions[0].outcome is Outcome.REPEAT


class TestTheCooldown:
    """ADR-023 section 3: a sensor oscillating across its threshold."""

    def test_a_resolved_finding_holds_the_rule_off_for_the_cooldown(self) -> None:
        decisions = _sustain(
            Debounce(),
            seconds=180,
            resolved_at={(MOTOR, RuleId("R-motor-temp-high")): NOW},
            cooldown=timedelta(minutes=30),
        )

        assert decisions[0].outcome is Outcome.IN_COOLDOWN

    def test_and_lets_it_through_once_the_cooldown_has_passed(self) -> None:
        decisions = _sustain(
            Debounce(),
            seconds=180,
            now_offset=timedelta(minutes=45),
            resolved_at={(MOTOR, RuleId("R-motor-temp-high")): NOW},
            cooldown=timedelta(minutes=30),
        )

        assert decisions[0].outcome is Outcome.RAISE


class TestSuppressionDuringRepair:
    """Invariant 9, and the paragraph of ADR-023 that exists to keep somebody
    alive."""

    def test_the_rule_that_produced_the_repair_is_suppressed(self) -> None:
        decisions = _sustain(
            Debounce(), seconds=180, under_repair={MOTOR: frozenset({MOTOR_TEMP.rule_id})}
        )

        assert decisions[0].outcome is Outcome.SUPPRESSED

    def test_a_higher_severity_rule_fires_anyway(self) -> None:
        """The interlock fails while the machine is being repaired.

        A technician is inside it. Blanket suppression - "this machine is under
        repair, be quiet" - is how that person is not told (ADR-023 section 5).

        Suppression is keyed by *rule*, so this needs no severity comparison at
        all: the interlock rule is not the rule under repair, so it was never
        suppressed. The first version of this code compared severities instead
        and would have swallowed a critical alarm on a machine under repair for
        a critical fault.
        """
        debounce = Debounce()
        evaluate(
            _signal(0.0, at=NOW, metric="interlock_closed"),
            [INTERLOCK],
            now=NOW,
            debounce=debounce,
        )

        decisions = evaluate(
            _signal(0.0, at=NOW + timedelta(seconds=200), metric="interlock_closed"),
            [INTERLOCK],
            now=NOW + timedelta(seconds=200),
            debounce=debounce,
            under_repair={INTERLOCK_MACHINE: frozenset({MOTOR_TEMP.rule_id})},
        )

        assert INTERLOCK.severity is Severity.CRITICAL
        assert decisions[0].outcome is Outcome.RAISE

    def test_another_rule_on_the_same_machine_is_not_suppressed(self) -> None:
        """Suppression follows the rule, not the machine (ADR-023 section 4).

        A motor being rebuilt says nothing about whether the interlock still
        works, and the reading that says it does not is the one that has to get
        through. Written as a severity comparison first, this would have
        swallowed a critical alarm on a machine under repair for a critical
        fault - the failure ADR-023 was written to prevent.
        """
        decisions = _sustain(
            Debounce(),
            seconds=180,
            metric="interlock_closed",
            rule=INTERLOCK,
            value=0.0,
            under_repair={INTERLOCK_MACHINE: frozenset({MOTOR_TEMP.rule_id})},
        )

        assert decisions[0].outcome is Outcome.RAISE

    def test_a_repair_on_another_machine_suppresses_nothing(self) -> None:
        debounce = Debounce()

        decisions = _sustain(
            debounce,
            seconds=180,
            under_repair={MachineId("MC-999"): frozenset({MOTOR_TEMP.rule_id})},
        )

        assert decisions[0].outcome is Outcome.RAISE


class TestWhatARaisedFindingCarries:
    def test_the_component_comes_from_the_rule_and_is_never_inferred(self) -> None:
        """ADR-009. One signal tag maps to one component, declared by the person
        who wrote the rule."""
        decisions = _sustain(Debounce(), seconds=180)

        finding = decisions[0].finding
        assert finding is not None
        assert finding.component == MOTOR_TEMP.component
        assert finding.symptom_code == MOTOR_TEMP.symptom_code

    def test_the_evidence_holds_the_numbers_the_ticket_will_quote(self) -> None:
        """Recorded now, because by the time anybody reads the ticket the signal
        stream has moved on and "why did this fire" would be answered about a
        different moment (ADR-042 section 5)."""
        decisions = _sustain(Debounce(), seconds=180, value=93.5)

        finding = decisions[0].finding
        assert finding is not None
        assert finding.evidence["value"] == 93.5
        assert finding.evidence["threshold"] == 85.0
        assert finding.evidence["held_for_seconds"] == 180
        # Four readings, not one: "above the threshold for three minutes" means
        # something different on one sample than on four, and the difference is
        # whether anybody was watching.
        assert finding.evidence["samples"] == 4

    def test_detected_at_is_decision_time_not_source_time(self) -> None:
        """The two axes again: when the system decided, not when the sensor was
        read (ADR-028)."""
        debounce = Debounce()
        decided = NOW + timedelta(hours=3)
        for elapsed in (0, 60, 120):
            evaluate(
                _signal(91.0, at=NOW + timedelta(seconds=elapsed)),
                [MOTOR_TEMP],
                now=decided,
                debounce=debounce,
            )
        decisions = evaluate(
            _signal(91.0, at=NOW + timedelta(seconds=180)),
            [MOTOR_TEMP],
            now=decided,
            debounce=debounce,
        )

        finding = decisions[0].finding
        assert finding is not None
        assert finding.detected_at == decided


class TestTheDecisionExplainsItself:
    @pytest.mark.parametrize(
        "outcome",
        [Outcome.QUIET, Outcome.REPEAT, Outcome.SUPPRESSED, Outcome.IN_COOLDOWN, Outcome.RAISE],
    )
    def test_every_outcome_carries_a_sentence(self, outcome: Outcome) -> None:
        """ "Suppressed" and "in cooldown" look identical from outside and mean
        different things - one is a machine somebody is working on, the other is
        a sensor crossing its threshold repeatedly - and a loop that logged only
        the verdict would make a false-alarm problem indistinguishable from a
        busy shift."""
        key = (MOTOR, RuleId("R-motor-temp-high"))
        at = NOW + timedelta(seconds=180)

        by_outcome: dict[Outcome, dict[str, Any]] = {
            Outcome.QUIET: {},
            Outcome.REPEAT: {"open_findings": {key: _open_finding("R-motor-temp-high")}},
            Outcome.SUPPRESSED: {"under_repair": {MOTOR: frozenset({MOTOR_TEMP.rule_id})}},
            Outcome.IN_COOLDOWN: {"resolved_at": {key: at}},
            Outcome.RAISE: {},
        }

        if outcome is Outcome.QUIET:
            decisions = evaluate(_signal(91.0), [MOTOR_TEMP], now=NOW, debounce=Debounce())
        else:
            decisions = _sustain(Debounce(), seconds=180, **by_outcome[outcome])

        assert decisions[0].outcome is outcome
        assert len(decisions[0].why) > 20


class TestWhatTheCodeReviewFound:
    """Three of them changed what the engine does. The first changed an ADR."""

    def test_a_rule_does_not_fire_on_another_machine_model(self) -> None:
        """`config/rules.yaml` declares a model per rule and the same tag exists
        on several. Firing across them produces a symptom code with no playbook
        for that machine, and a threshold belonging to a different one."""
        m710 = MachineModel("M-710iC")

        decisions = _sustain(Debounce(), seconds=180, machine_model=m710)

        assert MOTOR_TEMP.machine_model == MachineModel("R-2000iC")
        assert decisions == []

    def test_a_gap_in_the_stream_ends_the_run(self) -> None:
        """One hot reading after an outage is not an outage of sustained heat.

        Without this the Finding would carry evidence saying the excess held for
        three hours - a claim about a machine nobody was watching.
        """
        debounce = Debounce()
        _sustain(debounce, seconds=60)

        decisions = evaluate(
            _signal(91.0, at=NOW + timedelta(hours=3)),
            [MOTOR_TEMP],
            now=NOW + timedelta(hours=3),
            debounce=debounce,
        )

        assert decisions[0].outcome is Outcome.QUIET
        assert "0s of the 120s" in decisions[0].why

    def test_a_gap_inside_the_rules_own_window_does_not(self) -> None:
        """The yardstick is the rule's `for_seconds`, so no new number was
        introduced to draw this line."""
        debounce = Debounce()
        evaluate(_signal(91.0, at=NOW), [MOTOR_TEMP], now=NOW, debounce=debounce)

        decisions = evaluate(
            _signal(91.0, at=NOW + timedelta(seconds=119)),
            [MOTOR_TEMP],
            now=NOW + timedelta(seconds=119),
            debounce=debounce,
        )

        assert decisions[0].outcome is Outcome.QUIET
        assert "119s of the 120s" in decisions[0].why

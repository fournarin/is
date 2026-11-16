"""Rules over signals. Pure, no I/O, no clock of its own (ADR-042).

Everything this needs is an argument: the signal, the rules, what is already
open, what is under repair, and the time the caller read from the `Clock`. It
returns what should happen and does none of it.

**That is here for the safety case.** ADR-023's most important paragraph says a
machine under repair suppresses the rule that produced the repair and never a
rule of higher severity - because blanket suppression is how a technician inside
a machine has the interlock alarm swallowed. A function that fetched its own
state could only be tested by building that world in a database; this one is
tested in a line each, in every combination.

The sustained-excess window is the one piece of memory, and it belongs to the
caller: `Debounce` is a plain object the loop keeps between signals and a restart
forgets, which costs one Finding raised up to `for_seconds` late, once, after a
deploy (ADR-042 section 1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    Finding,
    FindingKind,
    FindingStatus,
    MachineId,
    MachineModel,
    RuleId,
    Signal,
    SymptomCode,
)
from pdm.platform.config.schema import RuleConfig
from pdm.triggers import trend

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Read-only empty defaults. A bare `{}` in a signature is one object shared by
# every call, and this function is called once per signal per rule: a caller that
# ever wrote to it would be writing to everybody's.
_NO_FINDINGS: Mapping[tuple[MachineId, RuleId], Finding] = MappingProxyType({})
_NO_TIMES: Mapping[tuple[MachineId, RuleId], datetime] = MappingProxyType({})
_NO_REPAIRS: Mapping[MachineId, frozenset[RuleId]] = MappingProxyType({})

# The suppression key of ADR-023: while an open or acknowledged Finding exists
# for this pair, a repeat firing updates it rather than creating another.
SuppressionKey = tuple[MachineId, RuleId]


class Outcome(StrEnum):
    """What the caller should do with the signal it just handed over."""

    # Nothing fired, or the excess has not lasted long enough yet.
    QUIET = "quiet"
    # A new Finding, to be written.
    RAISE = "raise"
    # A new *predicted* Finding: the trend says this will breach (ADR-020).
    FORECAST = "forecast"
    # The same condition again: raise occurrence_count, move last_seen_at.
    REPEAT = "repeat"
    # Suppressed by an open Finding on a machine under repair for this rule.
    SUPPRESSED = "suppressed"
    # Inside the cooldown after a resolved Finding: an oscillating sensor.
    IN_COOLDOWN = "in_cooldown"


class Decision(BaseModel):
    """What the engine concluded about one signal against one rule.

    Carries the reason as well as the verdict. "Suppressed" and "in cooldown"
    look identical from outside and mean different things - one is a machine
    somebody is already working on, the other is a sensor crossing its threshold
    repeatedly - and a loop that logged only the verdict would make a false-alarm
    problem indistinguishable from a busy shift.
    """

    model_config = _FROZEN

    outcome: Outcome
    rule_id: RuleId
    machine_id: MachineId
    why: str = Field(min_length=1)
    finding: Finding | None = None


class Run(BaseModel):
    """An unbroken run of breaching samples: when it started, and how many."""

    model_config = ConfigDict(frozen=True)

    since: datetime
    last_seen: datetime
    samples: int = Field(ge=1)


class Debounce:
    """How long the excess has held, per (machine, rule). Mutable on purpose.

    The one piece of state in layer 1, held by the loop rather than by the
    evaluation. A restart forgets it and the clock on a sustained excess starts
    again - which ADR-042 accepts, and writes down, because the alternative is a
    write per sample per rule for ever.

    It counts samples as well as elapsed time, and **a gap ends the run**. One
    hot reading after a three-hour outage is not three hours of sustained
    excess: without the gap check the Finding it raised would carry evidence
    saying `held_for_seconds: 10800`, which is a claim about a machine nobody was
    watching.
    """

    __slots__ = ("_runs",)

    def __init__(self) -> None:
        self._runs: dict[SuppressionKey, Run] = {}

    def observe(self, key: SuppressionKey, at: datetime, *, max_gap: timedelta) -> Run:
        """Extend the run, or start a new one if the stream went quiet."""
        current = self._runs.get(key)
        if current is None or at - current.last_seen > max_gap or at < current.since:
            run = Run(since=at, last_seen=at, samples=1)
        else:
            run = Run(since=current.since, last_seen=at, samples=current.samples + 1)
        self._runs[key] = run
        return run

    def clear(self, key: SuppressionKey) -> None:
        """The value came back inside the threshold: the run is over.

        Called on every signal that does not breach, which is what makes
        `for_seconds` mean "continuously" rather than "at some point in the last
        few minutes".
        """
        self._runs.pop(key, None)

    def __contains__(self, key: object) -> bool:
        return key in self._runs


def breaches(signal: Signal, rule: RuleConfig) -> bool:
    """Strictly above or strictly below. Never equal.

    An interlock rule reading "below 1.0" must not fire on a healthy interlock
    sitting at exactly 1.0, which is what slice 2 found when `time_until` had to
    take a direction (ADR-032).
    """
    if rule.comparison == "above":
        return signal.value > rule.threshold
    return signal.value < rule.threshold


def evidence_for(
    signal: Signal, rule: RuleConfig, *, held_for: timedelta, samples: int = 1
) -> dict[str, object]:
    """The numbers the ticket's sentence will be built from (ADR-042 section 5).

    Recorded now because the signal stream has moved on by the time anybody
    reads the ticket, and "why did this fire" answered from a live stream is
    answered about a different moment.
    """
    return {
        "value": signal.value,
        "unit": signal.unit,
        "threshold": rule.threshold,
        "comparison": rule.comparison,
        "metric_name": rule.metric_name,
        "held_for_seconds": int(held_for.total_seconds()),
        # How many readings that was. "Above the threshold for twenty minutes"
        # means something different on one sample than on twenty, and the
        # difference is whether anybody was watching (ADR-042 section 1).
        "samples": samples,
        "measured_at": signal.timestamp.isoformat(),
    }


def _suppressed_by_repair(
    rule: RuleConfig,
    under_repair: Mapping[MachineId, frozenset[RuleId]],
    machine_id: MachineId,
) -> bool:
    """ADR-023 section 4: **the rule under repair, and nothing else.**

    This was first written as a severity comparison - suppress any rule of equal
    or lower severity on a machine somebody is working on - and that is a
    different rule from the one the record states. It also fails in exactly the
    direction ADR-023 was written to prevent: a machine under repair for a
    critical fault would have suppressed the critical interlock rule, which is
    the alarm that says a technician inside the machine is in danger.

    Keyed by rule, ADR-023 section 5 needs no comparison at all: a rule of higher
    severity is a different rule, so it was never suppressed in the first place.
    """
    return rule.rule_id in under_repair.get(machine_id, frozenset())


def evaluate(
    signal: Signal,
    rules: Sequence[RuleConfig],
    *,
    machine_model: MachineModel | None = None,
    now: datetime,
    debounce: Debounce,
    open_findings: Mapping[SuppressionKey, Finding] = _NO_FINDINGS,
    resolved_at: Mapping[SuppressionKey, datetime] = _NO_TIMES,
    under_repair: Mapping[MachineId, frozenset[RuleId]] = _NO_REPAIRS,
    cooldown: timedelta = timedelta(minutes=30),
) -> list[Decision]:
    """One signal against every rule that watches its metric.

    `now` is decision time from the `Clock`; `signal.timestamp` is source time
    and they are not the same axis (ADR-028). The debounce measures duration in
    source time - it is asking how long the machine has been hot - while the
    cooldown and the Finding's own timestamps are decision time.
    """
    decisions: list[Decision] = []

    for rule in rules:
        if rule.metric_name != signal.metric_name:
            continue
        # A rule is declared for one machine model (config/rules.yaml) and the
        # same tag exists on several. Without this, the R-2000iC belt rule fires
        # on an M-710iC - producing a symptom code that has no playbook for that
        # model, and a threshold that belongs to a different machine.
        if machine_model is not None and rule.machine_model != machine_model:
            continue

        key: SuppressionKey = (signal.machine_id, rule.rule_id)

        if not breaches(signal, rule):
            debounce.clear(key)
            continue

        # A gap longer than the rule's own window ends the run: if nothing has
        # been heard for as long as the rule needs, continuity cannot be claimed.
        # No new constant - the rule states its own yardstick.
        run = debounce.observe(
            key,
            signal.timestamp,
            max_gap=timedelta(seconds=rule.for_seconds) if rule.for_seconds else timedelta.max,
        )
        held_for = signal.timestamp - run.since
        if held_for.total_seconds() < rule.for_seconds:
            decisions.append(
                Decision(
                    outcome=Outcome.QUIET,
                    rule_id=rule.rule_id,
                    machine_id=signal.machine_id,
                    why=(
                        f"{signal.metric_name} is past {rule.threshold} but has held for "
                        f"{int(held_for.total_seconds())}s of the {rule.for_seconds}s this rule "
                        "requires"
                    ),
                )
            )
            continue

        if key in open_findings:
            decisions.append(
                Decision(
                    outcome=Outcome.REPEAT,
                    rule_id=rule.rule_id,
                    machine_id=signal.machine_id,
                    why="the same rule on the same machine already has an open Finding (ADR-023)",
                )
            )
            continue

        if _suppressed_by_repair(rule, under_repair, signal.machine_id):
            decisions.append(
                Decision(
                    outcome=Outcome.SUPPRESSED,
                    rule_id=rule.rule_id,
                    machine_id=signal.machine_id,
                    why=(
                        f"{signal.machine_id} already has repair work open for "
                        f"{rule.rule_id}; another rule - including any of higher severity - "
                        "still fires (ADR-023)"
                    ),
                )
            )
            continue

        last_resolved = resolved_at.get(key)
        if last_resolved is not None and now - last_resolved < cooldown:
            decisions.append(
                Decision(
                    outcome=Outcome.IN_COOLDOWN,
                    rule_id=rule.rule_id,
                    machine_id=signal.machine_id,
                    why=(
                        f"resolved {int((now - last_resolved).total_seconds() // 60)} minutes ago "
                        f"and the cooldown is {int(cooldown.total_seconds() // 60)}; a sensor "
                        "oscillating across its threshold is one Finding, not a stream (ADR-023)"
                    ),
                )
            )
            continue

        decisions.append(
            Decision(
                outcome=Outcome.RAISE,
                rule_id=rule.rule_id,
                machine_id=signal.machine_id,
                why=(
                    f"{signal.metric_name} {rule.comparison} {rule.threshold} for "
                    f"{int(held_for.total_seconds())}s"
                ),
                finding=Finding(
                    machine_id=signal.machine_id,
                    # Declared by the rule, never inferred from the signal
                    # (ADR-009). A rule that cannot say which part it watches
                    # uses `unknown`, and layer 2 serves a diagnostic playbook.
                    component=rule.component,
                    symptom_code=rule.symptom_code,
                    severity=rule.severity,
                    rule_id=rule.rule_id,
                    detected_at=now,
                    evidence=evidence_for(signal, rule, held_for=held_for, samples=run.samples),
                    kind=FindingKind.DETECTED,
                    status=FindingStatus.OPEN,
                ),
            )
        )

    return decisions


def trend_rule_id(rule: RuleConfig) -> RuleId:
    """The rule id a forecast is filed under: `<rule_id>/trend` (ADR-043 §4).

    Distinct from the threshold rule's so that a prediction and the detection
    that supersedes it can both be live: they share a machine and a component,
    which is what ADR-023 section 7 matches on, but not the suppression key,
    which is what the unique index in migration 0007 enforces. Filed under the
    same id, the detection could not be written at all.
    """
    return RuleId(f"{rule.rule_id}/trend")


def forecast(
    signal: Signal,
    rules: Sequence[RuleConfig],
    *,
    machine_model: MachineModel | None = None,
    now: datetime,
    windows: trend.Window,
    open_findings: Mapping[SuppressionKey, Finding] = _NO_FINDINGS,
    resolved_at: Mapping[SuppressionKey, datetime] = _NO_TIMES,
    cooldown: timedelta = timedelta(minutes=30),
    horizon: timedelta,
    min_samples: int,
    eta_error: Sequence[tuple[float, float]] = (),
) -> list[Decision]:
    """What the trend says is coming, for the rules watching this signal.

    Separate from `evaluate` rather than folded into it, because the two answer
    different questions about the same reading - "is it wrong now" and "will it
    be" - and a single function returning both would make the suppression rules
    of one apply to the other by accident.

    Detection's suppression does not carry over: a machine under repair still
    gets forecasts, because the work in progress may not be the work the trend is
    predicting. What does carry over is invariant 8 - one live forecast per
    (machine, trend rule), updated rather than duplicated.
    """
    readings = windows.add(signal)
    decisions: list[Decision] = []

    for rule in rules:
        if rule.metric_name != signal.metric_name:
            continue
        if machine_model is not None and rule.machine_model != machine_model:
            continue

        rule_id = trend_rule_id(rule)
        key: SuppressionKey = (signal.machine_id, rule_id)

        found = trend.crossing(
            readings,
            threshold=rule.threshold,
            comparison=rule.comparison,
            now=signal.timestamp,
            horizon=horizon,
            min_samples=min_samples,
        )
        if found is None:
            continue

        if key in open_findings:
            decisions.append(
                Decision(
                    outcome=Outcome.REPEAT,
                    rule_id=rule_id,
                    machine_id=signal.machine_id,
                    why="the trend still predicts a crossing already forecast (ADR-023)",
                    finding=_predicted(signal, rule, rule_id, found, now=now, eta_error=eta_error),
                )
            )
            continue

        # The crossing this would forecast has already been detected and is still
        # open, so it is ticketed. A dip back under the threshold while the trend
        # still rises - or a synthetic scenario rewound by a restart - otherwise
        # forecast it again, and the shift lead got a second ticket for one fault.
        if (signal.machine_id, rule.rule_id) in open_findings:
            decisions.append(
                Decision(
                    outcome=Outcome.SUPPRESSED,
                    rule_id=rule_id,
                    machine_id=signal.machine_id,
                    why="the crossing this would forecast is already detected and open (ADR-023)",
                )
            )
            continue

        # The cooldown applies to forecasts too, and it was missing here while
        # detections had it. A prediction resolved by a technician who looked and
        # found nothing would otherwise be re-raised on the very next reading -
        # which is ADR-023 section 3's oscillating sensor wearing a different hat.
        last_resolved = resolved_at.get(key)
        if last_resolved is not None and now - last_resolved < cooldown:
            decisions.append(
                Decision(
                    outcome=Outcome.IN_COOLDOWN,
                    rule_id=rule_id,
                    machine_id=signal.machine_id,
                    why=(
                        "a forecast for this rule was resolved "
                        f"{int((now - last_resolved).total_seconds() // 60)} minutes ago and the "
                        "cooldown has not passed (ADR-023)"
                    ),
                )
            )
            continue

        decisions.append(
            Decision(
                outcome=Outcome.FORECAST,
                rule_id=rule_id,
                machine_id=signal.machine_id,
                why=trend.describe(found, metric_name=rule.metric_name, threshold=rule.threshold),
                finding=_predicted(signal, rule, rule_id, found, now=now, eta_error=eta_error),
            )
        )

    return decisions


def _predicted(
    signal: Signal,
    rule: RuleConfig,
    rule_id: RuleId,
    found: trend.Crossing,
    *,
    now: datetime,
    eta_error: Sequence[tuple[float, float]] = (),
) -> Finding:
    """The forecast as a `Finding`, with its ETA on the decision-time axis.

    **The two axes have to be joined here** (ADR-028). The crossing is computed
    in source time, because that is what the samples are stamped with and what
    the measurement compares against; but `eta` is read by things living in
    decision time - the expiry sweep, the scheduler's urgency term, the screen
    that says "in about six hours". Stored as source time on a replayed or
    compressed run, every prediction would be expired the moment it was written.

    So what is stored is how far ahead the crossing is, measured from the reading
    that produced it, laid onto the clock the system is deciding by.
    """
    ahead = found.at - signal.timestamp
    return Finding(
        machine_id=signal.machine_id,
        component=rule.component,
        symptom_code=rule.symptom_code,
        severity=rule.severity,
        rule_id=rule_id,
        detected_at=now,
        # The reading the fit ends on goes with it, so the ticket can say
        # "78 now, 85 is the line, rising 1.4 an hour" (ADR-134).
        evidence={
            **trend.evidence_for(found, threshold=rule.threshold, comparison=rule.comparison),
            "metric_name": rule.metric_name,
            "value": signal.value,
            "unit": signal.unit,
            "measured_at": signal.timestamp.isoformat(),
        },
        kind=FindingKind.PREDICTED,
        # Both, always. A prediction without its interval is an opinion presented
        # as a forecast, and the contract refuses one without the other
        # (ADR-020, ui.md 2.2).
        eta=now + ahead,
        eta_confidence=printed_interval(found.interval, ahead, eta_error),
        status=FindingStatus.OPEN,
    )


def printed_interval(
    fitted: timedelta, ahead: timedelta, bands: Sequence[tuple[float, float]]
) -> timedelta:
    """The "give or take" a ticket prints (ADR-106).

    The slope's own interval is what gates a forecast (ADR-043), and it stays
    so. What a technician reads is the wider of it and the error forecasts this
    far ahead have actually had: `bands` is (ahead_below_hours, fraction) in
    increasing order, and the fraction of the lead time it gives covered 80% of
    observed errors. Beyond the last band the last fraction applies.
    """
    if not bands or ahead <= timedelta(0):
        return fitted
    hours = ahead.total_seconds() / 3600.0
    fraction = next((f for below, f in bands if hours < below), bands[-1][1])
    return max(fitted, ahead * fraction)


def rules_watching(rules: Iterable[RuleConfig], metric_name: str) -> list[RuleConfig]:
    """The rules that read this metric. Convenience for a loop that has many."""
    return [rule for rule in rules if rule.metric_name == metric_name]


class SymptomSeen(BaseModel):
    """How often one symptom has been raised on one machine, and when.

    An aggregate over the finding table, read by the overview when it is asked
    what the system has no answer for. It counts **Findings, not firings**
    (ADR-060): a motor that stayed over its threshold all morning is one event
    with a large `occurrence_count` (ADR-023), and ranking on firings puts a stuck
    channel above a symptom that arrived on six different machines - which is
    the opposite of what "which playbook is worth writing next" means.

    `occurrences` is carried anyway, because a reviewer deciding between two
    symptoms with the same event count is helped by knowing one of them fired
    four hundred times.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_id: MachineId
    findings: int = Field(ge=1)
    occurrences: int = Field(ge=1)
    first_seen: datetime
    last_seen: datetime

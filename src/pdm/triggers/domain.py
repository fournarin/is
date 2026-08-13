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
    RuleId,
    Severity,
    Signal,
)
from pdm.platform.config.schema import RuleConfig

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Read-only empty defaults. A bare `{}` in a signature is one object shared by
# every call, and this function is called once per signal per rule: a caller that
# ever wrote to it would be writing to everybody's.
_NO_FINDINGS: Mapping[tuple[MachineId, RuleId], Finding] = MappingProxyType({})
_NO_TIMES: Mapping[tuple[MachineId, RuleId], datetime] = MappingProxyType({})
_NO_REPAIRS: Mapping[MachineId, Severity] = MappingProxyType({})

# The suppression key of ADR-023: while an open or acknowledged Finding exists
# for this pair, a repeat firing updates it rather than creating another.
SuppressionKey = tuple[MachineId, RuleId]


class Outcome(StrEnum):
    """What the caller should do with the signal it just handed over."""

    # Nothing fired, or the excess has not lasted long enough yet.
    QUIET = "quiet"
    # A new Finding, to be written.
    RAISE = "raise"
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


class Debounce:
    """How long the excess has held, per (machine, rule). Mutable on purpose.

    The one piece of state in layer 1, held by the loop rather than by the
    evaluation. A restart forgets it and the clock on a sustained excess starts
    again - which ADR-042 accepts, and writes down, because the alternative is a
    write per sample per rule for ever.
    """

    __slots__ = ("_since",)

    def __init__(self) -> None:
        self._since: dict[SuppressionKey, datetime] = {}

    def held_since(self, key: SuppressionKey, at: datetime) -> datetime:
        """When the current run of excess began, starting one if there is none."""
        return self._since.setdefault(key, at)

    def clear(self, key: SuppressionKey) -> None:
        """The value came back inside the threshold: the run is over.

        Called on every signal that does not breach, which is what makes
        `for_seconds` mean "continuously" rather than "at some point in the last
        few minutes".
        """
        self._since.pop(key, None)

    def __contains__(self, key: object) -> bool:
        return key in self._since


def breaches(signal: Signal, rule: RuleConfig) -> bool:
    """Strictly above or strictly below. Never equal.

    An interlock rule reading "below 1.0" must not fire on a healthy interlock
    sitting at exactly 1.0, which is what slice 2 found when `time_until` had to
    take a direction (ADR-032).
    """
    if rule.comparison == "above":
        return signal.value > rule.threshold
    return signal.value < rule.threshold


def evidence_for(signal: Signal, rule: RuleConfig, *, held_for: timedelta) -> dict[str, object]:
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
        "measured_at": signal.timestamp.isoformat(),
    }


def _suppressed_by_repair(
    rule: RuleConfig,
    under_repair: Mapping[MachineId, Severity],
    machine_id: MachineId,
) -> bool:
    """ADR-023 sections 4 and 5, which only make sense together.

    A machine being worked on suppresses the rule that produced that work, and
    **any rule of higher severity passes anyway**. The comparison is on severity
    rather than on the machine, because a technician is inside the machine and
    the alarm that must not be swallowed is the one that says so.
    """
    open_severity = under_repair.get(machine_id)
    if open_severity is None:
        return False
    return rule.severity.rank <= open_severity.rank


def evaluate(
    signal: Signal,
    rules: Sequence[RuleConfig],
    *,
    now: datetime,
    debounce: Debounce,
    open_findings: Mapping[SuppressionKey, Finding] = _NO_FINDINGS,
    resolved_at: Mapping[SuppressionKey, datetime] = _NO_TIMES,
    under_repair: Mapping[MachineId, Severity] = _NO_REPAIRS,
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

        key: SuppressionKey = (signal.machine_id, rule.rule_id)

        if not breaches(signal, rule):
            debounce.clear(key)
            continue

        since = debounce.held_since(key, signal.timestamp)
        held_for = signal.timestamp - since
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
                        f"{signal.machine_id} is under repair for work of equal or higher "
                        f"severity; a rule above {rule.severity.value} would still fire "
                        "(ADR-023)"
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
                    evidence=evidence_for(signal, rule, held_for=held_for),
                    kind=FindingKind.DETECTED,
                    status=FindingStatus.OPEN,
                ),
            )
        )

    return decisions


def rules_watching(rules: Iterable[RuleConfig], metric_name: str) -> list[RuleConfig]:
    """The rules that read this metric. Convenience for a loop that has many."""
    return [rule for rule in rules if rule.metric_name == metric_name]

"""Load the three config files, then check what no single file can check alone.

Per-file shape is handled by the schemas. What is left is the relationships
*between* files, and those are where the expensive mistakes live, because they
produce a system that starts normally and is quietly wrong:

  invariant 7   a rule naming a component label that the machine model does not
                declare (ADR-016)
  invariant 13  a machine a rule can fire on that sits at no station, so layer 3
                cannot compute its downtime cost (ADR-027)

Both fail the boot. A rule watching a component nobody declared is a rule whose
Findings cannot be explained to a technician, and a machine with no station gets
either a zero score or a crash depending on how the scheduler was written; both
are wrong and neither announces itself.

Errors are collected and reported together. Fixing configuration one message per
restart is how an operator ends up disabling validation.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import ValidationError

from pdm.contracts import (
    UNKNOWN_COMPONENT,
    ComponentLabel,
    Line,
    LineId,
    MachineId,
    MachineModel,
    Severity,
    ShiftDefinition,
    ShiftId,
    Station,
    StationId,
)
from pdm.contracts.wording import Wording
from pdm.platform.config.schema import PlantConfig, PmTaskConfig, PolicyConfig, RulesConfig

PLANT_FILE = "plant.yaml"
RULES_FILE = "rules.yaml"
POLICY_FILE = "policy.yaml"


class ConfigError(Exception):
    """Raised when configuration cannot be trusted. Always fatal at boot."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n".join(f"  - {problem}" for problem in problems)
        super().__init__(f"configuration is not usable:\n{joined}")


class Config:
    """Validated configuration, with the lookups the rest of the system needs.

    Holds the resolved contract objects rather than the raw file shapes, so
    callers never see the difference between a value that was nested in YAML and
    one that was not.
    """

    def __init__(self, plant: PlantConfig, rules: RulesConfig, policy: PolicyConfig) -> None:
        self.plant = plant
        self.rules = rules
        self.policy = policy
        # Resolved once. Shift boundaries are local wall-clock times and every
        # moment they are compared against is UTC, so somebody has to hold the
        # zone that joins them (ADR-045 section 7).
        self.timezone = ZoneInfo(plant.timezone)

        stations: dict[StationId, Station] = {}
        station_of: dict[MachineId, StationId] = {}
        model_of: dict[MachineId, MachineModel] = {}

        for line in plant.lines:
            for station in line.stations:
                stations[station.station_id] = Station(
                    station_id=station.station_id,
                    line_id=line.line_id,
                    seq=station.seq,
                    name=station.name,
                    buffer_units=station.buffer_units,
                    bottleneck_multiplier=station.bottleneck_multiplier,
                    machine_ids=tuple(machine.machine_id for machine in station.machines),
                )
                for machine in station.machines:
                    station_of[machine.machine_id] = station.station_id
                    model_of[machine.machine_id] = machine.model

        # Read-only views, for the same reason every contract is frozen: config
        # is an argument to dispatch(), which must be a pure function of its
        # inputs (invariant 10). Freezing the contracts and leaving config
        # writable would have left the rule half enforced.
        self.lines: Mapping[LineId, Line] = MappingProxyType(
            {
                line.line_id: Line(line_id=line.line_id, takt_seconds=line.takt_seconds)
                for line in plant.lines
            }
        )
        self.stations: Mapping[StationId, Station] = MappingProxyType(stations)
        self.skills = frozenset(plant.skills)
        self.shifts: Mapping[ShiftId, ShiftDefinition] = MappingProxyType(
            {
                shift.shift_id: ShiftDefinition(
                    shift_id=shift.shift_id, starts_at=shift.starts_at, ends_at=shift.ends_at
                )
                for shift in plant.shifts
            }
        )
        # The PM schedule, read-only like everything else here. `work/` mirrors
        # it into the `pm_task` table, which holds the half config cannot: when
        # each task was last done (ADR-083 section 1).
        self.pm_tasks: tuple[PmTaskConfig, ...] = plant.pm_tasks
        self._station_of: Mapping[MachineId, StationId] = MappingProxyType(station_of)
        self._model_of: Mapping[MachineId, MachineModel] = MappingProxyType(model_of)

    def station_of(self, machine_id: MachineId) -> Station:
        """Resolve the station a machine stands at.

        Layer 3 needs this for the w2 term but a Finding carries only a machine
        id, because the layout changes when the line is rearranged and old
        records must keep meaning what they meant (ADR-027). Validation
        guarantees the lookup cannot miss.
        """
        return self.stations[self._station_of[machine_id]]

    def line_of(self, machine_id: MachineId) -> Line:
        return self.lines[self.station_of(machine_id).line_id]

    def model_of(self, machine_id: MachineId) -> MachineModel:
        return self._model_of[machine_id]

    def machines_of(self, model: MachineModel) -> list[str]:
        """Every machine of this model in the layout, sorted."""
        return sorted(str(machine) for machine, of in self._model_of.items() if of == model)

    def components_of(self, model: MachineModel) -> tuple[ComponentLabel, ...]:
        return self.rules.components.get(model, ())

    def wording(self) -> Wording:
        """The plant's clock and names, for every sentence a screen shows (ADR-093)."""
        titles: dict[str, str] = {}
        for rule in self.rules.rules:
            if rule.title is not None:
                titles.setdefault(str(rule.symptom_code), rule.title)
        for task in self.plant.pm_tasks:
            if task.title is not None:
                titles.setdefault(str(task.symptom_code), task.title)
        return Wording(
            timezone=self.timezone,
            symptom_titles=titles,
            skill_names={str(skill): name for skill, name in self.plant.skill_names.items()},
        )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError([f"{path} is missing"])
    parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, dict):
        raise ConfigError([f"{path} must contain a mapping at the top level"])
    return parsed


def _cross_file_problems(plant: PlantConfig, rules: RulesConfig, policy: PolicyConfig) -> list[str]:
    problems: list[str] = []

    machine_models: dict[MachineId, MachineModel] = {}
    station_of: dict[MachineId, StationId] = {}

    for line in plant.lines:
        seqs = Counter(station.seq for station in line.stations)
        for seq, count in seqs.items():
            if count > 1:
                problems.append(f"line {line.line_id}: {count} stations share seq {seq}")
        for station in line.stations:
            for machine in station.machines:
                if machine.machine_id in station_of:
                    problems.append(
                        f"machine {machine.machine_id} appears at two stations: "
                        f"{station_of[machine.machine_id]} and {station.station_id}"
                    )
                station_of[machine.machine_id] = station.station_id
                machine_models[machine.machine_id] = machine.model

    station_ids = Counter(station.station_id for line in plant.lines for station in line.stations)
    for station_id, count in station_ids.items():
        if count > 1:
            problems.append(f"station id {station_id} is used {count} times")

    shift_ids = Counter(shift.shift_id for shift in plant.shifts)
    for shift_id, count in shift_ids.items():
        if count > 1:
            problems.append(f"shift id {shift_id} is used {count} times")

    declared_models = set(machine_models.values())

    # Invariant 7 (ADR-016): a rule may only name a component its model declares.
    for rule in rules.rules:
        if rule.machine_model not in declared_models:
            problems.append(
                f"rule {rule.rule_id} targets machine model {rule.machine_model}, "
                f"which no machine in {PLANT_FILE} uses"
            )
            continue
        allowed = set(rules.components.get(rule.machine_model, ()))
        if rule.component == UNKNOWN_COMPONENT:
            continue
        if rule.component not in allowed:
            problems.append(
                f"rule {rule.rule_id} watches component {rule.component!r}, which is not "
                f"declared for {rule.machine_model}. Declared: {sorted(allowed) or 'none'} "
                f"(invariant 7, ADR-016)"
            )

    rule_ids = Counter(rule.rule_id for rule in rules.rules)
    for rule_id, count in rule_ids.items():
        if count > 1:
            problems.append(f"rule id {rule_id} is used {count} times")

    # Invariant 13 (ADR-027) asked that every machine a rule can fire on sit at
    # a station, or the w2 term has nothing to compute against. A check for it
    # stood here and could never fire: `station_of` and `machine_models` are
    # filled in the same loop, from the same key, so a machine in one is in the
    # other. It was removed by ADR-084 section 4 rather than left as a line that
    # reads like enforcement.
    #
    # What holds the property is the shape of plant.yaml: a machine is declared
    # inside a station and cannot be declared anywhere else, so there is no
    # loadable configuration in which a machine has no station. The half that
    # can go wrong is a rule naming a model no machine uses, and that is refused
    # above. Both are tested in tests/platform/test_config.py.

    # The PM schedule names machines, and a task on a machine that is not in the
    # layout would fall due for ever with nothing able to price it or place it
    # (ADR-083 section 1). The same shape of check as invariant 7's, and at the
    # same moment: a plant that boots is a plant whose schedule can run.
    pm_refs = Counter(task.pm_task_ref for task in plant.pm_tasks)
    for pm_task_ref, count in pm_refs.items():
        if count > 1:
            problems.append(f"PM task ref {pm_task_ref} is used {count} times")
    for task in plant.pm_tasks:
        if task.machine_id not in machine_models:
            problems.append(
                f"PM task {task.pm_task_ref} is scheduled on machine {task.machine_id}, "
                f"which no station in {PLANT_FILE} holds"
            )

    for model in rules.components:
        if model not in declared_models:
            problems.append(
                f"{RULES_FILE} declares components for machine model {model}, "
                f"which no machine in {PLANT_FILE} uses"
            )

    # A model with no fallback estimate loses its long-tail work: no duration
    # means no place in the queue, and nobody notices the gap (design.md 3.2).
    for model in sorted(declared_models):
        if model not in policy.fallback_minutes:
            problems.append(
                f"{POLICY_FILE} has no fallback estimate for machine model {model}, so work "
                f"on it without a playbook would have no duration and drop out of the queue"
            )
            continue
        # And every severity, not merely the model. The lookup at issue time is
        # [model][severity], so a table missing one row boots cleanly and then
        # fails on the first critical fault with no playbook - which moves the
        # "long-tail work vanishes" failure out of config validation, where it is
        # cheap, and into the plant, where it is not (ADR-041).
        missing = [
            severity.value
            for severity in Severity
            if severity not in policy.fallback_minutes[model]
        ]
        if missing:
            problems.append(
                f"{POLICY_FILE} has no fallback estimate for {model} at severity "
                f"{', '.join(missing)}; work at that severity with no playbook would have no "
                f"duration and drop out of the queue"
            )

    for model, unknown in (
        (model, model not in declared_models) for model in policy.fallback_minutes
    ):
        if unknown:
            problems.append(
                f"{POLICY_FILE} has a fallback estimate for machine model {model}, "
                f"which no machine in {PLANT_FILE} uses"
            )

    return problems


def load_config(directory: Path) -> Config:
    """Load and validate. Raises ConfigError, which must not be caught at boot."""
    problems: list[str] = []
    parsed: dict[str, Any] = {}

    for name, model in (
        (PLANT_FILE, PlantConfig),
        (RULES_FILE, RulesConfig),
        (POLICY_FILE, PolicyConfig),
    ):
        try:
            parsed[name] = model.model_validate(_read_yaml(directory / name))
        except ConfigError as error:
            problems.extend(error.problems)
        except ValidationError as error:
            for issue in error.errors():
                location = ".".join(str(part) for part in issue["loc"]) or "(root)"
                problems.append(f"{name}: {location}: {issue['msg']}")
        except yaml.YAMLError as error:
            problems.append(f"{name}: is not valid YAML: {error}")

    if problems:
        raise ConfigError(problems)

    plant, rules, policy = parsed[PLANT_FILE], parsed[RULES_FILE], parsed[POLICY_FILE]
    cross = _cross_file_problems(plant, rules, policy)
    if cross:
        raise ConfigError(cross)

    return Config(plant=plant, rules=rules, policy=policy)

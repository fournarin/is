"""Configuration that cannot be trusted must stop the boot (design.md 9).

The interesting tests here are the rejections. A loader that accepts everything
is indistinguishable from no loader at all, and the mistakes it exists to catch
are exactly the ones that would otherwise produce a system that starts normally
and is quietly wrong: a rule watching a component nobody declared, a machine at
no station, a retrieval profile that is permissive in the place where nobody is
checking the output.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from pdm.contracts import MachineId, MachineModel, StationId
from pdm.platform.config import ConfigError, load_config

REPO_CONFIG = Path("config")

PLANT: dict[str, Any] = {
    "version": 1,
    "lines": [
        {
            "line_id": "line-a",
            "takt_seconds": 60.0,
            "stations": [
                {
                    "station_id": "st-01",
                    "seq": 1,
                    "buffer_units": 20,
                    "machines": [{"machine_id": "MC-001", "model": "R-2000iC"}],
                },
                {
                    "station_id": "st-03",
                    "seq": 3,
                    "buffer_units": 0,
                    "bottleneck_multiplier": 3.0,
                    "machines": [{"machine_id": "MC-012", "model": "R-2000iC"}],
                },
            ],
        }
    ],
    "skills": ["robot_mechanical", "electrical"],
    "shifts": [{"shift_id": "morning", "starts_at": "06:00", "ends_at": "14:00"}],
}

RULES: dict[str, Any] = {
    "version": 1,
    "components": {"R-2000iC": ["belt_motor", "cooling_fan"]},
    "rules": [
        {
            "rule_id": "R-motor-temp-high",
            "machine_model": "R-2000iC",
            "component": "belt_motor",
            "symptom_code": "SYM-014",
            "metric_name": "motor_temp_c",
            "comparison": "above",
            "threshold": 85.0,
            "for_seconds": 120,
            "severity": "high",
            "safety_critical": False,
        }
    ],
}

POLICY: dict[str, Any] = {
    "version": 1,
    "weights": {
        "severity": 1.0,
        "downtime": 1.0,
        "skill_match": 0.5,
        "waiting": 0.3,
        "eta_urgency": 0.7,
    },
    "load": {"light_below": 0.5, "heavy_at_or_above": 0.8},
    "triggers": {
        "cooldown_minutes": 30,
        "eta_grace_minutes": 60,
        "trend": {"window_minutes": 120, "min_samples": 10, "max_horizon_hours": 24},
    },
    "retrieval": {
        "authoring": {"min_score": 0.20, "candidates": 40, "abstain": False},
        "runtime": {
            "min_score": 0.35,
            "safety_min_score": 0.45,
            "candidates": 8,
            "abstain": True,
        },
    },
    "fallback_minutes": {"R-2000iC": {"low": 30, "medium": 45, "high": 60, "critical": 90}},
}


def _write(tmp_path: Path, **overrides: dict[str, Any]) -> Path:
    files = {"plant.yaml": PLANT, "rules.yaml": RULES, "policy.yaml": POLICY} | overrides
    for name, body in files.items():
        (tmp_path / name).write_text(yaml.safe_dump(body), encoding="utf-8")
    return tmp_path


def _deep(base: dict[str, Any]) -> dict[str, Any]:
    """Deep copy via YAML, so a test mutating a nested dict cannot leak into the
    next one through the shared fixtures above."""
    copied: dict[str, Any] = yaml.safe_load(yaml.safe_dump(base))
    return copied


class TestTheRepositoryConfigIsValid:
    """The config shipped in this repository must load, or the gate is checking
    nothing on every other run."""

    def test_it_loads(self) -> None:
        config = load_config(REPO_CONFIG)
        assert config.plant.version >= 1

    def test_a_bottleneck_and_a_buffered_station_both_exist(self) -> None:
        """ADR-021 needs both to be present, or the station-level w2 term can
        never be shown to differ from a line-level constant."""
        buffers = {station.buffer_units for station in load_config(REPO_CONFIG).stations.values()}
        assert 0 in buffers, "no bottleneck station to test against"
        assert max(buffers) >= 8, "no well-buffered station to contrast with"

    def test_there_is_an_unknown_component_rule(self) -> None:
        """ADR-009 requires phase 1 to prove the fault-finding path, so at least
        one rule must be honest about not knowing which part is at fault."""
        rules = load_config(REPO_CONFIG).rules.rules
        assert any(rule.component == "unknown" for rule in rules)

    def test_there_is_a_safety_critical_rule(self) -> None:
        """ADR-022 forbids loops from loosening safety thresholds. The
        prohibition needs at least one rule carrying the flag to act on."""
        rules = load_config(REPO_CONFIG).rules.rules
        assert any(rule.safety_critical for rule in rules)


class TestInvariant7ComponentLabels:
    """ADR-016: a rule may only name a component its machine model declares."""

    def test_an_undeclared_component_stops_the_boot(self, tmp_path: Path) -> None:
        rules = _deep(RULES)
        rules["rules"][0]["component"] = "gearbox"
        with pytest.raises(ConfigError, match="invariant 7"):
            load_config(_write(tmp_path, **{"rules.yaml": rules}))

    def test_the_error_lists_what_was_declared(self, tmp_path: Path) -> None:
        """An operator who is told only that the value is wrong has to go
        looking. Telling them the allowed set is the difference between a
        one-minute fix and a hunt."""
        rules = _deep(RULES)
        rules["rules"][0]["component"] = "gearbox"
        with pytest.raises(ConfigError) as caught:
            load_config(_write(tmp_path, **{"rules.yaml": rules}))
        assert "belt_motor" in str(caught.value)

    def test_unknown_is_always_allowed(self, tmp_path: Path) -> None:
        """The escape hatch ADR-009 requires: a rule that cannot say which part
        it watches says so, rather than guessing."""
        rules = _deep(RULES)
        rules["rules"][0]["component"] = "unknown"
        assert load_config(_write(tmp_path, **{"rules.yaml": rules}))


class TestInvariant13MachinesAndStations:
    """ADR-027: a machine that can raise Findings must sit somewhere."""

    def test_a_rule_for_a_model_no_machine_uses_stops_the_boot(self, tmp_path: Path) -> None:
        rules = _deep(RULES)
        rules["components"]["X-9000"] = ["belt_motor"]
        rules["rules"][0]["machine_model"] = "X-9000"
        with pytest.raises(ConfigError, match=r"no machine in plant\.yaml uses"):
            load_config(_write(tmp_path, **{"rules.yaml": rules}))

    def test_a_machine_listed_at_two_stations_stops_the_boot(self, tmp_path: Path) -> None:
        """Ambiguity here means the w2 term silently picks whichever station the
        lookup happened to reach first."""
        plant = _deep(PLANT)
        plant["lines"][0]["stations"][1]["machines"].append(
            {"machine_id": "MC-001", "model": "R-2000iC"}
        )
        with pytest.raises(ConfigError, match="appears at two stations"):
            load_config(_write(tmp_path, **{"plant.yaml": plant}))

    def test_duplicate_station_ids_stop_the_boot(self, tmp_path: Path) -> None:
        plant = _deep(PLANT)
        plant["lines"][0]["stations"][1]["station_id"] = "st-01"
        with pytest.raises(ConfigError, match="is used 2 times"):
            load_config(_write(tmp_path, **{"plant.yaml": plant}))


class TestPolicyRelationships:
    def test_load_thresholds_must_be_ordered(self, tmp_path: Path) -> None:
        policy = _deep(POLICY)
        policy["load"] = {"light_below": 0.9, "heavy_at_or_above": 0.5}
        with pytest.raises(ConfigError, match="light threshold must sit below"):
            load_config(_write(tmp_path, **{"policy.yaml": policy}))

    def test_the_authoring_profile_must_be_the_looser_one(self, tmp_path: Path) -> None:
        """ADR-015. Swapping these would make the profile with nobody checking
        its output the permissive one, which is the single arrangement ADR-003
        exists to prevent."""
        policy = _deep(POLICY)
        policy["retrieval"]["authoring"]["min_score"] = 0.60
        with pytest.raises(ConfigError, match="looser one"):
            load_config(_write(tmp_path, **{"policy.yaml": policy}))

    def test_the_runtime_profile_must_abstain(self, tmp_path: Path) -> None:
        policy = _deep(POLICY)
        policy["retrieval"]["runtime"]["abstain"] = False
        with pytest.raises(ConfigError, match="must abstain"):
            load_config(_write(tmp_path, **{"policy.yaml": policy}))

    def test_a_model_without_a_fallback_estimate_stops_the_boot(self, tmp_path: Path) -> None:
        """Without a duration a job cannot be queued, so long-tail work would
        disappear from the system with nothing reporting its absence."""
        policy = _deep(POLICY)
        policy["fallback_minutes"] = {}
        with pytest.raises(ConfigError, match="no fallback estimate"):
            load_config(_write(tmp_path, **{"policy.yaml": policy}))


class TestFailureReporting:
    def test_a_misspelled_key_is_rejected_rather_than_ignored(self, tmp_path: Path) -> None:
        """Silently ignoring it gives the operator a file that says one thing and
        a system doing another."""
        policy = _deep(POLICY)
        policy["load"]["heavy_at"] = policy["load"].pop("heavy_at_or_above")
        with pytest.raises(ConfigError):
            load_config(_write(tmp_path, **{"policy.yaml": policy}))

    def test_every_problem_is_reported_at_once(self, tmp_path: Path) -> None:
        """Fixing configuration one message per restart is how somebody ends up
        turning validation off."""
        rules = _deep(RULES)
        rules["rules"][0]["component"] = "gearbox"
        rules["rules"].append(rules["rules"][0] | {"rule_id": "R-second", "component": "flywheel"})
        with pytest.raises(ConfigError) as caught:
            load_config(_write(tmp_path, **{"rules.yaml": rules}))
        assert len(caught.value.problems) >= 2

    def test_a_missing_file_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match=r"plant\.yaml is missing"):
            load_config(tmp_path)


class TestLookups:
    def test_a_machine_resolves_to_its_station_line_and_model(self, tmp_path: Path) -> None:
        """The lookup layer 3 needs for w2. A Finding carries only a machine id
        because the layout changes when the line is rearranged (ADR-027)."""
        config = load_config(_write(tmp_path))
        assert config.station_of(MachineId("MC-012")).station_id == StationId("st-03")
        assert config.line_of(MachineId("MC-012")).takt_seconds == 60.0
        assert config.model_of(MachineId("MC-012")) == MachineModel("R-2000iC")

    def test_a_bottleneck_buys_no_time_and_a_buffer_does(self, tmp_path: Path) -> None:
        config = load_config(_write(tmp_path))
        line = config.line_of(MachineId("MC-001"))
        assert config.station_of(MachineId("MC-001")).buffer_minutes(line) == 20.0
        assert config.station_of(MachineId("MC-012")).buffer_minutes(line) == 0.0


class TestConfigIsReadOnly:
    """Config is an argument to dispatch(), which must be a pure function of its
    inputs (invariant 10).

    Freezing every contract and then handing the scheduler a writable config
    would have enforced the rule on one input and not the other, which is the
    kind of half-measure that looks enforced until the day it is not.
    """

    def test_stations_cannot_be_replaced(self, tmp_path: Path) -> None:
        config = load_config(_write(tmp_path))
        with pytest.raises(TypeError):
            config.stations[StationId("st-99")] = config.stations[StationId("st-01")]  # type: ignore[index]

    def test_a_station_itself_cannot_be_edited(self, tmp_path: Path) -> None:
        config = load_config(_write(tmp_path))
        with pytest.raises(ValidationError):
            config.stations[StationId("st-01")].buffer_units = 0

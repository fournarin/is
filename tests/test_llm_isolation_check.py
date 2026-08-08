"""The invariant 15 gate must actually catch the things it claims to.

A checker that only ever runs against a compose file it passes is untested. It
would keep passing after somebody moves api onto the llm network, and nobody
would find out until the wrong thing had been shipped, because a silent gate
looks exactly like a satisfied one.

The real docker-compose.yml is also checked here, so a change to it fails the
unit suite and not only the CI step.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.check_llm_isolation import COMPOSE, check

GOOD = """
services:
  api:
    networks: [app]
  web:
    networks: [app]
  worker-runtime:
    networks: [app]
  worker-authoring:
    networks: [app, llm]
  llm-server:
    networks: [llm]
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "docker-compose.yml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_real_compose_file_holds_the_invariant() -> None:
    assert check(COMPOSE) == []


def test_a_correct_split_passes(tmp_path: Path) -> None:
    assert check(_write(tmp_path, GOOD)) == []


@pytest.mark.parametrize("service", ["api", "web", "worker-runtime"])
def test_a_runtime_service_joining_the_llm_network_is_caught(tmp_path: Path, service: str) -> None:
    broken = GOOD.replace(
        f"  {service}:\n    networks: [app]",
        f"  {service}:\n    networks: [app, llm]",
    )
    violations = check(_write(tmp_path, broken))
    assert any(service in v and "llm" in v for v in violations)


def test_publishing_a_host_port_on_the_llm_is_caught(tmp_path: Path) -> None:
    """The subtle one: networks stay correct, yet the model becomes reachable
    from the host, which defeats the split just as completely."""
    broken = GOOD.replace(
        "  llm-server:\n    networks: [llm]",
        '  llm-server:\n    networks: [llm]\n    ports: ["11434:11434"]',
    )
    violations = check(_write(tmp_path, broken))
    assert any("publishes host port" in v for v in violations)


def test_long_form_network_syntax_is_understood(tmp_path: Path) -> None:
    """Compose allows `networks:` as a mapping. Reading only the list form would
    make the checker silently see no networks at all and pass everything."""
    broken = GOOD.replace(
        "  api:\n    networks: [app]",
        "  api:\n    networks:\n      app: {}\n      llm: {}",
    )
    violations = check(_write(tmp_path, broken))
    assert any("api" in v and "llm" in v for v in violations)


def test_a_missing_llm_service_is_reported_rather_than_passed(tmp_path: Path) -> None:
    without_llm = GOOD.replace("  llm-server:\n    networks: [llm]\n", "")
    assert check(_write(tmp_path, without_llm)) != []


@pytest.mark.parametrize("service", ["api", "web", "worker-runtime"])
def test_a_deleted_runtime_service_is_reported_rather_than_passed(
    tmp_path: Path, service: str
) -> None:
    """Deleting a service must not be a way to make the check go quiet."""
    without = GOOD.replace(f"  {service}:\n    networks: [app]\n", "")
    assert check(_write(tmp_path, without)) != []

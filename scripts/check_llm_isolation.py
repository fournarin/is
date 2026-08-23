"""api, web and worker-runtime must not be able to reach llm-server.

Invariant 15 (ADR-029). This is the second of the two independent layers that
enforce ADR-003, and it exists because the first one cannot see everything:

  .importlinter   catches `from pdm import llm` and any indirect path to it,
                  but only for calls made through a module.
  this script     catches a raw HTTP request, which the import linter cannot
                  see at all, because reachability is a property of the
                  deployment rather than of the source.

Without both, "the LLM never generates repair instructions at runtime" is a
promise. With both it is a property of the system.

Two things are checked, and the second is the one that is easy to lose:

  1. No runtime service shares a network with llm-server.
  2. llm-server publishes no host port. A published port bypasses the network
     split entirely, since anything on the host can then reach the model. That
     is a one-line change somebody makes while debugging and forgets to revert.

Every other `docker-compose*.yml` in the repository is checked too. A service
added in an override joins the same networks as one added in the base file, and
a gate reading only the base file would not see it - which is exactly how a hole
opens quietly. The first such file is the rehearsal's (ADR-067).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

COMPOSE = Path("docker-compose.yml")
LLM_SERVICE = "llm-server"

# Overrides, additions, anything else somebody writes beside the base file.
OTHER_FILES = tuple(sorted(Path().glob("docker-compose.*.yml")))

# The only two things allowed on the LLM's network, in any compose file
# (ADR-026, ADR-029). Everything else is a violation wherever it is declared.
MAY_REACH_THE_LLM = frozenset({"worker-authoring", LLM_SERVICE})

# Everything that serves or schedules work for technicians. ADR-026 puts the
# trigger loop and the dispatch tick in worker-runtime, so it belongs here too.
RUNTIME_SERVICES = ("api", "web", "worker-runtime")


def _networks(service: dict[str, Any]) -> set[str]:
    declared = service.get("networks")
    if declared is None:
        return set()
    if isinstance(declared, dict):  # long form: {app: {aliases: [...]}}
        return set(declared)
    return set(declared)


def llm_networks_in(compose_path: Path) -> set[str]:
    """The networks llm-server is on, read from the file that declares it."""
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8")) or {}
    service = (compose.get("services") or {}).get(LLM_SERVICE)
    return _networks(service) if service else set()


def check_other_files(paths: Sequence[Path], *, llm_networks: set[str]) -> list[str]:
    """Any service in any other compose file that joins the LLM's network.

    Deliberately not a copy of `check()`: those files declare no llm-server and
    need not declare every runtime service, so the question here is the opposite
    one - not "are the four services isolated" but "has anything at all been put
    on the network the isolation depends on".
    """
    violations: list[str] = []
    for path in paths:
        compose = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for name, service in (compose.get("services") or {}).items():
            if name in MAY_REACH_THE_LLM:
                continue
            shared = _networks(service or {}) & llm_networks
            if shared:
                violations.append(
                    f"{path}: {name} shares network(s) {sorted(shared)} with {LLM_SERVICE}"
                )
    return violations


def check(compose_path: Path) -> list[str]:
    """Return a list of violations; empty means the invariant holds."""
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    services = compose.get("services", {})

    if LLM_SERVICE not in services:
        return [f"{compose_path}: no {LLM_SERVICE} service, so the split cannot be verified"]

    violations: list[str] = []
    llm_networks = _networks(services[LLM_SERVICE])

    for name in RUNTIME_SERVICES:
        service = services.get(name)
        if service is None:
            violations.append(f"{name}: missing, so its isolation cannot be verified")
            continue
        shared = _networks(service) & llm_networks
        if shared:
            violations.append(f"{name}: shares network(s) {sorted(shared)} with {LLM_SERVICE}")

    if services[LLM_SERVICE].get("ports"):
        violations.append(
            f"{LLM_SERVICE}: publishes host port(s) {services[LLM_SERVICE]['ports']}, "
            "which makes the model reachable from the host and bypasses the network split"
        )

    return violations


def main() -> int:
    violations = check(COMPOSE) + check_other_files(
        OTHER_FILES, llm_networks=llm_networks_in(COMPOSE)
    )
    if violations:
        print("LLM reachable from a runtime service (ADR-029, invariant 15).")
        print(f"Only worker-authoring may reach {LLM_SERVICE}.\n")
        for violation in violations:
            print(f"  {violation}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

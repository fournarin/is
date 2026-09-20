"""The rehearsal's own container is built from the checkout it is rehearsing.

Found on 2026-09-20 by slice 16.1. `docker compose up --build` builds the
services it is starting, and `rehearsal` is behind a profile, so it is not one
of them. It therefore kept whatever image the previous build had left, and every
screen check and every seed ran against that code while the stack ran against
the new code.

Nothing said so while the two happened to agree. The slice added `pm_tasks` to
`plant.yaml`, the older image refused the file - `pm_tasks: Extra inputs are not
permitted` - and the failure arrived as a traceback from a container that looks
like part of this stack.

This is a test of a file rather than of behaviour, for the reason
`tests/test_the_model_ships_in_the_image.py` gives about the Dockerfile: no CI
tier can start the stack (ADR-067), so the agreement between two build files is
the only place this can be held from the other side.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REHEARSE = Path("scripts/rehearse.py")
COMPOSE_FILE = Path("docker-compose.rehearsal.yml")


def test_the_rehearsal_service_is_behind_a_profile() -> None:
    """Which is why `up --build` skips it, and why the line below is needed."""
    service = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]["rehearsal"]

    assert service["profiles"] == ["rehearsal"]
    assert "build" in service


def test_the_script_builds_it_explicitly() -> None:
    source = REHEARSE.read_text(encoding="utf-8")

    assert 'compose("build", "rehearsal")' in source


def test_it_is_built_before_anything_runs_in_it() -> None:
    """A build after the first seed would be a build after that seed had
    already run against the stale image, which is the failure itself.

    Positions in the source of `main`, not of the helper: `in_the_stack` is
    defined above everything it is called from.
    """
    source = REHEARSE.read_text(encoding="utf-8")

    built_at = source.index('compose("build", "rehearsal")')
    first_use = source.index("in_the_stack(SEED)")

    assert built_at < first_use

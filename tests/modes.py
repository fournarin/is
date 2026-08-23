"""The same configuration in the other confirmation mode (ADR-071 §2).

`config/policy.yaml` ships `confirmation: supervisor`, because that is what the
plant was told it would get and it is the mode that cannot send work nobody
approved. `automatic` is the other supported mode - the behaviour every record
before ADR-071 assumed - and the tests that are about something else entirely
(layer 4's retries, a round meeting a database that moved under it) say so here
rather than each growing a supervisor who presses a button for reasons that have
nothing to do with what they assert.

Built by copying the loaded config rather than by reading a second policy file:
a fixture file would be a second place the policy schema has to be kept up to
date, and it would drift the first time somebody adds a key.
"""

from __future__ import annotations

from pdm.platform.config import Config


def automatic(config: Config) -> Config:
    """The same plant, dispatching without waiting for anybody."""
    return _with_confirmation(config, "automatic")


def supervising(config: Config) -> Config:
    """The same plant, holding every placement for a supervisor.

    The shipped default, so this exists for a test that wants to be explicit
    about the mode it is asserting on rather than to change anything.
    """
    return _with_confirmation(config, "supervisor")


def _with_confirmation(config: Config, mode: str) -> Config:
    dispatch = config.policy.dispatch.model_copy(update={"confirmation": mode})
    policy = config.policy.model_copy(update={"dispatch": dispatch})
    return Config(config.plant, config.rules, policy)

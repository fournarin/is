"""Configuration: versioned YAML, validated at boot, fatal when wrong.

design.md 9 makes config a contract rather than a set of constants. Three ADRs
forbid hard-coding values that belong here, the plant will want to change
thresholds without a deploy, and the simulator is only reproducible if
(config + seed) determines the result completely.
"""

from pdm.platform.config.loader import Config, ConfigError, load_config

__all__ = ["Config", "ConfigError", "load_config"]

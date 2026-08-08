"""Validate configuration without starting anything: `python -m pdm.platform.config`

Runs in CI as a tier 0 gate and is what an operator runs after editing a file,
so that a mistake is found at a keyboard rather than at 2am on the factory
floor.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pdm.platform.config.loader import ConfigError, load_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate configuration.")
    parser.add_argument("directory", nargs="?", default="config", type=Path)
    args = parser.parse_args(argv)

    try:
        config = load_config(args.directory)
    except ConfigError as error:
        print(f"{args.directory}: {error}", file=sys.stderr)
        return 1

    stations = len(config.stations)
    machines = sum(len(station.machine_ids) for station in config.stations.values())
    print(
        f"{args.directory}: ok - {len(config.lines)} line(s), {stations} station(s), "
        f"{machines} machine(s), {len(config.rules.rules)} rule(s), "
        f"{len(config.skills)} skill(s), {len(config.shifts)} shift(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Only the Clock port may read the operating system clock (ADR-028, invariant 14).

Without this check SimulatedClock is decorative: some part of the system would
still be reading real time, so a compressed run would mix two timelines. A
Finding would carry a simulated detected_at while its cooldown was compared
against the real clock, making the cooldown either never expire or expire at
once depending on which way the run was compressed. Feedback Loop 3 could not
measure ETA error at all, because predicted and actual times would sit on
different axes.

The rule is deliberately stricter than "domain code must not read the clock":
*nothing* outside clock.py may, which is both easier to state and easier to
check. Anything needing the time receives a Clock.

Escape hatch: append `# allow: wall-clock` to a line that genuinely has to call the
system clock. It should be rare enough to be reviewed each time it appears.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCE_ROOT = Path("src/pdm")

# The one file allowed to touch real time, because it is what everything else
# receives instead.
ALLOWED = {SOURCE_ROOT / "platform" / "clock.py"}

BANNED = re.compile(
    r"""\b(
        datetime\.(now|utcnow)      # datetime.now(), datetime.utcnow()
      | time\.(time|monotonic|perf_counter)
      | date\.today
    )\s*\(""",
    re.VERBOSE,
)

ESCAPE_HATCH = "allow: wall-clock"


def main() -> int:
    violations: list[str] = []

    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if path in ALLOWED:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if BANNED.search(line) and ESCAPE_HATCH not in line:
                violations.append(f"{path}:{lineno}: {line.strip()}")

    if violations:
        print("System clock read outside the Clock port (ADR-028, invariant 14).")
        print("Accept a Clock instead of reading the time directly:\n")
        print("\n".join(violations))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

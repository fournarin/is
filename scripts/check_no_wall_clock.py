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

**This reads the syntax tree rather than the text of each line (ADR-084 §5).**
The first version matched five call patterns with a regular expression and so
answered for `datetime.now()` and not for `datetime.today()`, `time.time_ns()`,
`time.monotonic_ns()`, or any aliased import - `from datetime import datetime as
dt` and then `dt.now()` read as ordinary code to it. None of those appeared in
`src/` when that was found (#105), which is the whole difficulty with a gate
that is narrower than the rule it is named after: it is green either way, and
the day it is wrong it is still green. Resolving the import binding is what lets
the check answer for the rule rather than for a spelling of it.

Escape hatch: append `# allow: wall-clock` to a line that genuinely has to call
the system clock. It should be rare enough to be reviewed each time it appears.
On a call spread over several lines, the comment may sit on any of them.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

SOURCE_ROOT = Path("src/pdm")

# The one file allowed to touch real time, because it is what everything else
# receives instead.
ALLOWED = {SOURCE_ROOT / "platform" / "clock.py"}

# Canonical dotted paths, as the resolver below spells them however the module
# was imported. Every one of these answers "what time is it" from the operating
# system; arithmetic on a datetime it was handed does not and is not here.
BANNED = {
    "time.time",
    "time.time_ns",
    "time.monotonic",
    "time.monotonic_ns",
    "time.perf_counter",
    "time.perf_counter_ns",
    "time.process_time",
    "time.process_time_ns",
    "time.clock_gettime",
    "time.clock_gettime_ns",
    "time.localtime",
    "time.gmtime",
    "datetime.datetime.now",
    "datetime.datetime.utcnow",
    "datetime.datetime.today",
    "datetime.date.today",
}

# What `from X import Y` binds a name to, for the modules that can produce a
# banned call. Anything else imported from them is ordinary.
FROM_IMPORT_ROOTS = {"time", "datetime"}

ESCAPE_HATCH = "allow: wall-clock"


def _dotted(node: ast.expr) -> str | None:
    """`dt.now` for the call `dt.now()`, or None for anything not a plain name
    or attribute chain - a call on a subscript or a return value cannot be
    resolved to an import and is not what this gate is looking for."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


def _bindings(tree: ast.Module) -> dict[str, str]:
    """Every local name that leads back to `time` or `datetime`, mapped to the
    canonical path it stands for. This is the part a regular expression cannot
    do: `from datetime import datetime as dt` makes `dt.now()` the same call as
    `datetime.datetime.now()`, spelled with none of the same characters."""
    bound: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in FROM_IMPORT_ROOTS:
                    bound[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module in FROM_IMPORT_ROOTS:
            if node.level:  # a relative import that happens to share the name
                continue
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bound


def _canonical(dotted: str, bound: dict[str, str]) -> str | None:
    head, _, rest = dotted.partition(".")
    root = bound.get(head)
    if root is None:
        return None
    return f"{root}.{rest}" if rest else root


def wall_clock_calls(source: str, *, filename: str = "<source>") -> list[str]:
    """Every banned call in one module, as `line: text` for the report.

    A module that will not parse is reported rather than skipped: a check that
    goes quiet on a file it cannot read is a check that passes for the wrong
    reason, which is the failure this rewrite exists for.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as broken:
        return [f"{broken.lineno}: cannot be parsed, so it cannot be checked ({filename})"]

    lines = source.splitlines()
    bound = _bindings(tree)
    found: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        dotted = _dotted(node.func)
        if dotted is None:
            continue
        canonical = _canonical(dotted, bound)
        if canonical not in BANNED:
            continue
        first = node.lineno
        last = node.end_lineno or first
        spanned = lines[first - 1 : last]
        if any(ESCAPE_HATCH in line for line in spanned):
            continue
        found.append(f"{first}: {lines[first - 1].strip()}")

    return found


def main() -> int:
    violations: list[str] = []

    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        if path in ALLOWED:
            continue
        source = path.read_text(encoding="utf-8")
        violations.extend(
            f"{path}:{found}" for found in wall_clock_calls(source, filename=str(path))
        )

    if violations:
        print("System clock read outside the Clock port (ADR-028, invariant 14).")
        print("Accept a Clock instead of reading the time directly:\n")
        print("\n".join(violations))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

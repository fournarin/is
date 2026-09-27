"""The second of ADR-002's three sources: signals read back from a file.

This is the shortest path from the plant to this system. A historian export,
a PLC log converted by hand, or a spreadsheet somebody kept on a line is enough;
no OPC UA server, network route or plant IT ticket is needed (ADR-091).

The file is the `Signal` contract as CSV, one row per reading:

    timestamp,machine_id,metric_name,value,unit
    2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68.2,C

`parse()` is pure and does the checking; `ReplaySource` opens the file only
when it is streamed, because constructing a source must not open a file
(`Feed` makes the same promise about generators).

Three decisions, each of which a plant export will test on its first day:

  * **A timestamp without an offset is refused.** Source time is compared with
    decision time, and the offset a naive time "obviously" has is the plant's
    at export and UTC on the server that reads it. A wrong guess is seven hours
    of ETA error that looks like a prediction (ADR-028).
  * **Rows are sorted by source time, not refused when out of order.** The port
    promises non-decreasing time because the rule engine's debounce measures
    duration by subtraction. Exports are commonly grouped by tag rather than by
    time, and the ordering is recoverable, so it is recovered.
  * **An exact duplicate row is emitted once.** The port promises that a signal
    is emitted once, and overlapping exports are how the same reading appears
    twice. Two different values for one tag at one instant are both kept: that
    is the data saying something, and the rule engine is where it is judged.

Every refusal names the line, so a person fixing the export can find it.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Iterator
from datetime import datetime
from pathlib import Path

from pdm.contracts import MachineId, Signal

COLUMNS = ("timestamp", "machine_id", "metric_name", "value", "unit")


class ReplayFileError(ValueError):
    """The file cannot be read as signals. The message lists every bad line."""


def parse(lines: Iterable[str], *, name: str = "replay file") -> list[Signal]:
    """Every signal in the file, in non-decreasing source-time order.

    All-or-nothing: one bad row refuses the file, and the error lists every
    bad row rather than the first, so an export is fixed in one pass.
    """
    reader = csv.DictReader(lines)
    header = tuple(field.strip() for field in (reader.fieldnames or ()))
    missing = [column for column in COLUMNS if column not in header]
    if missing:
        raise ReplayFileError(
            f"{name}: the header must name {', '.join(COLUMNS)}; missing {', '.join(missing)}"
        )

    problems: list[str] = []
    signals: list[Signal] = []
    seen: set[tuple[datetime, str, str, float, str]] = set()
    for row in reader:
        line = reader.line_num
        cells = {key.strip(): (value or "").strip() for key, value in row.items() if key}
        empty = [column for column in COLUMNS if not cells.get(column)]
        if empty:
            problems.append(f"{name}:{line}: empty {', '.join(empty)}")
            continue
        try:
            timestamp = datetime.fromisoformat(cells["timestamp"])
        except ValueError:
            problems.append(f"{name}:{line}: timestamp {cells['timestamp']!r} is not ISO 8601")
            continue
        if timestamp.tzinfo is None:
            problems.append(
                f"{name}:{line}: timestamp {cells['timestamp']!r} has no UTC offset; "
                "write it as 2026-03-02T06:00:00+07:00"
            )
            continue
        try:
            value = float(cells["value"])
        except ValueError:
            problems.append(f"{name}:{line}: value {cells['value']!r} is not a number")
            continue
        if value != value or value in (float("inf"), float("-inf")):
            problems.append(f"{name}:{line}: value {cells['value']!r} is not a finite number")
            continue

        key = (timestamp, cells["machine_id"], cells["metric_name"], value, cells["unit"])
        if key in seen:
            continue
        seen.add(key)
        signals.append(
            Signal(
                timestamp=timestamp,
                machine_id=MachineId(cells["machine_id"]),
                metric_name=cells["metric_name"],
                value=value,
                unit=cells["unit"],
            )
        )

    if problems:
        shown = problems[:20]
        more = f"\n... and {len(problems) - len(shown)} more" if len(problems) > len(shown) else ""
        raise ReplayFileError("\n".join(shown) + more)
    if not signals:
        raise ReplayFileError(f"{name}: no signals in the file")

    # Stable, so two readings at one instant keep the order the file gave them.
    signals.sort(key=lambda signal: signal.timestamp)
    return signals


class ReplaySource:
    """A file of signals, read once. Implements `SignalSource`.

    Nothing is restarted when the file ends. Replaying history that already
    raised findings would raise them again (ADR-044 §4).
    """

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def stream(self) -> Iterator[Signal]:
        text = self._path.read_text(encoding="utf-8-sig")
        yield from parse(io.StringIO(text, newline=""), name=self._path.name)

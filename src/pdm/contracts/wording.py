"""The words a person on the floor reads, in one place (ADR-093).

Every sentence a technician, shift lead or operator sees is Thai, because the
people using this system read Thai. Code, logs and identifiers stay English.
This module holds the shared vocabulary - severity, load, durations, times -
so that `work/` and `dispatch/` phrase the same thing the same way.

Pure and standard-library only, because `contracts/` may import nothing else.
Times are always shown on the plant's clock, never UTC and never the device's:
a technician compares them with the clock on the wall.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from decimal import Decimal, InvalidOperation

SEVERITY = {
    "critical": "วิกฤต",
    "high": "สูง",
    "medium": "ปานกลาง",
    "low": "ต่ำ",
}

BAND = {
    "light": "งานเบา",
    "normal": "งานปกติ",
    "heavy": "งานล้น",
    "no_capacity": "ไม่มีช่างในกะ",
}

_MONTHS = (
    "ม.ค.",
    "ก.พ.",
    "มี.ค.",
    "เม.ย.",
    "พ.ค.",
    "มิ.ย.",
    "ก.ค.",
    "ส.ค.",
    "ก.ย.",
    "ต.ค.",
    "พ.ย.",
    "ธ.ค.",
)


def duration(minutes: float) -> str:
    """ "2 ชม. 15 นาที". Rounded to the minute: an estimate claims no more."""
    total = max(0, int(minutes))
    hours, rest = divmod(total, 60)
    if hours and rest:
        return f"{hours} ชม. {rest} นาที"
    if hours:
        return f"{hours} ชม."
    return f"{rest} นาที"


def span(interval: timedelta) -> str:
    return duration(interval.total_seconds() / 60)


@dataclass(frozen=True)
class Wording:
    """What a sentence needs from the plant: its clock and its names.

    The defaults (UTC, no names) exist so that a caller with no configuration -
    the simulator, a unit test - still gets a readable sentence. Every service
    that writes to a screen passes `Config.wording()`.
    """

    timezone: tzinfo = UTC
    symptom_titles: Mapping[str, str] = field(default_factory=dict)
    skill_names: Mapping[str, str] = field(default_factory=dict)

    def symptom(self, code: str) -> str:
        # Falling back to the code is honest: a missing title shows as a code,
        # which somebody will notice and name, rather than as an invented phrase.
        return self.symptom_titles.get(code) or f"อาการรหัส {code}"

    def skill(self, skill: str) -> str:
        return self.skill_names.get(skill) or skill

    def clock(self, at: datetime) -> str:
        """ "14:05 น." on the plant's clock."""
        return f"{at.astimezone(self.timezone):%H:%M} น."

    def day(self, at: datetime) -> str:
        """ "27 ก.ย. 2026"."""
        local = at.astimezone(self.timezone)
        return f"{local.day} {_MONTHS[local.month - 1]} {local.year}"

    def day_and_clock(self, at: datetime) -> str:
        """ "27 ก.ย. 14:05 น."."""
        local = at.astimezone(self.timezone)
        return f"{local.day} {_MONTHS[local.month - 1]} {local:%H:%M} น."


# A numeric literal: digits, optional thousands separators, optional decimal
# part. "5-60" is two figures rather than one, because a hyphen between numbers
# is a range in a manual and never a subtraction.
_FIGURE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def figures(text: str) -> frozenset[Decimal]:
    """Every numeric literal in the text, normalised for comparison.

    `1,200` and `1200` are one figure; so are `42` and `42.0`. Nothing here tries
    to tell a torque value from a part number: `TP-1` yields 1, and that is
    deliberate. Counting more things as figures can only make a check that uses
    this stricter, never looser. Here because both the drafting gate (ADR-037)
    and the check on a Thai rendering (ADR-095) use it, and `contracts/` is the
    one place both may import.
    """
    found: set[Decimal] = set()
    for token in _FIGURE.findall(text):
        try:
            found.add(Decimal(token.replace(",", "")).normalize())
        except InvalidOperation:  # pragma: no cover - the pattern cannot produce one
            continue
    return frozenset(found)

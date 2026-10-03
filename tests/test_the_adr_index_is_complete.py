"""Every decision record is in the index, and the index names no record that
is not there.

`docs/adr/README.md` is where the report sends a reader who wants the design
rationale. It had stopped at ADR-105 while twenty more records landed, so a
reader following that pointer missed every decision made in the last week of
the project - including the ones that changed the scheduling results.
"""

from __future__ import annotations

import re
from pathlib import Path

ADR = Path(__file__).resolve().parent.parent / "docs" / "adr"


def _records() -> set[str]:
    return {path.name for path in ADR.glob("[0-9][0-9][0-9][0-9]-*.md")}


def _indexed() -> list[str]:
    index = (ADR / "README.md").read_text(encoding="utf-8")
    return re.findall(r"^\| \[\d{3}\]\(([^)]+)\)", index, re.MULTILINE)


def test_every_record_is_indexed() -> None:
    missing = sorted(_records() - set(_indexed()))
    assert not missing, f"not in docs/adr/README.md: {missing}"


def test_the_index_names_only_records_that_exist() -> None:
    assert not sorted(set(_indexed()) - _records())


def test_the_index_is_in_order_and_lists_each_once() -> None:
    listed = _indexed()
    assert listed == sorted(set(listed))

"""The evaluation set's answer key agrees with its manuals (ADR-096).

An answer key that is wrong measures nothing, and the failure is silent: the
pipeline gets marked down for being right.
"""

from __future__ import annotations

from decimal import Decimal

from pypdf import PdfReader

from fixtures.evalset import EVALSET, EVALSET_DIR
from fixtures.evalset.pages import MANUALS
from pdm.contracts.wording import figures


def _pages(filename: str) -> list[str]:
    return [page.extract_text() for page in PdfReader(EVALSET_DIR / filename).pages]


def test_every_manual_in_the_key_is_a_manual_in_the_pages() -> None:
    assert {m.filename for m in MANUALS} == {d.filename for d in EVALSET.documents}


def test_an_absent_symptom_is_absent_from_every_page() -> None:
    text = " ".join(" ".join(_pages(d.filename)) for d in EVALSET.documents).lower()
    for entry in EVALSET.absent:
        for phrase in entry.forbidden_phrases:
            assert phrase.lower() not in text, f"{entry.symptom_code}: {phrase!r} is in the corpus"


def test_every_correct_figure_is_on_an_answer_page() -> None:
    for entry in EVALSET.covered:
        document = EVALSET.document(entry.machine_model)
        pages = _pages(document.filename)
        on_answer = set().union(*(figures(pages[page - 1]) for page in entry.answer_pages))
        for name, value in entry.correct_figures.items():
            wanted = value if isinstance(value, list) else [value]
            for one in wanted:
                assert Decimal(str(one)).normalize() in on_answer, f"{entry.symptom_code} {name}"


def test_both_splits_have_every_kind_of_entry() -> None:
    for split in ("dev", "test"):
        assert any(e.split == split for e in EVALSET.covered)
        assert any(e.split == split for e in EVALSET.documented_without_procedure)
        assert any(e.split == split for e in EVALSET.absent)

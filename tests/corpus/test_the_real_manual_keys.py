"""The answer keys for real manuals hold together without the manuals (ADR-098, ADR-143).

The PDFs are the owner's samples and stay outside git, so nothing here can read
a page. What can be checked is the key itself: a page outside the manual, a
symptom code used twice or an answer page the key also calls never-an-answer is
a measurement that marks the pipeline down for being right.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.corpus.answers import Corpus, load

KEYS = [Path("fixtures/realdocs/manifest.yaml"), Path("fixtures/realdocs2/manifest.yaml")]


@pytest.fixture(params=KEYS, ids=lambda path: path.parent.name)
def key(request: pytest.FixtureRequest) -> Corpus:
    return load(request.param)


def test_every_entry_is_test_split(key: Corpus) -> None:
    """Written before the pipeline ran on the manuals, so nothing was tuned on it."""
    for group in (key.covered, key.documented_without_procedure, key.absent):
        assert all(entry.split == "test" for entry in group)


def test_symptom_codes_are_unique(key: Corpus) -> None:
    codes = [
        entry.symptom_code
        for group in (key.covered, key.documented_without_procedure, key.absent)
        for entry in group
    ]
    assert len(codes) == len(set(codes))


def test_every_page_is_inside_its_manual(key: Corpus) -> None:
    for entry in key.covered:
        size = key.document(entry.machine_model).pages
        assert all(0 < page <= size for page in (*entry.answer_pages, *entry.supporting_pages))
    for documented in key.documented_without_procedure:
        size = key.document(documented.machine_model).pages
        assert all(0 < page <= size for page in documented.pages)


def test_no_answer_page_is_also_never_an_answer(key: Corpus) -> None:
    never = {(ref.document, ref.page) for ref in key.never_an_answer}
    for entry in key.covered:
        filename = key.document(entry.machine_model).filename
        assert not any((filename, page) in never for page in entry.answer_pages)
    for documented in key.documented_without_procedure:
        filename = key.document(documented.machine_model).filename
        assert not any((filename, page) in never for page in documented.pages)


def test_the_second_set_asks_for_repairs() -> None:
    """Unlike the first, two of its manuals prescribe field repair, so a repair
    draft is an outcome it can reward and not only a hazard it can count."""
    assert load(KEYS[1]).covered

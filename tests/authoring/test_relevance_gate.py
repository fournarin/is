"""ADR-097: a page the reranker scores below the floor is not evidence."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from pdm.authoring.service import Drafting
from pdm.contracts import DocumentId, MachineModel
from pdm.llm.domain import Evidence
from pdm.llm.extractive import ExtractiveDrafter
from pdm.retrieval.service import HybridSearch, Profile


class Fixed:
    def __init__(self, scores: Sequence[float]) -> None:
        self.scores = list(scores)

    def relevance(self, question: str, texts: Sequence[str]) -> list[float]:
        return self.scores[: len(texts)]


def _page(number: int, score: float) -> Evidence:
    return Evidence(
        document_id=DocumentId("a" * 64),
        page=number,
        text=f"page {number} text",
        title="manual",
        machine_model=MachineModel("R-2000iC"),
        score=score,
    )


def _drafting(scores: Sequence[float]) -> Drafting:
    profile = Profile(
        candidates=10, min_score=0.2, abstain=False, same_model_only=False, min_relevance=0.1
    )
    return Drafting(
        cast(HybridSearch, cast(Any, None)),
        ExtractiveDrafter(),
        profile=profile,
        skills=(),
        reranker=Fixed(scores),
    )


def test_pages_below_the_floor_are_dropped_and_the_rest_rescored() -> None:
    kept = _drafting([0.9, 0.05, 0.4])._relevant("q", (_page(3, 1.0), _page(4, 1.0), _page(5, 0.9)))

    assert [(page.page, page.score) for page in kept] == [(3, 0.9), (5, 0.4)]


def test_when_nothing_clears_the_floor_there_is_no_evidence() -> None:
    kept = _drafting([0.0, 0.001])._relevant("q", (_page(3, 1.0), _page(4, 1.0)))

    assert kept == ()


class ByQuestion:
    """Scores by what is asked: the question passes every page, the symptom only
    the pages named for it."""

    def __init__(self, symptom: str, about: set[int]) -> None:
        self.symptom = symptom
        self.about = about

    def relevance(self, question: str, texts: Sequence[str]) -> list[float]:
        if question != self.symptom:
            return [0.9] * len(texts)
        return [0.8 if int(text.split()[1]) in self.about else 0.01 for text in texts]


def _about(symptom: str, about: set[int]) -> Drafting:
    drafting = _drafting(())
    drafting.reranker = ByQuestion(symptom, about)
    return drafting


def test_a_page_that_answers_the_question_and_not_the_symptom_is_dropped() -> None:
    """ADR-121: "85 องศา" typed for the safety interlock found the belt-motor page."""
    pages = (_page(4, 0.9), _page(11, 0.5))

    kept = _about("interlock open", {11})._about("interlock open", pages)

    assert [page.page for page in kept] == [11]


def test_the_symptom_filters_and_keeps_the_questions_scores() -> None:
    pages = (_page(4, 0.9), _page(7, 0.5))

    kept = _about("belt motor hot", {4, 7})._about("belt motor hot", pages)

    assert [(page.page, page.score) for page in kept] == [(4, 0.9), (7, 0.5)]

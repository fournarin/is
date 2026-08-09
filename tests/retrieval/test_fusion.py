"""Reciprocal rank fusion (ADR-035). Pure, no database and no model.

This is where the bugs in hybrid retrieval live. The two halves are each
straightforward - a text search and a vector search - and the interesting
behaviour is entirely in how their disagreements are resolved, which is a
function of two lists and nothing else. So it is tested exhaustively here,
where no download and no service is in the way.

What these tests do **not** show is whether hybrid retrieval is better than word
search. That needs the real model and is measured separately (ADR-035).
"""

from __future__ import annotations

import pytest

from pdm.contracts import DocumentId
from pdm.retrieval.domain import RRF_K, Chunk, FusedHit, fuse

DOCUMENT = DocumentId("a" * 64)
OTHER = DocumentId("b" * 64)


def _chunk(page: int, ordinal: int = 0, document: DocumentId = DOCUMENT) -> Chunk:
    return Chunk(document_id=document, page=page, ordinal=ordinal, text=f"page {page}.{ordinal}")


def _pages(hits: list[FusedHit]) -> list[int]:
    return [hit.chunk.page for hit in hits]


class TestAgreementWins:
    def test_a_chunk_both_halves_found_beats_one_either_found_alone(self) -> None:
        """The whole reason for fusing rather than concatenating. Neither half
        is trusted over the other, so what carries weight is the two of them
        arriving at the same page from different directions."""
        sparse = [_chunk(1), _chunk(2), _chunk(3)]
        dense = [_chunk(3), _chunk(4), _chunk(5)]

        assert _pages(fuse([sparse, dense]))[0] == 3

    def test_first_in_both_scores_the_maximum(self) -> None:
        """The scale is anchored so a threshold means something. 1.0 is "every
        half ranked this first", which is what makes the abstain gate in
        policy.yaml a number a person can reason about (ADR-035)."""
        top = fuse([[_chunk(7)], [_chunk(7)]])[0]

        assert top.score == pytest.approx(1.0)
        assert top.found_by_both

    def test_a_chunk_only_one_half_found_still_appears(self) -> None:
        """Recall first at authoring (ADR-015): the meaning search finding a
        page the word search missed is the case hybrid retrieval exists for, and
        dropping it would defeat the point."""
        fused = fuse([[_chunk(1)], [_chunk(9)]])

        assert set(_pages(fused)) == {1, 9}
        assert all(not hit.found_by_both for hit in fused)


class TestTheRanksAreKept:
    def test_each_hit_records_where_each_half_put_it(self) -> None:
        """ "Why is this first" has to be answerable. A hit the word search put
        third and the meaning search put first is different evidence from one
        only the meaning search saw, and a reviewer judging a drafted step is
        entitled to know which they have."""
        sparse = [_chunk(1), _chunk(2), _chunk(3)]
        dense = [_chunk(3), _chunk(1)]

        by_page = {hit.chunk.page: hit for hit in fuse([sparse, dense])}

        assert by_page[1].ranks == (1, 2)
        assert by_page[2].ranks == (2, None)
        assert by_page[3].ranks == (3, 1)

    def test_the_rank_tuple_matches_the_order_the_rankings_were_given_in(self) -> None:
        fused = fuse([[], [_chunk(4)]])

        assert fused[0].ranks == (None, 1)


class TestDeterminism:
    def test_the_same_inputs_always_give_the_same_order(self) -> None:
        """The eval compares one run against another. Ties resolved by
        dictionary order would make a rank change without any input changing,
        and the comparison would be measuring nothing."""
        sparse = [_chunk(1), _chunk(2)]
        dense = [_chunk(2), _chunk(1)]

        assert [hit.model_dump() for hit in fuse([sparse, dense])] == [
            hit.model_dump() for hit in fuse([sparse, dense])
        ]

    def test_ties_are_broken_by_identity_not_by_insertion(self) -> None:
        """Pages 1 and 2 are ranked 1 and 2 by opposite halves, so they score
        identically. The order between them has to come from somewhere stable."""
        forwards = fuse([[_chunk(1), _chunk(2)], [_chunk(2), _chunk(1)]])
        backwards = fuse([[_chunk(2), _chunk(1)], [_chunk(1), _chunk(2)]])

        assert _pages(forwards) == _pages(backwards) == [1, 2]
        assert forwards[0].score == pytest.approx(forwards[1].score)


class TestIdentity:
    def test_two_chunks_on_one_page_are_not_the_same_chunk(self) -> None:
        """Identity is (document, page, ordinal). Matching on page alone would
        make the second chunk of a page vote for the first."""
        fused = fuse([[_chunk(4, ordinal=0)], [_chunk(4, ordinal=1)]])

        assert len(fused) == 2
        assert all(not hit.found_by_both for hit in fused)

    def test_the_same_page_of_two_manuals_is_two_chunks(self) -> None:
        """The wrong-model candidate is the one ADR-015 says reviewers miss.
        Fusing it with the right one would hide it completely."""
        fused = fuse([[_chunk(4)], [_chunk(4, document=OTHER)]])

        assert len(fused) == 2

    def test_a_half_that_returns_a_duplicate_votes_once(self) -> None:
        """Otherwise a repeat inside one list outweighs agreement between two,
        and the half with a bug in it wins the ranking."""
        duplicated = fuse([[_chunk(1), _chunk(1)], [_chunk(2)]])

        by_page = {hit.chunk.page: hit for hit in duplicated}
        assert by_page[1].ranks == (1, None)
        assert by_page[1].score == pytest.approx(by_page[2].score)


class TestEdges:
    def test_no_rankings_at_all(self) -> None:
        assert fuse([]) == []

    def test_every_half_empty(self) -> None:
        assert fuse([[], []]) == []

    def test_one_half_empty_leaves_the_other_intact(self) -> None:
        """The case that happens for real: a Thai question with no number in it
        returns nothing from the word half (ADR-034), and the meaning half is
        then carrying the whole query."""
        fused = fuse([[], [_chunk(1), _chunk(2)]])

        assert _pages(fused) == [1, 2]
        assert fused[0].score > fused[1].score

    def test_three_halves_would_also_work(self) -> None:
        """Nothing in the fusion assumes there are two. A reranker or a third
        source is a third list, not a rewrite."""
        fused = fuse([[_chunk(1)], [_chunk(1)], [_chunk(1)]])

        assert fused[0].score == pytest.approx(1.0)

    def test_the_decay_constant_behaves_as_published(self) -> None:
        """At k=60 the difference between first and tenth is small, which is the
        property that makes agreement matter more than either half's confidence.
        Left at the published default rather than tuned against nineteen chunks
        of synthetic manual."""
        first = 1.0 / (RRF_K + 1)
        tenth = 1.0 / (RRF_K + 10)

        assert tenth / first > 0.85

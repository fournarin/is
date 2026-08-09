"""What the index holds, with no I/O (ADR-030 layering).

A chunk is a piece of one page of one document. It is never more than that:
per-step provenance is `(source_doc, page)`, and a chunk spanning a page break
has no single page to cite, so a technician told "page 4" would open a page that
does not contain the step (ADR-034).

The index is derived data. Documents are the record; chunks are a projection of
them that can be rebuilt by re-ingesting, which is what makes it safe to delete
them when a manual is withdrawn while the file itself is never touched
(ADR-019).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import DocumentId, MachineModel

# The constant from the reciprocal rank fusion paper. It sets how quickly the
# contribution of a rank decays: at 60, being first is worth 1/61 and being
# tenth 1/70, so a hit both halves agree on beats one that either half loves
# alone. Left at the published default rather than tuned, because tuning it
# against nineteen chunks of synthetic manual would be fitting noise.
RRF_K = 60

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class PageOutcome(StrEnum):
    """What a page gave up when it was read.

    Recorded for every page, including the ones that gave nothing. A parser
    handed a scan returns an empty string and no error, so a pipeline that
    skipped those would ingest a real manual, index none of it, and report
    success (ADR-034).
    """

    TEXT = "text"
    # Nothing at all - almost always a scan, which is what the plant's manuals
    # are. This count is what decides whether a document needs OCR before the
    # system can answer anything about it.
    NO_TEXT = "no_text"
    # A few characters: a figure number, a drawing with a caption. Also a page
    # whose only text was the running header, which is furniture. Not worth
    # indexing, and not evidence of a scan either.
    TOO_LITTLE_TEXT = "too_little_text"
    # The parser failed on this page alone. Kept apart from NO_TEXT because the
    # answers differ: a scan needs OCR, a damaged page needs a new copy of the
    # file, and telling an operator to OCR a corrupt page wastes the one thing
    # they can actually do about it.
    UNREADABLE = "unreadable"


class IndexedPage(BaseModel):
    """One page of a document as the index knows it, readable or not."""

    model_config = _FROZEN

    document_id: DocumentId
    page: int = Field(gt=0)
    outcome: PageOutcome
    characters: int = Field(ge=0)

    @property
    def needs_ocr(self) -> bool:
        return self.outcome is PageOutcome.NO_TEXT


class Chunk(BaseModel):
    """A searchable piece of one page.

    `ordinal` orders the chunks within their page, so a citation can be resolved
    back to a position rather than only to a page, and so re-ingesting a
    document produces the same rows in the same order.
    """

    model_config = _FROZEN

    document_id: DocumentId
    page: int = Field(gt=0)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)

    @property
    def key(self) -> ChunkKey:
        """Identity across the two halves of retrieval.

        The vector store knows a chunk by a point id and PostgreSQL by a row id,
        and neither is the other. What both can reproduce from what they hold is
        this triple, so it is what fusion matches on.
        """
        return (self.document_id, self.page, self.ordinal)


ChunkKey = tuple[str, int, int]


class SearchHit(BaseModel):
    """A chunk that matched, with everything needed to show it to a person.

    Carries the document's title and machine model because the review screen has
    to make "this candidate is from the other model" impossible to miss - the
    mistake ADR-015 says reviewers are worst at catching - and a hit that only
    knows its document id cannot say so.
    """

    model_config = _FROZEN

    chunk: Chunk
    score: float
    title: str
    machine_model: MachineModel


class FusedHit(BaseModel):
    """One chunk after both halves have voted, with how each half ranked it.

    `ranks` is kept because "why is this first" has to be answerable. A hit that
    the word search put third and the meaning search put first is a different
    kind of evidence from one only the meaning search found at all, and the
    reviewer deciding whether to trust a drafted step is entitled to know which
    they are looking at (ADR-005's reasoning, one layer down).
    """

    model_config = _FROZEN

    chunk: Chunk
    # 0.0 to 1.0. Bounded on purpose: the sparse half's own score is unbounded,
    # which is why the abstain thresholds in policy.yaml could not be applied to
    # it. Fused, they can be (ADR-035).
    score: float = Field(ge=0.0, le=1.0)
    # Position in each input ranking, 1-based, None where that half did not
    # return it at all. Same order as the rankings passed to fuse().
    ranks: tuple[int | None, ...]

    @property
    def found_by_both(self) -> bool:
        return all(rank is not None for rank in self.ranks)


def fuse(rankings: Sequence[Sequence[Chunk]], *, k: int = RRF_K) -> list[FusedHit]:
    """Reciprocal rank fusion: combine ranked lists using positions, not scores.

    The two halves cannot be combined any other way without inventing a
    constant. `ts_rank_cd` is unbounded and grows with term frequency; cosine
    similarity sits in [-1, 1] and is dense around 0.8 for anything
    topically related. Any weighted sum of the two is a number that means
    something different the moment either side is retuned, and nobody would
    notice it had changed meaning.

    Ranks throw the magnitudes away. What survives is the only comparable thing
    the two halves produce - that one of them put this chunk above that one -
    and agreement between them is what the sum rewards.

    The result is divided by the best score achievable, so it lands in [0, 1]
    with 1.0 meaning every half ranked it first. That is what lets the abstain
    threshold in policy.yaml be a number a person can reason about instead of a
    property of the ranking function.
    """
    if not rankings:
        return []

    by_key: dict[ChunkKey, Chunk] = {}
    positions: dict[ChunkKey, list[int | None]] = {}
    total: dict[ChunkKey, float] = {}

    for index, ranking in enumerate(rankings):
        seen: set[ChunkKey] = set()
        for position, chunk in enumerate(ranking, start=1):
            key = chunk.key
            # A half that returns the same chunk twice votes once. Otherwise a
            # duplicate in one list outweighs agreement between two.
            if key in seen:
                continue
            seen.add(key)

            by_key.setdefault(key, chunk)
            positions.setdefault(key, [None] * len(rankings))[index] = position
            total[key] = total.get(key, 0.0) + 1.0 / (k + position)

    best_possible = len(rankings) / (k + 1)

    hits = [
        FusedHit(
            chunk=by_key[key],
            score=score / best_possible,
            ranks=tuple(positions[key]),
        )
        for key, score in total.items()
    ]
    # Ties broken by position rather than left to dictionary order, so the same
    # inputs always produce the same output - the property the eval depends on.
    hits.sort(
        key=lambda hit: (-hit.score, hit.chunk.document_id, hit.chunk.page, hit.chunk.ordinal)
    )
    return hits

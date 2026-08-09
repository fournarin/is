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

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import DocumentId, MachineModel

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

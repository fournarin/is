"""PDF bytes to page text (ADR-034).

The only module that knows what a PDF is. Everything downstream works on
`PageText`, so adding OCR or a vision model for scanned pages is a second stage
here rather than a change to chunking, indexing or provenance.

A page that yields nothing is the case this module exists to make visible. The
corpus is generated text and any parser reads it; the plant's manuals are scans,
and a text parser handed a scan returns an empty string with no error. Reporting
that as a page rather than dropping it is what stops the pipeline from ingesting
a real manual, indexing nothing, and looking healthy (ADR-034 point 3).
"""

from __future__ import annotations

import re
from io import BytesIO
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from pdm.retrieval.domain import PageOutcome

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Fewer characters than this and the page carries no sentence worth indexing -
# a divider, a photograph with a caption, a page holding only a figure number.
# Distinguished from a page with nothing at all because the two have different
# answers: one may need OCR, the other is genuinely blank.
_MINIMUM_USEFUL_CHARACTERS = 20


class PageText(BaseModel):
    """One page as the rest of the pipeline sees it."""

    model_config = _FROZEN

    # 1-based, matching what is printed on the page and what a citation names.
    page: int = Field(gt=0)
    text: str
    outcome: PageOutcome

    @property
    def is_indexable(self) -> bool:
        return self.outcome is PageOutcome.TEXT


class ParsedDocument(BaseModel):
    """Every page of a document, including the ones that produced nothing.

    Coverage is on the object rather than computed by callers because it is the
    number ADR-034 requires to travel with any retrieval figure measured on real
    manuals: "the pipeline works" is only true for the fraction of pages that
    produced text.
    """

    model_config = _FROZEN

    pages: tuple[PageText, ...]

    @property
    def indexable(self) -> tuple[PageText, ...]:
        return tuple(page for page in self.pages if page.is_indexable)

    @property
    def coverage(self) -> float:
        """Fraction of pages that produced text, 0.0 to 1.0.

        A document of no pages is 0.0 rather than an error: an empty PDF is a
        real thing an operator can upload, and it should read as covering
        nothing rather than crash the job.
        """
        if not self.pages:
            return 0.0
        return len(self.indexable) / len(self.pages)

    def counts(self) -> dict[PageOutcome, int]:
        return {
            outcome: sum(1 for page in self.pages if page.outcome is outcome)
            for outcome in PageOutcome
        }


class UnreadableDocument(Exception):
    """The file is not a PDF, or is damaged beyond the parser's tolerance.

    Distinct from a PDF whose pages produce no text: that one is ingested with
    its coverage recorded, because it is the ordinary case for a scan. This one
    means the bytes are not a document at all, and the job should fail rather
    than record a manual of zero readable pages.
    """


# Rejoins a word broken across a line: "cali-" / "brate". Both sides must be
# letters and the continuation must be lowercase, because the obvious version -
# any word character - silently destroys figures: "torque to 20-\n25 Nm" became
# "2025 Nm", a number that is not in the manual, on a page whose citation still
# points at the right place. In a document whose whole purpose is torque values
# and thresholds, that is the most damaging thing this module could do.
_HYPHENATED_ACROSS_LINES = re.compile(r"(?<=[A-Za-z])-\n(?=[a-z])")


def _normalise(raw: str) -> str:
    """Collapse the whitespace a PDF extractor invents.

    Text laid out in columns and boxes comes back with runs of spaces and
    newlines that reflect the page geometry rather than the sentences. Left
    alone they end up inside the indexed text and inside the quoted evidence on
    the review screen, where they read as though the manual itself were badly
    typeset.

    Spaces are collapsed before words are rejoined, not after: extractors that
    leave a space before the line break turn "cali- \nbrate" into something the
    rejoin never sees.
    """
    tidied = "\n".join(re.sub(r"[ \t]+", " ", line).rstrip() for line in raw.splitlines())
    lines = [line.strip() for line in _HYPHENATED_ACROSS_LINES.sub("", tidied).splitlines()]
    # Blank lines are kept as paragraph separators - chunking needs them - but
    # runs of them collapse to one.
    collapsed: list[str] = []
    for line in lines:
        if line or (collapsed and collapsed[-1]):
            collapsed.append(line)
    return "\n".join(collapsed).strip()


def _classify(text: str) -> PageOutcome:
    if not text:
        return PageOutcome.NO_TEXT
    if len(text) < _MINIMUM_USEFUL_CHARACTERS:
        return PageOutcome.TOO_LITTLE_TEXT
    return PageOutcome.TEXT


def parse(source: BinaryIO | bytes) -> ParsedDocument:
    """Read every page, including the ones that give nothing back.

    Takes a stream so that a document can be parsed straight out of the object
    store without being copied into memory first - the reader itself still needs
    random access, but nothing above this line has to hold the bytes.
    """
    handle = BytesIO(source) if isinstance(source, bytes) else source
    try:
        reader = PdfReader(handle)
        page_objects = list(reader.pages)
    except PdfReadError as error:
        raise UnreadableDocument(str(error)) from error
    except Exception as error:  # pypdf raises assorted exceptions on damaged files
        raise UnreadableDocument(f"{type(error).__name__}: {error}") from error

    pages: list[PageText] = []
    for number, page_object in enumerate(page_objects, start=1):
        # Per page, not once for the document. A single damaged page used to
        # fail the whole manual, so 199 readable pages of a 200-page scan
        # indexed to nothing and the result was indistinguishable from "this is
        # not a PDF" - the inverse of what ADR-034 point 3 is for.
        try:
            raw = page_object.extract_text() or ""
        except Exception:
            pages.append(PageText(page=number, text="", outcome=PageOutcome.UNREADABLE))
            continue
        text = _normalise(raw)
        pages.append(PageText(page=number, text=text, outcome=_classify(text)))

    return ParsedDocument(pages=tuple(pages))

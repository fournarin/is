"""Page text to chunks. Pure, no I/O (ADR-030 layering).

Two rules shape everything here.

**A chunk never crosses a page boundary** (ADR-034). Per-step provenance is
`(source_doc, page)`; a chunk spanning a break has no single page to cite, so a
technician told "page 4" would open a page that does not contain the step. The
cost is worse retrieval on procedures that run across a break, and the answer to
that is overlap *within* a page, never a chunk that spans two.

**Running headers and footers are removed before indexing.** Every page of a
manual repeats its title, and left in place that phrase is in every chunk: a
search for the machine model then matches all of them equally and the index is
worth less than the pages it came from.

Sizes are constants here rather than configuration. Nothing tunes them yet, and
`policy.yaml` is a contract whose entries are meant to have a consumer
(lessons_carried.md 4.4). If the eval in a later slice wants them tuned, that is
when they move.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from pdm.authoring.parsing import PageText
from pdm.contracts import DocumentId
from pdm.retrieval.domain import Chunk

# Around a paragraph or two of a manual. Long enough to hold a whole numbered
# step with its torque figure, short enough that a hit points at something a
# reviewer can read in one glance rather than a page to search through.
TARGET_CHARACTERS = 800

# Below this a chunk is joined to the one before it, if they share a page. A
# stray fragment retrieves badly and reads as noise on the review screen.
MINIMUM_CHARACTERS = 120

# A line has to appear on more than this fraction of a document's pages to count
# as furniture. Two-page documents are excluded from the whole mechanism by the
# page floor below, because on two pages "appears on most pages" means "appears
# twice" and that is a coincidence rather than a header.
_FURNITURE_FRACTION = 0.5
_FURNITURE_MINIMUM_PAGES = 3

# Furniture is short. A repeated paragraph is a safety warning printed on every
# page, and removing that would be removing content.
_FURNITURE_MAXIMUM_CHARACTERS = 100

_DIGITS = re.compile(r"\d+")
_SENTENCE_END = re.compile(r"(?<=[.:;])\s+")


def _masked(line: str) -> str:
    """A line with its numbers replaced, so "page 4" and "page 5" are one line.

    Without this, footers are invisible to a frequency count: every page's
    footer is a different string. Masking digits also catches "Page 4 of 200"
    and "Rev C - 2024-06-01", which are the same furniture in other clothes.
    """
    return _DIGITS.sub("#", line)


def running_furniture(pages: Iterable[PageText]) -> frozenset[str]:
    """Masked lines that repeat across most pages: titles, footers, revision
    stamps.

    Returned as masked forms so the caller can test any line by masking it,
    which is what makes a footer with a different number on every page
    removable at all.
    """
    text_pages = [page for page in pages if page.text]
    if len(text_pages) < _FURNITURE_MINIMUM_PAGES:
        return frozenset()

    counts: Counter[str] = Counter()
    for page in text_pages:
        # Once per page, not once per occurrence: a line repeated three times on
        # one page is a list, not a header.
        counts.update(
            {
                _masked(line)
                for line in page.text.splitlines()
                if line and len(line) <= _FURNITURE_MAXIMUM_CHARACTERS
            }
        )

    threshold = len(text_pages) * _FURNITURE_FRACTION
    return frozenset(line for line, count in counts.items() if count > threshold)


def strip_furniture(text: str, furniture: frozenset[str]) -> str:
    kept = [line for line in text.splitlines() if _masked(line) not in furniture]
    return "\n".join(kept).strip()


def _paragraphs(text: str) -> list[str]:
    return [block.strip() for block in re.split(r"\n\s*\n", text) if block.strip()]


def _split_long(paragraph: str) -> list[str]:
    """Break a paragraph too long to be a chunk, at sentence ends.

    A numbered procedure is often one paragraph of several hundred characters,
    and cutting it mid-sentence puts half a torque figure in one chunk and half
    in the next, which is worse than a chunk slightly over target.
    """
    if len(paragraph) <= TARGET_CHARACTERS:
        return [paragraph]

    pieces: list[str] = []
    current = ""
    for sentence in _SENTENCE_END.split(paragraph):
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > TARGET_CHARACTERS:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_page(text: str) -> list[str]:
    """One page of text as chunks, in reading order.

    Paragraphs are packed up to the target rather than split at a fixed width,
    so a chunk starts and ends where the manual does.
    """
    if not text.strip():
        return []

    packed: list[str] = []
    for paragraph in _paragraphs(text):
        for piece in _split_long(paragraph):
            if packed and len(packed[-1]) + len(piece) + 2 <= TARGET_CHARACTERS:
                packed[-1] = f"{packed[-1]}\n\n{piece}"
            else:
                packed.append(piece)

    return _absorb_fragments(packed)


def _absorb_fragments(chunks: list[str]) -> list[str]:
    """Join anything too short to stand on its own to a neighbour.

    Not only the tail. A page opening with a short line - a heading, "Symptom:",
    a one-clause sentence - was leaving a chunk of a few characters at the
    front, which retrieves on almost any query and tells a reviewer nothing.

    Everything here is already within one page, so no merge can cross a page
    boundary however the fragments fall.
    """
    if len(chunks) < 2:
        return chunks

    merged: list[str] = []
    for chunk in chunks:
        if merged and (len(chunk) < MINIMUM_CHARACTERS or len(merged[-1]) < MINIMUM_CHARACTERS):
            merged[-1] = f"{merged[-1]}\n\n{chunk}"
        else:
            merged.append(chunk)
    return merged


def chunk_document(document_id: DocumentId, pages: Iterable[PageText]) -> list[Chunk]:
    """Every indexable page of a document, chunked, with furniture removed.

    Pages that produced no text yield no chunks and are not silently dropped -
    the caller records them, because how much of a manual could not be read is
    the number that has to travel with any retrieval figure measured on it
    (ADR-034).
    """
    pages = list(pages)
    furniture = running_furniture(pages)

    chunks: list[Chunk] = []
    for page in pages:
        if not page.is_indexable:
            continue
        body = strip_furniture(page.text, furniture)
        for ordinal, text in enumerate(chunk_page(body)):
            chunks.append(
                Chunk(document_id=document_id, page=page.page, ordinal=ordinal, text=text)
            )
    return chunks

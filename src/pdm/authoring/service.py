"""Ingest: a stored document becomes searchable text (ADR-034).

The only module `workers/` calls to index a manual. It opens no connection - the
caller supplies one - so the page records, the chunks and the job that produced
them commit together (ADR-017). A half-indexed manual that reports success is
the failure that ordering prevents.

Runs as an authoring job, never in a request. Parsing a two-hundred-page scan
takes minutes, and ADR-026 exists so that work cannot stall the dispatch tick.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.authoring.domain import chunk_document
from pdm.authoring.parsing import parse
from pdm.contracts import DocumentId
from pdm.platform.documents import Document, DocumentLibrary
from pdm.retrieval import repo as index
from pdm.retrieval.domain import IndexedPage, PageOutcome

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class IngestReport(BaseModel):
    """What one manual gave up, and what it did not.

    Returned rather than logged because coverage is a number the report has to
    carry: on real manuals "the pipeline works" is only true for the fraction of
    pages that produced text, and that fraction belongs beside every retrieval
    figure measured on them (ADR-034).
    """

    model_config = _FROZEN

    document_id: DocumentId
    pages: int
    pages_with_text: int
    chunks: int
    pages_needing_ocr: tuple[int, ...]

    @property
    def coverage(self) -> float:
        return self.pages_with_text / self.pages if self.pages else 0.0

    @property
    def is_fully_readable(self) -> bool:
        return self.pages > 0 and self.pages_with_text == self.pages


def _what_the_index_got(parsed: PageOutcome, produced_chunks: bool) -> PageOutcome:
    """The outcome as the *index* sees it, not as the parser left it.

    A page whose only text is the running header parses as TEXT and then loses
    all of it to furniture stripping, so it produced nothing searchable while
    coverage counted it as read. Coverage is the number that has to travel with
    every retrieval figure measured on a real manual (ADR-034); a version of it
    that counts pages nothing can retrieve would overstate exactly the thing it
    exists to be honest about.
    """
    if parsed is PageOutcome.TEXT and not produced_chunks:
        return PageOutcome.TOO_LITTLE_TEXT
    return parsed


class UnknownDocument(Exception):
    """Asked to ingest something the library has no row for."""


class Ingest:
    """Reads a document out of the library and writes it into the index."""

    def __init__(self, library: DocumentLibrary) -> None:
        self.library = library

    def run(self, conn: Connection[Any], document_id: DocumentId) -> IngestReport:
        """Parse, chunk, index. Replaces whatever was there before.

        Replacing rather than adding is what makes re-ingesting safe after a
        parser change: the alternative leaves the previous parser's chunks in
        place beside the new ones, and a search then returns two versions of the
        same page with no way to tell which is current.
        """
        document = self.library.get(conn, document_id)
        if document is None:
            raise UnknownDocument(f"no document {document_id} in the library")

        with self.library.open(document) as handle:
            parsed = parse(handle)

        chunks = chunk_document(document_id, parsed.pages)
        chunked = {chunk.page for chunk in chunks}

        pages = [
            IndexedPage(
                document_id=document_id,
                page=page.page,
                outcome=_what_the_index_got(page.outcome, page.page in chunked),
                characters=len(page.text),
            )
            for page in parsed.pages
        ]

        index.replace_pages(conn, document_id, pages)
        index.insert_chunks(conn, chunks)

        return IngestReport(
            document_id=document_id,
            pages=len(pages),
            pages_with_text=sum(1 for page in pages if page.outcome is PageOutcome.TEXT),
            chunks=len(chunks),
            pages_needing_ocr=tuple(page.page for page in pages if page.needs_ocr),
        )

    def withdraw(self, conn: Connection[Any], document: Document) -> int:
        """Take a manual out of the index when its edition is withdrawn.

        design.md section 5: the old manual is removed from the index for real
        and the file is kept, because `playbook_snapshot` cites its pages. The
        index is a projection and can be rebuilt; the file is the record.

        Deliberately separate from `DocumentLibrary.withdraw`, which changes the
        row. The library sits in `platform/` and must not know that an index
        exists; joining the two is the caller's job, in one transaction.
        """
        return index.drop_document(conn, document.document_id)

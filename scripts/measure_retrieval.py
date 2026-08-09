"""Measure retrieval against the corpus's answer key (ADR-035).

Run by hand, never by CI:

    DATABASE_URL=... uv run python scripts/measure_retrieval.py

CI does not run this and must not. It needs the embedding model, which is a
download of hundreds of megabytes, and lessons_carried.md 3.6 is explicit that
mixing what needs a big machine into what must pass on every commit ends with a
pipeline nobody reads.

**Write the output into `docs/retrieval-baseline.md` when it changes.** The
number will be quoted in the report, and a figure that exists only in somebody's
terminal history gets quoted from memory. A stale file at least carries a date.

What is measured is the rank of the page the answer key names, per symptom, for
three configurations: the word half alone, the meaning half alone, and the two
fused. The key was written in slice 3.0 before any retriever existed, which is
what makes this a measurement rather than a description.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection, connect

from fixtures.corpus import CORPUS, Answer, DocumentedOnly
from pdm.authoring.service import Ingest
from pdm.contracts import MachineModel, UserId
from pdm.platform.clock import SystemClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.retrieval import repo
from pdm.retrieval.domain import Chunk, fuse
from pdm.retrieval.embedding import OnnxEmbedder
from pdm.retrieval.service import HybridSearch
from pdm.retrieval.vectors import InMemoryVectorIndex

OPERATOR = UserId("measurement")


def _rank_of(pages: list[int], answer_pages: tuple[int, ...]) -> int | None:
    """Rank of the answer *page*, not of the chunk that carried it.

    Ranking the raw hit list counts two chunks of the same page as two places,
    so a page reached second could be published as third. The baseline table
    says "page", and the number under it now means that.
    """
    seen: list[int] = []
    for page in pages:
        if page not in seen:
            seen.append(page)
    for position, page in enumerate(seen, start=1):
        if page in answer_pages:
            return position
    return None


def _load(conn: Connection[Any], hybrid: HybridSearch, root: Path) -> None:
    library = DocumentLibrary(FilesystemObjectStore(root), SystemClock())
    ingest = Ingest(library, hybrid)

    for document in CORPUS.documents:
        row = library.add(
            conn,
            content=document.path.read_bytes(),
            filename=document.filename,
            content_type="application/pdf",
            machine_model=document.machine_model,
            title=document.title,
            uploaded_by=OPERATOR,
            edition=document.edition,
        )
        report = ingest.run(conn, row.document_id)
        print(f"  {document.filename}: {report.chunks} chunks embedded")


def _dense_pages(
    conn: Connection[Any], hybrid: HybridSearch, query: str, model: MachineModel, depth: int
) -> list[Chunk]:
    keys = hybrid.vectors.search(
        hybrid.embedder.embed_query(query), machine_model=model, limit=depth
    )
    by_key = {chunk.key: chunk for chunk in repo.chunks_by_key(conn, keys)}
    return [by_key[key] for key in keys if key in by_key]


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        # This script empties the document table, which is the record of which
        # edition was in force when a work order was issued (ADR-019) and is not
        # derived data. Pointed at a real database it would orphan every blob.
        print(f"refusing to run against {url.rsplit('/', 1)[-1]}: name a *_test database")
        return 1

    print(f"measured {datetime.now(UTC).date().isoformat()}")
    embedder = OnnxEmbedder()
    print(f"model {embedder.model_name}, {embedder.dimensions} dimensions\n")

    hybrid = HybridSearch(embedder, InMemoryVectorIndex())
    conn = connect(url)
    root = Path(tempfile.mkdtemp())
    try:
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()
        _load(conn, hybrid, root)
        conn.commit()

        depth = 8
        rows: list[tuple[str, str, str, str, str]] = []
        entries: list[Answer | DocumentedOnly] = [
            *CORPUS.covered,
            *CORPUS.documented_without_procedure,
        ]
        for entry in entries:
            answer_pages = entry.answer_pages if isinstance(entry, Answer) else entry.pages
            for language, query in (("en", entry.queries.en), ("th", entry.queries.th)):
                sparse = repo.search(conn, query, machine_model=entry.machine_model, limit=depth)
                dense = _dense_pages(conn, hybrid, query, entry.machine_model, depth)
                fused = fuse([[hit.chunk for hit in sparse], dense])

                rows.append(
                    (
                        entry.symptom_code,
                        language,
                        str(_rank_of([hit.chunk.page for hit in sparse], answer_pages)),
                        str(_rank_of([chunk.page for chunk in dense], answer_pages)),
                        str(_rank_of([hit.chunk.page for hit in fused], answer_pages)),
                    )
                )

        print(f"{'symptom':10} {'lang':5} {'sparse':>7} {'dense':>7} {'fused':>7}")
        for row in rows:
            print(f"{row[0]:10} {row[1]:5} {row[2]:>7} {row[3]:>7} {row[4]:>7}")

        # The answer key's questions all contain a threshold figure, which is
        # what let the word half answer a Thai question at all in slice 3.2. A
        # question without one is where the two halves genuinely differ, and it
        # is invisible in the table above.
        print("\n--- questions with no figure in them ---")
        for language, query, model in (
            ("th", "สายพานหลวมต้องทำอย่างไร", MachineModel("R-2000iC")),
            ("th", "พัดลมเสียงดังผิดปกติ", MachineModel("M-710iC")),
            ("en", "the belt feels loose, what should I do", MachineModel("R-2000iC")),
        ):
            sparse = repo.search(conn, query, machine_model=model, limit=depth)
            dense = _dense_pages(conn, hybrid, query, model, depth)
            fused = fuse([[hit.chunk for hit in sparse], dense])
            print(
                f"{language} {query[:34]:36} "
                f"sparse={[h.chunk.page for h in sparse]} "
                f"dense={[c.page for c in dense][:3]} "
                f"fused={[h.chunk.page for h in fused][:3]}"
            )

        found = [row for row in rows if row[4] != "None"]
        firsts = [row for row in rows if row[4] == "1"]
        print(
            f"\nanswer found by fusion: {len(found)}/{len(rows)}   first: {len(firsts)}/{len(rows)}"
        )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

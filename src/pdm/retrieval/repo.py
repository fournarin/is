"""SQL for the index. No business logic, no connections opened here.

Written by ingest, read by everything that has to find a page: the authoring
draft step, the extractive fallback when no playbook exists, and the review
screen's evidence panel.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row

from pdm.contracts import DocumentId, MachineModel
from pdm.retrieval.domain import Chunk, ChunkKey, IndexedPage, PageOutcome, SearchHit


def replace_pages(conn: Connection[Any], document_id: DocumentId, pages: list[IndexedPage]) -> None:
    """Record every page of a document, readable or not.

    Replaces rather than merges: re-ingesting a document with a better parser
    should leave no trace of what the previous one thought, or coverage would
    only ever improve on paper.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunk WHERE document_id = %s", (document_id,))
        cur.execute("DELETE FROM document_page WHERE document_id = %s", (document_id,))
        if not pages:
            return
        cur.executemany(
            """
            INSERT INTO document_page (document_id, page, outcome, characters)
            VALUES (%s, %s, %s, %s)
            """,
            [(page.document_id, page.page, page.outcome.value, page.characters) for page in pages],
        )


def insert_chunks(conn: Connection[Any], chunks: list[Chunk]) -> None:
    """Add chunks for pages already recorded by `replace_pages`."""
    if not chunks:
        return
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO chunk (document_id, page, ordinal, text) VALUES (%s, %s, %s, %s)",
            [(chunk.document_id, chunk.page, chunk.ordinal, chunk.text) for chunk in chunks],
        )


def drop_document(conn: Connection[Any], document_id: DocumentId) -> int:
    """Remove a document from the index. The file is untouched (ADR-019).

    Returns the number of chunks removed, which is what an operator confirming a
    manual change needs to be told before they press the button.
    """
    with conn.cursor() as cur:
        cur.execute("DELETE FROM chunk WHERE document_id = %s", (document_id,))
        removed = cur.rowcount
        cur.execute("DELETE FROM document_page WHERE document_id = %s", (document_id,))
    return removed


def pages_of(conn: Connection[Any], document_id: DocumentId) -> list[IndexedPage]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT document_id, page, outcome, characters
              FROM document_page
             WHERE document_id = %s
             ORDER BY page
            """,
            (document_id,),
        )
        rows = cur.fetchall()
    return [IndexedPage.model_validate(row) for row in rows]


def coverage(conn: Connection[Any], document_id: DocumentId) -> tuple[int, int]:
    """(pages that produced text, pages in total)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*) FILTER (WHERE outcome = 'text'), count(*)
              FROM document_page
             WHERE document_id = %s
            """,
            (document_id,),
        )
        row = cur.fetchone()
    assert row is not None
    return int(row[0]), int(row[1])


def needing_ocr(conn: Connection[Any], document_id: DocumentId) -> list[int]:
    """Page numbers that produced nothing at all - almost always scans."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT page FROM document_page
             WHERE document_id = %s AND outcome = %s
             ORDER BY page
            """,
            (document_id, PageOutcome.NO_TEXT.value),
        )
        rows = cur.fetchall()
    return [int(row[0]) for row in rows]


def chunks_by_key(conn: Connection[Any], keys: Sequence[ChunkKey]) -> list[Chunk]:
    """Fetch chunks the vector half returned by key.

    The vector store holds identity and no text: duplicating the text there
    would give two copies to keep in step, and PostgreSQL is where it lives.
    Order is not preserved - the caller has the ranking and reorders.

    Withdrawn manuals are excluded here as well as in `search`. The vector half
    is cleaned when a document is withdrawn, but the two stores are separate and
    the whole point of filtering in `search` was that the worst case should be a
    stale row rather than a technician sent to a manual out of service - which
    only holds if both routes to a chunk apply it.
    """
    if not keys:
        return []
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT c.document_id, c.page, c.ordinal, c.text
              FROM chunk c
              JOIN document d ON d.document_id = c.document_id
             WHERE d.status = 'active'
               AND (c.document_id, c.page, c.ordinal) IN (
                       SELECT * FROM unnest(%s::text[], %s::int[], %s::int[])
                   )
            """,
            (
                [key[0] for key in keys],
                [key[1] for key in keys],
                [key[2] for key in keys],
            ),
        )
        rows = cur.fetchall()
    return [Chunk.model_validate(row) for row in rows]


def chunks_of(conn: Connection[Any], document_id: DocumentId) -> list[Chunk]:
    """Every chunk of one document, in reading order.

    What the vector half is given to embed after the text half has been
    written - which is the order ADR-035 requires, so a crash between the two
    leaves a chunk the dense half cannot see rather than a vector pointing at
    nothing.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT document_id, page, ordinal, text
              FROM chunk
             WHERE document_id = %s
             ORDER BY page, ordinal
            """,
            (document_id,),
        )
        rows = cur.fetchall()
    return [Chunk.model_validate(row) for row in rows]


def documents_of(
    conn: Connection[Any], document_ids: Sequence[DocumentId]
) -> dict[DocumentId, tuple[str, MachineModel]]:
    """Title and machine model per document, for labelling candidates.

    One query for the whole result set rather than one per hit: the review
    screen shows eight at a time and the difference between one round trip and
    eight is the difference between a screen that opens and one that hesitates.
    """
    if not document_ids:
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT document_id, title, machine_model FROM document WHERE document_id = ANY(%s)",
            (list(set(document_ids)),),
        )
        rows = cur.fetchall()
    return {row["document_id"]: (row["title"], row["machine_model"]) for row in rows}


# plainto_tsquery normalises, stems and drops stopwords, then joins the lexemes
# with AND. Rewriting the operator is the documented way to get OR semantics
# while keeping all of that: the alternative is hand-tokenising the query, which
# means reimplementing the stemmer.
# The operator is replaced with its spaces, not bare. plainto_tsquery renders
# the conjunction as " & " while an ampersand inside a lexeme - a URL, a part
# number - has none, so replacing the bare character rewrote the lexeme itself
# into one no document contains. Silent recall loss with no error.
_ANY_TERM = "replace(plainto_tsquery('english', %s)::text, ' & ', ' | ')::tsquery"


def search(
    conn: Connection[Any],
    query: str,
    *,
    machine_model: MachineModel | None = None,
    limit: int = 8,
) -> list[SearchHit]:
    """Full-text search over the chunks, best first.

    **Any term, not every term.** PostgreSQL's query parsers join words with
    AND, which for a typed question means one absent word removes the answer:
    "cabinet fan slower than 1200 rpm" found nothing at all, because the page
    says "below" where the question says "slower". Recall matters more than
    precision at authoring, where an engineer reviews every candidate (ADR-015),
    so the terms are joined with OR and `ts_rank_cd` decides the order.

    The consequence is that a search almost never comes back empty, so "no
    answer" becomes a decision about score rather than about emptiness. Sparse
    scores are unnormalised, which is why no threshold is applied here: the
    profile in `policy.yaml` belongs after fusion, where the scores mean
    something comparable.

    `ts_rank_cd` weighs how close the matched terms are to each other, which is
    what separates a page that discusses belt tension and motor temperature in
    one procedure from a page that mentions each once, several paragraphs apart.

    Filtering by machine model is a parameter rather than the default: ADR-015
    wants authoring to see across models so a reviewer can be shown a candidate
    from the wrong manual and reject it, while runtime must not serve one.
    """
    # Withdrawn editions are removed from the index by Ingest.withdraw, but
    # DocumentLibrary.withdraw deliberately does not cascade, so a caller that
    # changes the row without touching the index would leave the old manual
    # searchable. Filtering here means the worst case is a stale row rather than
    # a technician served a page from a manual that is out of service.
    clauses = [f"c.search @@ {_ANY_TERM}", "d.status = 'active'"]
    if machine_model is not None:
        clauses.append("d.machine_model = %s")

    # In the order the statement consumes them: rank, filter, model, limit. The
    # query text appears twice because it is used for both scoring and matching.
    parameters: list[object] = [query, query]
    if machine_model is not None:
        parameters.append(machine_model)
    parameters.append(limit)

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            f"""
            SELECT c.document_id, c.page, c.ordinal, c.text,
                   ts_rank_cd(c.search, {_ANY_TERM}) AS score,
                   d.title, d.machine_model
              FROM chunk c
              JOIN document d ON d.document_id = c.document_id
             WHERE {" AND ".join(clauses)}
             ORDER BY score DESC, c.document_id, c.page, c.ordinal
             LIMIT %s
            """,
            parameters,
        )
        rows = cur.fetchall()

    return [
        SearchHit(
            chunk=Chunk(
                document_id=row["document_id"],
                page=row["page"],
                ordinal=row["ordinal"],
                text=row["text"],
            ),
            score=float(row["score"]),
            title=row["title"],
            machine_model=row["machine_model"],
        )
        for row in rows
    ]

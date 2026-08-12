"""Measure drafting against the corpus's answer key (ADR-037).

Run by hand, never by CI, for the reason `measure_retrieval.py` gives: it needs
the embedding model, which is hundreds of megabytes.

    DATABASE_URL=postgresql://.../pdm_test uv run python scripts/measure_drafting.py

What is measured, per symptom in the answer key:

  * which page the draft cites, against the page the key names;
  * whether the outcome is the one the key's category implies - a repair draft
    for `covered`, a fault-finding draft for `documented_without_procedure`, and
    nothing at all for `absent`;
  * whether every figure in the drafted steps is one the key calls correct, and
    which of the figures the key marks as belonging to something else got in;
  * what the retrieval score of the drafted page was, and whether the word half
    matched it - the two numbers the "nothing here" decision has to be made on.

**Write the output into `docs/drafting-baseline.md` when it changes.**
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection, connect

from fixtures.corpus import CORPUS, AbsentSymptom, Answer, DocumentedOnly
from pdm.authoring.drafting import DraftOutcome, DraftResult, figures
from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import MachineModel, UserId
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.retrieval import repo
from pdm.retrieval.embedding import OnnxEmbedder
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import InMemoryVectorIndex

OPERATOR = UserId("measurement")


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


def _cited_pages(result: DraftResult) -> list[int]:
    if result.draft is None:
        return []
    seen: list[int] = []
    for step in result.draft.steps:
        if step.page not in seen:
            seen.append(step.page)
    return seen


def _figure_report(result: DraftResult, entry: Answer) -> str:
    """Which of the page's figures the draft used, and whose they are.

    The gate only checks that a figure is on the cited page. This asks the
    narrower question the answer key can answer: is it the *right* figure. The
    difference between the two columns is the gate's known limit, stated rather
    than discovered (ADR-037).
    """
    if result.draft is None:
        return "-"
    drafted = set[object]()
    for step in result.draft.steps:
        drafted |= figures(step.text)

    correct = set[object]()
    for value in entry.correct_figures.values():
        values = value if isinstance(value, list) else [value]
        correct |= figures(" ".join(str(number) for number in values))

    misleading = {
        figure
        for wrong in entry.figures_on_the_page_that_are_not_the_answer
        for figure in figures(str(wrong.value))
    }
    return (
        f"{len(drafted & correct)}/{len(correct)} of the key's figures"
        + (f", {len(drafted & misleading)} misleading" if drafted & misleading else "")
    )


def _anchor(conn: Connection[Any], query: str, model: MachineModel, page: int) -> str:
    """Whether the word half matched the drafted page, and how strongly.

    The fused score cannot say "there is nothing here": reciprocal rank fusion
    only knows positions, and the vector half returns its nearest neighbours
    however far away they are, so an unanswerable question still produces a page
    at a respectable score. The word half is the half that can be empty.
    """
    hits = repo.search(conn, query, machine_model=model, limit=8)
    for hit in hits:
        if hit.chunk.page == page:
            return f"{hit.score:.3f}"
    return "no match"


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        print(f"refusing to run against {url.rsplit('/', 1)[-1]}: name a *_test database")
        return 1

    print(f"measured {datetime.now(UTC).date().isoformat()}")
    embedder = OnnxEmbedder()
    print(f"model {embedder.model_name}, {embedder.dimensions} dimensions")

    config = load_config(Path("config"))
    authoring, _ = profiles_from(config.policy.retrieval)
    print(f"authoring profile: candidates={authoring.candidates} min_score={authoring.min_score}\n")

    hybrid = HybridSearch(embedder, InMemoryVectorIndex())
    drafting = Drafting(
        hybrid,
        ExtractiveDrafter(),
        profile=authoring,
        skills=config.skills,
    )

    conn = connect(url)
    root = Path(tempfile.mkdtemp())
    try:
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()
        _load(conn, hybrid, root)
        conn.commit()

        entries: list[Answer | DocumentedOnly | AbsentSymptom] = [
            *CORPUS.covered,
            *CORPUS.documented_without_procedure,
            *CORPUS.absent,
        ]
        expected = {
            Answer: DraftOutcome.REPAIR,
            DocumentedOnly: DraftOutcome.DIAGNOSTIC,
            AbsentSymptom: DraftOutcome.NOT_FOUND,
        }

        header = (
            f"{'symptom':9} {'lang':4} {'wanted':11} {'outcome':11} {'key':4} {'cited':9} "
            f"{'score':6} {'word half':9} figures"
        )
        print(header)
        print("-" * len(header))

        agreed = 0
        total = 0
        for entry in entries:
            wanted = expected[type(entry)]
            if isinstance(entry, Answer):
                key_pages: tuple[int, ...] = entry.answer_pages
            elif isinstance(entry, DocumentedOnly):
                key_pages = entry.pages
            else:
                key_pages = ()

            for language, query in (("en", entry.queries.en), ("th", entry.queries.th)):
                result = drafting.run(
                    conn,
                    symptom_code=entry.symptom_code,
                    machine_model=entry.machine_model,
                    question=query,
                )
                cited = _cited_pages(result)
                total += 1
                agreed += int(result.outcome is wanted)
                score = (
                    f"{result.draft.steps[0].confidence:.2f}"
                    if result.draft is not None
                    else "-"
                )
                anchor = (
                    _anchor(conn, query, entry.machine_model, cited[0]) if cited else "-"
                )
                print(
                    f"{entry.symptom_code:9} {language:4} {wanted.value:11} "
                    f"{result.outcome.value:11} "
                    f"{','.join(str(page) for page in key_pages) or '-':4} "
                    f"{','.join(str(page) for page in cited) or '-':9} "
                    f"{score:6} {anchor:9} "
                    f"{_figure_report(result, entry) if isinstance(entry, Answer) else '-'}"
                )
                if result.outcome is not wanted:
                    print(f"{'':10}   -> {result.reason}")

        print(f"\noutcome as the answer key implies: {agreed}/{total}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

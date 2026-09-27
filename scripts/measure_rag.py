"""Measure retrieval and drafting against an answer key, split by dev and test.

Run by hand, never by CI: it needs the embedding model.

    DATABASE_URL=postgresql://.../pdm_test FASTEMBED_CACHE_PATH=... \\
        uv run python scripts/measure_rag.py [corpus|evalset] [--rerank]

`evalset` (the default) is the corpus written for measurement (ADR-096); its
`test` entries have never been tuned on. `corpus` is the original five-symptom
corpus, every entry of which has been looked at.

Per question (each symptom is asked in English and in Thai):

  * **retrieval**: the rank of the first answer page among the pages retrieved
    for that machine model - hit@1 and hit@3;
  * **outcome**: whether drafting produced what the key implies - a repair draft
    citing the answer pages, a fault-finding draft citing the documented page,
    or nothing for an absent symptom;
  * **unsafe**: a repair draft where the key says there is no procedure, or a
    repair draft citing a page that is not the answer. These are the errors that
    cost the most: a plausible procedure for the wrong thing. The reviewer is
    the last line against them (ADR-003); this counts how often the reviewer
    is needed as that line.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from psycopg import Connection, connect

from fixtures.corpus.answers import AbsentSymptom, Answer, Corpus, DocumentedOnly, load
from pdm.authoring.drafting import DraftOutcome, DraftResult
from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import MachineModel, UserId
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.retrieval.embedding import OnnxEmbedder
from pdm.retrieval.rerank import OnnxReranker
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import InMemoryVectorIndex

OPERATOR = UserId("measurement")
CORPORA = {
    "corpus": Path("fixtures/corpus"),
    "evalset": Path("fixtures/evalset"),
}
Entry = Answer | DocumentedOnly | AbsentSymptom


def _load(
    conn: Connection[Any], hybrid: HybridSearch, corpus: Corpus, root: Path, here: Path
) -> None:
    library = DocumentLibrary(FilesystemObjectStore(root), SystemClock())
    ingest = Ingest(library, hybrid)
    for document in corpus.documents:
        row = library.add(
            conn,
            content=(here / document.filename).read_bytes(),
            filename=document.filename,
            content_type="application/pdf",
            machine_model=document.machine_model,
            title=document.title,
            uploaded_by=OPERATOR,
            edition=document.edition,
        )
        ingest.run(conn, row.document_id)


def _key_pages(entry: Entry) -> tuple[int, ...]:
    if isinstance(entry, Answer):
        return entry.answer_pages
    if isinstance(entry, DocumentedOnly):
        return entry.pages
    return ()


def _rank(pages: list[tuple[str, int]], own: str, key: tuple[int, ...]) -> int | None:
    """1-based rank of the first answer page among the model's own pages."""
    for index, (document, page) in enumerate(pages, start=1):
        if document == own and page in key:
            return index
    return None


def _verdict(entry: Entry, result: DraftResult, own: str) -> tuple[bool, bool]:
    """(as the key implies, unsafe)."""
    cited = (
        [(str(step.source_doc), step.page) for step in result.draft.steps]
        if result.draft is not None
        else []
    )
    on_key = bool(cited) and all(doc == own and page in _key_pages(entry) for doc, page in cited)
    repair = result.outcome is DraftOutcome.REPAIR
    if isinstance(entry, Answer):
        return repair and on_key, repair and not on_key
    if isinstance(entry, DocumentedOnly):
        return result.outcome is DraftOutcome.DIAGNOSTIC and on_key, repair
    return result.outcome is DraftOutcome.NOT_FOUND, repair


def main() -> int:
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    name = args[0] if args else "evalset"
    rerank = "--rerank" in sys.argv
    here = CORPORA[name]
    corpus = load(here / "manifest.yaml")
    url = os.environ.get("DATABASE_URL", "")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        print("set DATABASE_URL to a *_test database")
        return 1

    embedder = OnnxEmbedder()
    config = load_config(Path("config"))
    authoring, _ = profiles_from(config.policy.retrieval)
    hybrid = HybridSearch(embedder, InMemoryVectorIndex())
    reranker = OnnxReranker() if rerank else None
    drafting = Drafting(
        hybrid, ExtractiveDrafter(), profile=authoring, skills=config.skills, reranker=reranker
    )
    print(
        f"measured {datetime.now(UTC).date().isoformat()} on {name} · model {embedder.model_name}"
        f" · reranker {reranker.model_name if reranker else 'none'}"
        f" · min_relevance {authoring.min_relevance if reranker else '-'}"
    )

    conn = connect(url)
    try:
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()
        _load(conn, hybrid, corpus, Path(tempfile.mkdtemp()), here)
        conn.commit()
        by_hash: dict[str, str] = {
            str(document.sha256): document.filename for document in corpus.documents
        }

        tally: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
        entries: list[Entry] = [
            *corpus.covered,
            *corpus.documented_without_procedure,
            *corpus.absent,
        ]
        print(
            f"\n{'split':5} {'symptom':8} {'lang':4} {'kind':10} {'rank':4} "
            f"{'outcome':10} ok  unsafe"
        )
        for entry in entries:
            own = corpus.document(entry.machine_model).sha256
            kind = type(entry).__name__
            for language, query in (("en", entry.queries.en), ("th", entry.queries.th)):
                hits = hybrid.search(
                    conn, query, machine_model=MachineModel(entry.machine_model), profile=authoring
                )
                pages: list[tuple[str, int]] = []
                for hit in hits:
                    key = (str(hit.chunk.document_id), hit.chunk.page)
                    if key not in pages:
                        pages.append(key)
                rank = _rank(pages, own, _key_pages(entry)) if _key_pages(entry) else None
                result = drafting.run(
                    conn,
                    symptom_code=entry.symptom_code,
                    machine_model=entry.machine_model,
                    question=query,
                )
                ok, unsafe = _verdict(entry, result, own)
                cited = (
                    sorted(
                        {
                            f"{by_hash.get(str(s.source_doc), '?')[:6]}:{s.page}"
                            for s in result.draft.steps
                        }
                    )
                    if result.draft is not None
                    else []
                )
                print(
                    f"{entry.split:5} {entry.symptom_code:8} {language:4} {kind[:10]:10} "
                    f"{rank if rank is not None else '-':4} {result.outcome.value:10} "
                    f"{'✓' if ok else '✗':3} {'UNSAFE' if unsafe else ''} {' '.join(cited)}"
                )
                row = tally[(entry.split, language)]
                row[0] += 1
                row[1] += int(ok)
                row[2] += int(unsafe)
                if _key_pages(entry):
                    row[3] += 1
                    row[4] += int(rank == 1)
                    row[5] += int(rank is not None and rank <= 3)

        print(
            f"\n{'split':5} {'lang':4} {'outcome ok':>12} {'unsafe':>8} {'hit@1':>8} {'hit@3':>8}"
        )
        for (split, language), (n, good, bad, ranked, at1, at3) in sorted(tally.items()):
            print(
                f"{split:5} {language:4} {f'{good}/{n}':>12} {bad:>8} "
                f"{f'{at1}/{ranked}':>8} {f'{at3}/{ranked}':>8}"
            )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

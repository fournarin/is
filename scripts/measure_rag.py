"""Measure retrieval and drafting against an answer key, split by dev and test.

Run by hand, never by CI: it needs the embedding model.

    DATABASE_URL=postgresql://.../pdm_test FASTEMBED_CACHE_PATH=... \\
        uv run python scripts/measure_rag.py [corpus|evalset|realdocs|realdocs2] [--rerank]
            [--candidates=N] [--symptom] [--mismatched] [--json=PATH]

`--symptom` hands drafting the symptom's description as well as the question
(ADR-121), using the other language's query as the description: it measures
what the second relevance test costs a question that is right. `--mismatched`
asks each symptom another symptom's question of the same model, with its own
description: it measures whether a wrong question still drafts the wrong page
under this symptom. Without `--symptom`, `--mismatched` shows what that cost
before ADR-121.

`evalset` (the default) is the corpus written for measurement (ADR-096); its
`test` entries have never been tuned on. `corpus` is the original five-symptom
corpus, every entry of which has been looked at. `realdocs` and `realdocs2` are
keys for real manufacturer manuals kept outside git (ADR-098, ADR-143); the
second has manuals that prescribe field repair, so it has `covered` entries.

`--json=PATH` also writes one record per question, for a results file to be
built from what was measured rather than copied out of the terminal.

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

import json
import os
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from psycopg import Connection, connect

from fixtures.corpus.answers import AbsentSymptom, Answer, Corpus, DocumentedOnly, load
from pdm.authoring.drafting import DraftOutcome, DraftResult
from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import MachineModel, UserId
from pdm.contracts.wording import figures
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
    "realdocs": Path("fixtures/realdocs"),
    "realdocs2": Path("fixtures/realdocs2"),
}
# The real manuals are not in the repository (ADR-098); their key is.
REALDOCS_DIR = Path(os.environ.get("REALDOCS_DIR", "ตัวอย่างเอกสารจริง"))
Entry = Answer | DocumentedOnly | AbsentSymptom


def _figures_found(entry: Entry, result: DraftResult) -> dict[str, bool] | None:
    """For a covered entry, whether each figure the key names is in the draft.

    Reported beside the verdict, not folded into it: the verdict is about the
    page, and a draft from the right page that drops a torque value is a
    different finding from one that cites the wrong page.
    """
    if not isinstance(entry, Answer) or not entry.correct_figures:
        return None
    drafted = (
        set().union(*(figures(step.text) for step in result.draft.steps))
        if result.draft is not None
        else set()
    )
    found: dict[str, bool] = {}
    for name, value in entry.correct_figures.items():
        wanted = value if isinstance(value, list) else [value]
        found[name] = all(Decimal(str(one)).normalize() in drafted for one in wanted)
    return found


def _load(
    conn: Connection[Any], hybrid: HybridSearch, corpus: Corpus, root: Path, here: Path
) -> dict[str, dict[str, Any]]:
    """Ingest every manual; what each one gave up travels with the figures (ADR-034)."""
    library = DocumentLibrary(FilesystemObjectStore(root), SystemClock())
    ingest = Ingest(library, hybrid)
    coverage: dict[str, dict[str, Any]] = {}
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
        report = ingest.run(conn, row.document_id)
        coverage[document.filename] = {
            "pages": report.pages,
            "pages_with_text": report.pages_with_text,
            "pages_needing_ocr": list(report.pages_needing_ocr),
            "chunks": report.chunks,
        }
        print(f"ingested {document.filename}: {report.pages_with_text}/{report.pages} pages")
    return coverage


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
    with_symptom = "--symptom" in sys.argv
    mismatched = "--mismatched" in sys.argv
    json_path = next(
        (Path(arg.split("=", 1)[1]) for arg in sys.argv[1:] if arg.startswith("--json=")), None
    )
    records: list[dict[str, Any]] = []
    here = CORPORA[name]
    corpus = load(here / "manifest.yaml")
    if name.startswith("realdocs"):
        here = REALDOCS_DIR
    url = os.environ.get("DATABASE_URL", "")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        print("set DATABASE_URL to a *_test database")
        return 1

    embedder = OnnxEmbedder()
    config = load_config(Path("config"))
    authoring, _ = profiles_from(config.policy.retrieval)
    for arg in sys.argv[1:]:
        if arg.startswith("--candidates="):
            authoring = authoring.model_copy(update={"candidates": int(arg.split("=", 1)[1])})
    hybrid = HybridSearch(embedder, InMemoryVectorIndex())
    reranker = OnnxReranker() if rerank else None
    drafting = Drafting(
        hybrid, ExtractiveDrafter(), profile=authoring, skills=config.skills, reranker=reranker
    )
    print(
        f"measured {datetime.now(UTC).date().isoformat()} on {name} · model {embedder.model_name}"
        f" · reranker {reranker.model_name if reranker else 'none'}"
        f" · min_relevance {authoring.min_relevance if reranker else '-'}"
        f"{' · symptom described' if with_symptom else ''}"
        f"{' · mismatched questions' if mismatched else ''}"
    )

    conn = connect(url)
    try:
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()
        coverage = _load(conn, hybrid, corpus, Path(tempfile.mkdtemp()), here)
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
            # Another symptom of the same model, for --mismatched: the next one
            # round the list, so every symptom is asked somebody else's question.
            same_model = [one for one in entries if one.machine_model == entry.machine_model]
            other = same_model[(same_model.index(entry) + 1) % len(same_model)]
            for language, own_query, other_language in (
                ("en", entry.queries.en, entry.queries.th),
                ("th", entry.queries.th, entry.queries.en),
            ):
                query = (
                    (other.queries.en if language == "en" else other.queries.th)
                    if mismatched and other is not entry
                    else own_query
                )
                symptom = (own_query if mismatched else other_language) if with_symptom else None
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
                    symptom=symptom,
                )
                ok, unsafe = _verdict(entry, result, own)
                cited = (
                    sorted(
                        {
                            f"{by_hash.get(str(s.source_doc), '?')[:6]}:{s.page}@{s.confidence:.2f}"
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
                records.append(
                    {
                        "symptom_code": entry.symptom_code,
                        "language": language,
                        "split": entry.split,
                        "kind": kind,
                        "machine_model": entry.machine_model,
                        "query": query,
                        "rank": rank,
                        "outcome": result.outcome.value,
                        "ok": ok,
                        "unsafe": unsafe,
                        "cited": [
                            {
                                "document": by_hash.get(str(step.source_doc), "?"),
                                "page": step.page,
                                "confidence": round(step.confidence, 3),
                            }
                            for step in (result.draft.steps if result.draft is not None else ())
                        ],
                        "figures": _figures_found(entry, result),
                        "reason": result.reason,
                    }
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
    if json_path is not None:
        json_path.write_text(
            json.dumps(
                {
                    "set": name,
                    "measured": datetime.now(UTC).isoformat(timespec="seconds"),
                    "embedder": embedder.model_name,
                    "reranker": reranker.model_name if reranker else None,
                    "min_relevance": authoring.min_relevance if reranker else None,
                    "candidates": authoring.candidates,
                    "symptom_described": with_symptom,
                    "mismatched": mismatched,
                    "coverage": coverage,
                    "questions": records,
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

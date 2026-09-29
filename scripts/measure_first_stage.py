"""Which first stage should feed the reranker: sparse, dense, RRF or a union?

Run by hand, never by CI (it needs the embedding model):

    DATABASE_URL=postgresql://.../pdm_test FASTEMBED_CACHE_PATH=... \\
        PYTHONPATH=. uv run python scripts/measure_first_stage.py [corpus|evalset|realdocs]

Since the reranker (ADR-097), the fused order no longer decides the answer: the
reranker scores every candidate again. What the first stage still decides is
*which* candidates the reranker sees - the authoring profile's `candidates`
chunks. So the question for each configuration is whether the answer page is
inside that cut, and how deep it sits:

  * **sparse**: PostgreSQL full-text alone;
  * **dense**: the multilingual embedding alone;
  * **rrf**: the two fused on rank, as shipped (ADR-035);
  * **union**: the top half of the cut from each, interleaved, with no fusion.

Only questions whose key names a page are counted; an absent symptom has no
page to find. The rank is by page among the machine model's own manual, as in
`measure_rag.py`.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections import defaultdict
from datetime import UTC, datetime
from itertools import zip_longest
from pathlib import Path
from statistics import median

from psycopg import connect

from fixtures.corpus.answers import load
from pdm.contracts import MachineModel
from pdm.platform.config import load_config
from pdm.retrieval import repo
from pdm.retrieval.domain import Chunk, fuse
from pdm.retrieval.embedding import OnnxEmbedder
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import InMemoryVectorIndex
from scripts.measure_rag import CORPORA, REALDOCS_DIR, Entry, _key_pages, _load

CONFIGS = ("sparse", "dense", "rrf", "union")


def _interleave(first: list[Chunk], second: list[Chunk], limit: int) -> list[Chunk]:
    """The top half of the cut from each list, alternating, then the rest of each.

    An empty or short list gives up its share to the other: a Thai query that
    full-text search cannot tokenise still sends the reranker a full cut.
    """
    half = limit // 2
    out: list[Chunk] = []
    seen: set[object] = set()

    def take(chunk: Chunk) -> None:
        if chunk.key not in seen:
            seen.add(chunk.key)
            out.append(chunk)

    for pair in zip_longest(first[:half], second[:half]):
        for chunk in pair:
            if chunk is not None:
                take(chunk)
    for chunk in [*second[half:], *first[half:]]:
        take(chunk)
    return out


def _place(
    chunks: list[Chunk], own: str, key: tuple[int, ...], cut: int
) -> tuple[int | None, bool]:
    """(page rank of the first answer page, whether an answer chunk is inside the cut)."""
    pages: list[tuple[str, int]] = []
    rank = None
    for chunk in chunks:
        page = (str(chunk.document_id), chunk.page)
        if page not in pages:
            pages.append(page)
            if rank is None and page[0] == own and page[1] in key:
                rank = len(pages)
    inside = any(str(chunk.document_id) == own and chunk.page in key for chunk in chunks[:cut])
    return rank, inside


def main() -> int:
    name = sys.argv[1] if len(sys.argv) > 1 else "evalset"
    here = CORPORA[name]
    corpus = load(here / "manifest.yaml")
    if name == "realdocs":
        here = REALDOCS_DIR
    url = os.environ.get("DATABASE_URL", "")
    if not url.rsplit("/", 1)[-1].endswith("_test"):
        print("set DATABASE_URL to a *_test database")
        return 1

    embedder = OnnxEmbedder()
    authoring, _ = profiles_from(load_config(Path("config")).policy.retrieval)
    cut = authoring.candidates
    depth = cut * 2
    vectors = InMemoryVectorIndex()
    hybrid = HybridSearch(embedder, vectors)
    print(f"measured {datetime.now(UTC).date().isoformat()} on {name} · cut {cut} chunks")

    rows: dict[tuple[str, str], dict[str, list[tuple[int | None, bool]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    detail: list[str] = []
    with connect(url) as conn:
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()
        _load(conn, hybrid, corpus, Path(tempfile.mkdtemp()), here)
        conn.commit()
        entries: list[Entry] = [*corpus.covered, *corpus.documented_without_procedure]
        for entry in entries:
            own = str(corpus.document(entry.machine_model).sha256)
            key = _key_pages(entry)
            model = MachineModel(entry.machine_model)
            for language, query in (("en", entry.queries.en), ("th", entry.queries.th)):
                sparse = [
                    hit.chunk for hit in repo.search(conn, query, machine_model=model, limit=depth)
                ]
                keys = vectors.search(embedder.embed_query(query), machine_model=model, limit=depth)
                by_key = {chunk.key: chunk for chunk in repo.chunks_by_key(conn, keys)}
                dense = [by_key[k] for k in keys if k in by_key]
                lists = {
                    "sparse": sparse,
                    "dense": dense,
                    "rrf": [hit.chunk for hit in fuse([sparse, dense])],
                    "union": _interleave(sparse, dense, cut),
                }
                placed = {config: _place(lists[config], own, key, cut) for config in CONFIGS}
                for config in CONFIGS:
                    rows[(entry.split, language)][config].append(placed[config])
                detail.append(
                    f"{entry.split:5} {entry.symptom_code:8} {language:3} "
                    + " ".join(
                        f"{config}={placed[config][0] if placed[config][0] is not None else '-':>4}"
                        f"{'' if placed[config][1] else '*'}"
                        for config in CONFIGS
                    )
                )

    print("\nper question: page rank of the answer (* = outside the cut)")
    print("\n".join(detail))
    print(
        f"\n{'split':5} {'lang':4} "
        + " ".join(f"{c + ' in cut':>14} {'median':>6}" for c in CONFIGS)
    )
    for (split, language), by_config in sorted(rows.items()):
        cells = []
        for config in CONFIGS:
            results = by_config[config]
            inside = sum(ok for _, ok in results)
            ranks = [rank for rank, _ in results if rank is not None]
            cells.append(f"{inside:>9}/{len(results):<4} {median(ranks) if ranks else '-':>6}")
        print(f"{split:5} {language:4} " + " ".join(cells))
    return 0


if __name__ == "__main__":
    sys.exit(main())

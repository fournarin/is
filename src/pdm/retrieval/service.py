"""Hybrid search: both halves, fused, under a profile (ADR-015, ADR-035).

The only module `authoring/`, `playbooks/` and `api/` call to find a page. It
opens no connection - the caller supplies one.

Two profiles, because the cost of the two kinds of mistake is not the same in
the two situations (ADR-015). At authoring an engineer reviews every candidate,
so missing the right page is the expensive error and a wide net is right. At
runtime nobody stands between the system and the technician, so serving a page
that only looks relevant is the expensive one, and the system abstains instead.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import DocumentId, MachineModel
from pdm.platform.config.schema import RetrievalPolicy
from pdm.retrieval import repo
from pdm.retrieval.domain import Chunk, FusedHit, SearchHit, fuse
from pdm.retrieval.embedding import Embedder
from pdm.retrieval.vectors import VectorIndex, records_for


class Profile(BaseModel):
    """One of the two retrieval settings from policy.yaml.

    Held as its own model rather than passed as loose arguments so that a call
    site cannot take the candidate count from one profile and the threshold from
    the other - which would read as working and be neither profile.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: int = Field(gt=0)
    min_score: float = Field(ge=0.0, le=1.0)
    # Return nothing rather than the best of a bad set. Runtime abstains;
    # authoring does not, because a reviewer can dismiss a wrong candidate in a
    # second and cannot conjure a page the system never offered.
    abstain: bool
    # Never crosses machine models silently. The one line ADR-015 does not move
    # even at authoring time: a lockout procedure for a neighbouring model reads
    # correctly line by line and is wrong in the order the interlocks release.
    same_model_only: bool
    # A page the reranker scores below this is not evidence at all (ADR-097).
    min_relevance: float | None = None
    min_relevance_to_draft: float | None = None
    min_relevance_for_repair: float | None = None


def profiles_from(policy: RetrievalPolicy) -> tuple[Profile, Profile]:
    """The two profiles as configured, in the order (authoring, runtime).

    Built from `policy.yaml` rather than written here. The first version of this
    module hardcoded them, with a docstring claiming they came from config -
    which meant retuning the file changed nothing, and the two values drifted
    apart without anything noticing. `RetrievalPolicy` already validates at boot
    that the authoring profile is the looser of the two (ADR-015).

    `same_model_only` is not in the file and is not configurable: it is the one
    line ADR-015 says does not move, and a knob for it is a knob somebody turns.
    """
    return (
        Profile(
            candidates=policy.authoring.candidates,
            min_score=policy.authoring.min_score,
            abstain=policy.authoring.abstain,
            same_model_only=False,
            min_relevance=policy.authoring.min_relevance,
            min_relevance_to_draft=policy.authoring.min_relevance_to_draft,
            min_relevance_for_repair=policy.authoring.min_relevance_for_repair,
        ),
        Profile(
            candidates=policy.runtime.candidates,
            min_score=policy.runtime.min_score,
            abstain=policy.runtime.abstain,
            same_model_only=True,
        ),
    )


class Retrieved(BaseModel):
    """A fused hit with the text and the manual it came from.

    Assembled here because neither half has all of it: the vector store knows
    only keys, and the fused hit knows only ranks. The review screen needs the
    title and the model on every candidate so that "this one is from the other
    manual" is impossible to miss (ADR-015).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    chunk: Chunk
    score: float
    ranks: tuple[int | None, ...]
    title: str
    machine_model: MachineModel

    @property
    def found_by_both(self) -> bool:
        return all(rank is not None for rank in self.ranks)


class HybridSearch:
    """Word search and meaning search, fused on rank."""

    def __init__(self, embedder: Embedder, vectors: VectorIndex) -> None:
        self.embedder = embedder
        self.vectors = vectors

    def index_document(
        self,
        document_id: DocumentId,
        chunks: list[Chunk],
        machine_model: MachineModel,
    ) -> int:
        """Add a document's chunks to the vector half.

        Called after the chunks are in PostgreSQL, never before: that order is
        what makes a crash between the two a chunk the dense half cannot see,
        rather than a vector pointing at a chunk that does not exist (ADR-035).
        """
        self.vectors.ensure_ready(self.embedder.dimensions)
        self.vectors.drop_document(document_id)
        if not chunks:
            return 0
        vectors = self.embedder.embed_passages([chunk.text for chunk in chunks])
        self.vectors.upsert(records_for(chunks, vectors, machine_model))
        return len(chunks)

    def drop_document(self, document_id: DocumentId) -> None:
        self.vectors.drop_document(document_id)

    def search(
        self,
        conn: Connection[Any],
        query: str,
        *,
        machine_model: MachineModel | None = None,
        profile: Profile,
    ) -> list[Retrieved]:
        """Both halves, fused, filtered by the profile.

        Each half is asked for more than the profile will return. Fusion can
        only rank what it is given, and a chunk that is eighth in one half and
        first in the other is exactly the hit worth surfacing - it cannot be if
        the lists were cut to four before they met.
        """
        if profile.same_model_only and machine_model is None:
            raise ValueError(
                "this profile must not search across machine models, and no model was "
                "given. A lockout procedure from a neighbouring model reads correctly "
                "and is wrong in the order the interlocks release (ADR-015)."
            )

        depth = profile.candidates * 2

        sparse = repo.search(conn, query, machine_model=machine_model, limit=depth)
        dense_keys = self.vectors.search(
            self.embedder.embed_query(query), machine_model=machine_model, limit=depth
        )

        # The vector half returns keys; the text comes from PostgreSQL, which is
        # the only place it lives.
        dense_chunks = repo.chunks_by_key(conn, dense_keys)
        by_key = {chunk.key: chunk for chunk in dense_chunks}
        dense = [by_key[key] for key in dense_keys if key in by_key]

        fused = fuse([[hit.chunk for hit in sparse], dense])
        return self._describe(conn, fused, profile)

    def _describe(
        self, conn: Connection[Any], fused: list[FusedHit], profile: Profile
    ) -> list[Retrieved]:
        above = [hit for hit in fused if hit.score >= profile.min_score]
        if profile.abstain and not above:
            return []

        # Without a threshold to clear, a profile that never abstains still
        # returns its best guesses - which is what ADR-015 asks of authoring.
        chosen = (above if above else fused)[: profile.candidates]
        documents = repo.documents_of(conn, [hit.chunk.document_id for hit in chosen])

        return [
            Retrieved(
                chunk=hit.chunk,
                score=hit.score,
                ranks=hit.ranks,
                title=documents[hit.chunk.document_id][0],
                machine_model=documents[hit.chunk.document_id][1],
            )
            for hit in chosen
            if hit.chunk.document_id in documents
        ]


def sparse_only(
    conn: Connection[Any],
    query: str,
    *,
    machine_model: MachineModel | None = None,
    limit: int = 8,
) -> list[SearchHit]:
    """The word half on its own.

    Kept reachable because it is the baseline every hybrid figure is compared
    against, and a baseline that can only be produced by editing code is a
    baseline nobody reproduces.
    """
    return repo.search(conn, query, machine_model=machine_model, limit=limit)

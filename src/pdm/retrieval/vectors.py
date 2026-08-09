"""Where the vectors live (ADR-035).

Qdrant in production, an in-memory store for tests. Both behind one port, so
the fusion above them never learns which is underneath.

The collection is keyed the same way fusion is: a chunk is `(document_id, page,
ordinal)`, and the point id is derived from that triple rather than allocated,
so re-ingesting a document overwrites its own points instead of accumulating a
second copy beside them.

This half is derived data. PostgreSQL is written first and holds the record; a
crash between the two leaves a chunk the dense half cannot see, which is
degraded retrieval rather than a lost document, and re-ingesting repairs it
(ADR-019, ADR-035).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from pdm.contracts import DocumentId, MachineModel
from pdm.retrieval.domain import Chunk, ChunkKey

COLLECTION = "manual_chunks"

# A fixed namespace turns a chunk's identity into a stable UUID. Qdrant accepts
# unsigned integers or UUIDs as point ids and not arbitrary strings, and a
# random id would mean re-ingesting a document adds points beside the old ones
# rather than replacing them.
_NAMESPACE = uuid.UUID("6f1c4d02-9a1b-4f7e-9f4a-2b7a5c8e13d4")


def point_id(key: ChunkKey) -> str:
    document_id, page, ordinal = key
    return str(uuid.uuid5(_NAMESPACE, f"{document_id}:{page}:{ordinal}"))


class VectorRecord(BaseModel):
    """A chunk as the vector store holds it.

    The payload carries what a filter needs and nothing more. Chunk text stays
    in PostgreSQL: duplicating it here would give two copies to keep in step,
    and the one place a search result is assembled already has the row.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: DocumentId
    page: int
    ordinal: int
    machine_model: MachineModel
    vector: tuple[float, ...]

    @property
    def key(self) -> ChunkKey:
        return (self.document_id, self.page, self.ordinal)


@runtime_checkable
class VectorIndex(Protocol):
    """Store and search vectors, filtered by machine model.

    Returns keys rather than chunks: the text lives in PostgreSQL and the caller
    is already reading it there, so returning it from both halves would mean two
    answers to the question of what a chunk says.
    """

    def ensure_ready(self, dimensions: int) -> None: ...

    def upsert(self, records: Sequence[VectorRecord]) -> None: ...

    def drop_document(self, document_id: DocumentId) -> None: ...

    def search(
        self,
        vector: Sequence[float],
        *,
        machine_model: MachineModel | None = None,
        limit: int = 8,
    ) -> list[ChunkKey]: ...


class InMemoryVectorIndex:
    """Every vector in a dict, scored by dot product.

    Exact rather than approximate, which for a test is the point: a difference
    between the two halves should be the retrieval, not the index's recall
    settings.
    """

    def __init__(self) -> None:
        self._records: dict[ChunkKey, VectorRecord] = {}

    def ensure_ready(self, dimensions: int) -> None:
        return None

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        for record in records:
            self._records[record.key] = record

    def drop_document(self, document_id: DocumentId) -> None:
        for key in [key for key in self._records if key[0] == document_id]:
            del self._records[key]

    def search(
        self,
        vector: Sequence[float],
        *,
        machine_model: MachineModel | None = None,
        limit: int = 8,
    ) -> list[ChunkKey]:
        candidates = [
            record
            for record in self._records.values()
            if machine_model is None or record.machine_model == machine_model
        ]
        scored = [
            (sum(a * b for a, b in zip(vector, record.vector, strict=False)), record)
            for record in candidates
        ]
        # Ties broken by key so the same inputs give the same order, which the
        # eval depends on.
        scored.sort(key=lambda pair: (-pair[0], pair[1].key))
        return [record.key for _, record in scored[:limit]]


class QdrantVectorIndex:
    """The real store.

    Cosine distance, because the embedder returns unit vectors and cosine is
    what the model was trained against.
    """

    def __init__(self, client: Any, collection: str = COLLECTION) -> None:
        self._client = client
        self._collection = collection

    def ensure_ready(self, dimensions: int) -> None:
        """Create the collection if it is not there.

        Idempotent and safe to call at boot: the vector store is derived data,
        so a fresh one is a correct one - it fills up again the next time a
        document is ingested.
        """
        from qdrant_client.models import Distance, VectorParams

        if self._client.collection_exists(self._collection):
            return
        self._client.create_collection(
            collection_name=self._collection,
            vectors_config=VectorParams(size=dimensions, distance=Distance.COSINE),
        )

    def upsert(self, records: Sequence[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        if not records:
            return
        self._client.upsert(
            collection_name=self._collection,
            points=[
                PointStruct(
                    id=point_id(record.key),
                    vector=list(record.vector),
                    payload={
                        "document_id": record.document_id,
                        "page": record.page,
                        "ordinal": record.ordinal,
                        "machine_model": record.machine_model,
                    },
                )
                for record in records
            ],
        )

    def drop_document(self, document_id: DocumentId) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        self._client.delete(
            collection_name=self._collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                )
            ),
        )

    def search(
        self,
        vector: Sequence[float],
        *,
        machine_model: MachineModel | None = None,
        limit: int = 8,
    ) -> list[ChunkKey]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        query_filter = None
        if machine_model is not None:
            query_filter = Filter(
                must=[FieldCondition(key="machine_model", match=MatchValue(value=machine_model))]
            )

        response = self._client.query_points(
            collection_name=self._collection,
            query=list(vector),
            query_filter=query_filter,
            limit=limit,
            with_payload=True,
        )
        return [
            (point.payload["document_id"], point.payload["page"], point.payload["ordinal"])
            for point in response.points
        ]


def records_for(
    chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], model: MachineModel
) -> list[VectorRecord]:
    """Pair chunks with their vectors. Separate from the embedder so that the
    order of the two lists is checked in one place rather than assumed at each
    call site."""
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks but {len(vectors)} vectors")
    return [
        VectorRecord(
            document_id=chunk.document_id,
            page=chunk.page,
            ordinal=chunk.ordinal,
            machine_model=model,
            vector=tuple(vector),
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

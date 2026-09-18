"""Turning text into vectors, in process (ADR-029, ADR-035).

Two implementations and a port. The real one runs a small multilingual model on
ONNX; the fake one returns vectors somebody wrote by hand, so that fusion and
the store can be tested without half a gigabyte of download in the way.

ONNX rather than PyTorch is about what ships to the plant. `sentence-transformers`
brings `torch`, `transformers`, `scipy` and `scikit-learn` - roughly two
gigabytes into an image ADR-026 shares between three services, so all three
carry it. The same models run through `onnxruntime` at a tenth of that.
ADR-029 requires the embedding model to be in process; it does not require the
heaviest way of getting it there.
"""

from __future__ import annotations

import hashlib
import math
import os
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

# The model ADR-035 chose. Cross-lingual, because the questions are Thai and the
# manuals are English (ADR-029), and 384 dimensions at 0.22 GB because it shares
# a machine with PostgreSQL, Qdrant and an LLM.
#
# Not multilingual-e5-small, which the ADR named first: it is not in fastembed's
# catalogue, and the e5 variant that is weighs 2.24 GB.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DIMENSIONS = 384

# Where the weights are, and the one name the Dockerfile, docker-compose.yml and
# this module all have to agree on. fastembed's own variable, so that anything
# else reaching for the library inside these containers finds the same copy
# (ADR-079).
MODEL_CACHE_VARIABLE = "FASTEMBED_CACHE_PATH"

# Some families - e5 and its relatives - are trained with an instruction prefix
# and lose accuracy without it, because the same sentence is embedded
# differently depending on whether it is the thing being searched for or the
# thing being searched. Others, including the default above, are trained without
# and are made *worse* by adding one.
#
# Kept as a table rather than as a decision made once: switching model is a
# one-line change, and this is the detail that would silently come with it.
# Getting it wrong degrades retrieval without failing anything.
_PREFIXES: dict[str, tuple[str, str]] = {
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
}
_NO_PREFIX = ("", "")


@runtime_checkable
class Embedder(Protocol):
    """Text to vectors, with the two directions kept apart.

    Documents and queries are separate methods rather than one call with a flag,
    because the models this port is built for encode them differently and a flag
    is the kind of argument that gets left at its default.

    Every implementation returns **unit-length** vectors, so a dot product is a
    cosine similarity. Without that guarantee the in-process store would rank by
    raw dot product - which rewards long vectors rather than close ones - while
    Qdrant, which normalises internally for cosine distance, would rank the same
    query differently. Two stores disagreeing about the same vectors is the kind
    of difference nobody finds by reading.
    """

    @property
    def dimensions(self) -> int: ...

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OnnxEmbedder:
    """The real model, loaded once and reused.

    **The weights are read from `MODEL_CACHE_VARIABLE`, and the image ships
    them** (ADR-079). fastembed downloads a missing model on first use, which is
    the behaviour to design against rather than rely on: the plant's machine has
    no route to the internet, and a worker that silently reached for one would
    fail at the first document with a stack trace about TLS rather than about a
    missing model.

    `cache_dir` is passed explicitly rather than left to fastembed's own
    environment handling, so that what this reads is visible in this file and
    testable from outside it.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL, cache_dir: str | None = None) -> None:
        # Imported here rather than at module scope so that importing this
        # module - which the API does at boot - does not pull onnxruntime into
        # memory for a process that may never embed anything.
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.cache_dir = cache_dir or os.environ.get(MODEL_CACHE_VARIABLE) or None
        self._model = TextEmbedding(model_name=model_name, cache_dir=self.cache_dir)
        self._query_prefix, self._passage_prefix = _PREFIXES.get(model_name, _NO_PREFIX)
        self._dimensions = len(next(iter(self._model.embed(["dimension probe"]))))

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        prefixed = [f"{self._passage_prefix}{text}" for text in texts]
        # Normalised here rather than trusted from the model: this one mean-pools
        # and returns vectors of length ~5, so a dot product against them is not
        # a cosine similarity. Qdrant would normalise internally and the
        # in-process store would not, and the two would quietly rank the same
        # query differently.
        return [_unit(vector.tolist()) for vector in self._model.embed(prefixed)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.embed([f"{self._query_prefix}{text}"])))
        return _unit(vector.tolist())


class FakeEmbedder:
    """Deterministic vectors with no model behind them.

    For every test that is about fusion, the store, or the plumbing between
    them. It is emphatically **not** a stand-in for the model in anything that
    claims to measure retrieval quality: two texts about the same subject get
    unrelated vectors here, so a similarity result from this class means
    nothing (ADR-035).

    Vectors can also be declared outright, which is how a test says "these two
    passages are close" without pretending a hash function understands Thai.
    A declaration matches any text **containing** its key, because a chunk is a
    page's text after parsing and chunking rather than the string a test wrote
    down: exact matching meant the declarations silently never fired and the
    test measured the hash instead, which looked like a working test right up
    until it disagreed with itself.
    """

    def __init__(
        self,
        dimensions: int = 8,
        declared: dict[str, list[float]] | None = None,
    ) -> None:
        self._dimensions = dimensions
        self._declared = declared or {}

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        # First declaration whose key appears in the text. Insertion order, so
        # the answer does not depend on dictionary iteration.
        for key, vector in self._declared.items():
            if key in text:
                return _unit(vector)

        # Stable across processes: hashlib rather than hash(), which is salted
        # per interpreter and would make a seeded test irreproducible.
        #
        # Extended by counter rather than by asking for a longer digest, because
        # blake2b refuses anything over 64 bytes - so the obvious version broke
        # at 33 dimensions and would have broken on the first attempt to fake
        # the real model's 384.
        raw: list[float] = []
        block = 0
        while len(raw) < self._dimensions:
            digest = hashlib.blake2b(f"{block}:{text}".encode(), digest_size=64).digest()
            raw.extend(
                int.from_bytes(digest[offset : offset + 2], "big") / 65535.0 - 0.5
                for offset in range(0, 64, 2)
            )
            block += 1
        return _unit(raw[: self._dimensions])


def _unit(vector: Sequence[float]) -> list[float]:
    """Normalise to unit length so that a dot product is a cosine similarity."""
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        # An all-zero vector has no direction. Returning it unchanged would make
        # every similarity zero, which reads as "unrelated to everything" rather
        # than as the degenerate input it is.
        return [0.0] * len(vector)
    return [value / length for value in vector]

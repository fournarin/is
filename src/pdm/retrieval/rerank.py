"""How relevant a page is to a question, as a magnitude rather than a rank (ADR-097).

Rank fusion (ADR-035) knows positions, not distances: the closest of nineteen
chunks scores 1.0 whether it answers the question or not, which is why a symptom
the manuals never mention got a confident repair procedure. A cross-encoder reads
the question and the page together and returns a score that means something on
its own, so "nothing here answers this" becomes a threshold instead of a guess.

The model is `BAAI/bge-reranker-v2-m3` (Apache-2.0, multilingual, reads Thai),
as the ONNX export `onnx-community/bge-reranker-v2-m3-ONNX`, int8-quantised to
571 MB so it runs on the authoring worker's CPU. It is registered with fastembed,
which the project already depends on (ADR-008), so no new package comes in.
Build time only: nothing at runtime calls this (ADR-003).
"""

from __future__ import annotations

import math
import os
from collections.abc import Sequence
from typing import Protocol

from pdm.retrieval.embedding import MODEL_CACHE_VARIABLE

RERANK_MODEL = "onnx-community/bge-reranker-v2-m3-ONNX"
RERANK_FILE = "onnx/model_int8.onnx"


class Reranker(Protocol):
    def relevance(self, question: str, texts: Sequence[str]) -> list[float]:
        """Each text's relevance to the question, in [0, 1], in input order."""
        ...


class OnnxReranker:
    """`bge-reranker-v2-m3` through fastembed, from the image's model cache."""

    def __init__(self, cache_dir: str | None = None) -> None:
        # Imported here for the reason `OnnxEmbedder` gives: importing this
        # module must not pull onnxruntime into a process that never reranks.
        from fastembed.common.model_description import ModelSource
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        self.cache_dir = cache_dir or os.environ.get(MODEL_CACHE_VARIABLE)
        if not self.cache_dir:
            raise RuntimeError(f"{MODEL_CACHE_VARIABLE} is not set (ADR-079)")
        if RERANK_MODEL not in {m["model"] for m in TextCrossEncoder.list_supported_models()}:
            TextCrossEncoder.add_custom_model(
                model=RERANK_MODEL,
                sources=ModelSource(hf=RERANK_MODEL),
                model_file=RERANK_FILE,
                license="apache-2.0",
                size_in_gb=0.57,
            )
        self.model_name = RERANK_MODEL
        self._model = TextCrossEncoder(model_name=RERANK_MODEL, cache_dir=self.cache_dir)

    def relevance(self, question: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        # The model emits a logit; the sigmoid makes it a probability-like score
        # a threshold can be written against and read by a person.
        return [1.0 / (1.0 + math.exp(-score)) for score in self._model.rerank(question, texts)]

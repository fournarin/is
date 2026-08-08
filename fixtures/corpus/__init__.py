"""The synthetic manual corpus and its answer key (ADR-033).

Two manuals for machine models that exist in `config/plant.yaml`, written to
contain the mistakes the pipeline has to catch rather than to look convincing.
Every figure in them is invented.

Loaded through here rather than by parsing the YAML at each call site, so that
"which page is the answer for SYM-014" has one definition. The models are frozen
for the same reason the contracts are: an answer key a test can edit in place is
not an answer key.

This package lives outside `src/pdm` on purpose. It is a measurement instrument
and a demo seed, not part of the shipped system, and nothing under `src/` may
import it.
"""

from fixtures.corpus.answers import (
    CORPUS,
    AbsentSymptom,
    Answer,
    Corpus,
    Distractor,
    DocumentedOnly,
    ManualDocument,
    MisleadingFigure,
    PageRef,
)

__all__ = [
    "CORPUS",
    "AbsentSymptom",
    "Answer",
    "Corpus",
    "Distractor",
    "DocumentedOnly",
    "ManualDocument",
    "MisleadingFigure",
    "PageRef",
]

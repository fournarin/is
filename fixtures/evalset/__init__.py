"""A second synthetic corpus for measuring retrieval and drafting (ADR-096).

Separate from `fixtures/corpus` so that nothing tuned on the first corpus is
measured on it, and split into `dev` and `test` entries so that nothing tuned on
its own dev half is measured on its test half. Outside `src/pdm` for the same
reason as the first corpus: a measurement instrument, not part of the system.
"""

from pathlib import Path

from fixtures.corpus.answers import Corpus, load

EVALSET_DIR = Path(__file__).parent
EVALSET: Corpus = load(EVALSET_DIR / "manifest.yaml")

__all__ = ["EVALSET", "EVALSET_DIR"]

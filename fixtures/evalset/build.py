"""Lay the evaluation manuals out as PDFs, with the first corpus's renderer.

Run by hand, never by CI:

    uv run python fixtures/evalset/build.py

Prints each file's sha256 for the manifest, which ADR-019 turns into its
document id.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fixtures.corpus.build import _render
from fixtures.evalset.pages import MANUALS

HERE = Path(__file__).parent


def main() -> None:
    for manual in MANUALS:
        content = _render(manual)
        (HERE / manual.filename).write_bytes(content)
        print(f"{manual.filename} {hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    main()

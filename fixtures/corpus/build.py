"""Lay the corpus text out as PDFs (ADR-033).

Run by hand, never by CI:

    uv run python fixtures/corpus/build.py

The output is committed, and the manifest records the sha256 of each file
because ADR-019 makes that hash the document id. Regenerating therefore changes
every document id and every citation recorded against them, which is meant to
be a deliberate act with a visible diff rather than something that happens on a
dependency upgrade.

Everything that would otherwise vary between runs is pinned: creation and
modification dates, the producer string, and the file identifier. Without that
the same text produces different bytes every run, and content addressing turns
into a new id per build.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fpdf import FPDF

from fixtures.corpus.pages import MANUALS, Manual

HERE = Path(__file__).parent

# Any fixed moment. It is pinned rather than chosen: a real timestamp would make
# the bytes, and therefore the document id, depend on when the file was built.
FROZEN = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


def _render(manual: Manual) -> bytes:
    pdf = FPDF(format="A4", unit="mm")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.set_title(manual.title)
    pdf.set_author("synthetic corpus")
    pdf.set_subject(f"{manual.machine_model} - {manual.edition}")
    pdf.set_producer("pdm fixture corpus")
    pdf.set_creator("pdm fixture corpus")
    pdf.set_creation_date(FROZEN)

    for page in manual.pages:
        pdf.add_page()

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(120)
        pdf.cell(0, 5, f"{manual.title} - {manual.edition}", new_x="LMARGIN", new_y="NEXT")

        pdf.set_text_color(0)
        pdf.set_font("Helvetica", "B", 15)
        pdf.ln(4)
        pdf.multi_cell(0, 8, page.heading)

        pdf.set_font("Helvetica", "", 11)
        pdf.ln(3)
        pdf.multi_cell(0, 6, page.body)

        # Printed page numbers are what a playbook step cites, so they have to be
        # on the page rather than implied by position in the file.
        pdf.set_y(-18)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(120)
        pdf.cell(0, 5, f"page {page.number}", align="C")

    out = pdf.output()
    return bytes(out)


def main() -> None:
    for manual in MANUALS:
        content = _render(manual)
        path = HERE / manual.filename
        path.write_bytes(content)
        print(f"{manual.filename}  {len(content):>7} bytes  {hashlib.sha256(content).hexdigest()}")


if __name__ == "__main__":
    main()

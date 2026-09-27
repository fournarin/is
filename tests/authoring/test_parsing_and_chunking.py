"""Reading a PDF and cutting it into chunks (ADR-034). No database.

Two properties carry the rest. A chunk never spans a page, because a citation
names one page and a technician opens it. And a page that gives back nothing is
reported rather than dropped, because the plant's manuals are scans and a
parser handed one returns an empty string with no error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.corpus import CORPUS
from pdm.authoring.domain import (
    MINIMUM_CHARACTERS,
    TARGET_CHARACTERS,
    chunk_document,
    chunk_page,
    running_furniture,
    strip_furniture,
)
from pdm.authoring.parsing import PageText, ParsedDocument, UnreadableDocument, parse
from pdm.contracts import DocumentId
from pdm.retrieval.domain import PageOutcome

DOCUMENT = DocumentId("a" * 64)


def _page(number: int, text: str, outcome: PageOutcome = PageOutcome.TEXT) -> PageText:
    return PageText(page=number, text=text, outcome=outcome)


class TestReadingAPdf:
    def test_the_corpus_reads_page_for_page(self) -> None:
        for document in CORPUS.documents:
            parsed = parse(document.path.read_bytes())
            assert len(parsed.pages) == document.pages
            assert [page.page for page in parsed.pages] == list(range(1, document.pages + 1))

    def test_a_page_that_gives_nothing_is_reported_not_dropped(self) -> None:
        """The scanned-manual case. Dropping these would let a real manual
        ingest to nothing while the job reports success (ADR-034)."""
        parsed = ParsedDocument(
            pages=(
                _page(1, "readable text of a reasonable length, several words long"),
                _page(2, "", PageOutcome.NO_TEXT),
                _page(3, "fig. 4", PageOutcome.TOO_LITTLE_TEXT),
            )
        )

        assert len(parsed.pages) == 3
        assert len(parsed.indexable) == 1
        assert parsed.coverage == pytest.approx(1 / 3)
        assert parsed.counts()[PageOutcome.NO_TEXT] == 1

    def test_nothing_at_all_and_almost_nothing_are_different_answers(self) -> None:
        """One may need OCR; the other is a divider page and never will."""
        from pdm.authoring.parsing import _classify

        assert _classify("") is PageOutcome.NO_TEXT
        assert _classify("fig. 4") is PageOutcome.TOO_LITTLE_TEXT
        assert _classify("a sentence long enough to be worth indexing") is PageOutcome.TEXT

    def test_a_document_of_no_pages_covers_nothing_rather_than_crashing(self) -> None:
        assert ParsedDocument(pages=()).coverage == 0.0

    def test_bytes_that_are_not_a_pdf_are_refused(self, tmp_path: Path) -> None:
        """Distinct from a PDF that yields no text: that is a scan and is
        ingested with its coverage recorded. This is not a document."""
        with pytest.raises(UnreadableDocument):
            parse(b"this is not a PDF at all")

    def test_a_figure_split_across_lines_is_never_fused(self) -> None:
        """The most damaging thing this module could do, and it did it.

        Rejoining any word character across a hyphen turned "torque to 20-\n25
        Nm" into "2025 Nm" - a number that is not in the manual, on a page whose
        citation still points at the right place, so provenance could not catch
        it. In a document whose whole content is torque values and thresholds
        this is worse than failing to parse at all.
        """
        from pdm.authoring.parsing import _normalise

        assert "2025" not in _normalise("Torque the bolts to 20-\n25 Nm.")
        assert "20-\n25 Nm" in _normalise("Torque the bolts to 20-\n25 Nm.")

    def test_a_word_split_across_lines_is_rejoined(self) -> None:
        from pdm.authoring.parsing import _normalise

        assert "calibrate" in _normalise("cali-\nbrate the sensor")

    def test_a_trailing_space_before_the_break_does_not_defeat_it(self) -> None:
        """Some extractors leave one. Collapsing spaces after rejoining meant
        the rejoin never saw the hyphen."""
        from pdm.authoring.parsing import _normalise

        assert "calibrate" in _normalise("cali- \nbrate the sensor")

    def test_one_damaged_page_does_not_lose_the_other_hundred(self) -> None:
        """A single failing page used to raise for the whole document, so 199
        readable pages of a 200-page manual indexed to nothing and the result
        was indistinguishable from "this is not a PDF"."""
        from unittest.mock import patch

        document = CORPUS.documents[0]
        undamaged = parse(document.path.read_bytes())

        with patch("pypdf._page.PageObject.extract_text") as extract:
            extract.side_effect = [
                RuntimeError("damaged content stream") if page.page == 2 else page.text
                for page in undamaged.pages
            ]
            parsed = parse(document.path.read_bytes())

        assert len(parsed.pages) == document.pages
        assert parsed.pages[1].outcome is PageOutcome.UNREADABLE
        assert [p.outcome for p in parsed.pages if p.page != 2] == [PageOutcome.TEXT] * (
            document.pages - 1
        )

    def test_the_running_header_and_footer_survive_parsing(self) -> None:
        """They have to reach the chunker to be removed by it. A parser that
        silently dropped them would take the printed page number with them."""
        document = CORPUS.documents[0]
        first = parse(document.path.read_bytes()).pages[0]

        assert document.title in first.text
        assert first.text.splitlines()[-1] == "page 1"


class TestRemovingWhatEveryPageRepeats:
    def test_the_title_and_the_footer_are_both_found(self) -> None:
        """The footer is the interesting one: every page's is a different
        string, so it is invisible to a plain frequency count. Masking the
        digits is what makes "page 4" and "page 5" the same line - and it is
        why the returned set holds masked forms."""
        pages = [_page(n, f"R-2000iC Manual\nbody text {n} here\npage {n}") for n in (1, 2, 3, 4)]

        furniture = running_furniture(pages)

        assert "R-#iC Manual" in furniture
        assert "page #" in furniture

    def test_masking_digits_also_removes_short_lines_that_only_count(self) -> None:
        """The cost of the mechanism, stated rather than discovered.

        A short line repeating on most pages and differing only by a number is
        treated as furniture even when it is content. That shape is what page
        numbers, revision stamps and section numbers are, so the trade is worth
        making - but a manual whose every page carries a short numbered line of
        real content would lose it.
        """
        pages = [_page(n, f"Torque setting {n}\nreal content here") for n in (1, 2, 3)]

        assert "Torque setting #" in running_furniture(pages)

    def test_lines_that_differ_in_their_words_are_left_alone(self) -> None:
        subjects = ["belt tension", "servo grease", "fan bearings"]
        pages = [_page(n, f"R-2000iC Manual\nabout {s}") for n, s in enumerate(subjects, 1)]

        assert strip_furniture(pages[0].text, running_furniture(pages)) == "about belt tension"

    def test_a_repeated_paragraph_is_content_not_furniture(self) -> None:
        """A safety warning printed on every page is repeated and is not
        furniture. Removing it would remove the one line that matters most."""
        warning = (
            "Isolate the cell and apply a personal lock before any work described "
            "in this section, without exception, whatever the apparent urgency."
        )
        pages = [_page(n, f"Title\n{warning}\nbody {n}") for n in (1, 2, 3)]

        assert warning not in running_furniture(pages)

    def test_two_pages_are_too_few_to_call_anything_furniture(self) -> None:
        """On two pages "appears on most pages" means "appears twice", which is
        a coincidence rather than a header."""
        pages = [_page(n, "Same line\nbody") for n in (1, 2)]

        assert running_furniture(pages) == frozenset()


class TestChunking:
    def test_a_chunk_never_crosses_a_page(self) -> None:
        """The rule the whole citation scheme rests on (ADR-034). A step saying
        "page 4" must be findable on page 4."""
        pages = [_page(1, "first page text " * 40), _page(2, "second page text " * 40)]

        chunks = chunk_document(DOCUMENT, pages)

        for chunk in chunks:
            page = next(p for p in pages if p.page == chunk.page)
            assert chunk.text.replace("\n\n", " ") in " ".join(page.text.split())

    def test_pages_that_gave_no_text_produce_no_chunks(self) -> None:
        pages = [
            _page(1, "readable text, long enough to be worth indexing here"),
            _page(2, "", PageOutcome.NO_TEXT),
        ]

        assert {chunk.page for chunk in chunk_document(DOCUMENT, pages)} == {1}

    def test_ordinals_number_the_chunks_within_their_page(self) -> None:
        long_page = "\n\n".join(f"Paragraph {n}. " + "filler " * 60 for n in range(4))
        chunks = chunk_document(DOCUMENT, [_page(1, long_page), _page(2, long_page)])

        for page in (1, 2):
            ordinals = [chunk.ordinal for chunk in chunks if chunk.page == page]
            assert ordinals == list(range(len(ordinals)))

    def test_paragraphs_are_packed_rather_than_cut_at_a_fixed_width(self) -> None:
        text = "\n\n".join(["short one.", "short two.", "short three."])

        assert chunk_page(text) == ["short one.\n\nshort two.\n\nshort three."]

    def test_a_paragraph_too_long_for_a_chunk_is_split_at_sentence_ends(self) -> None:
        sentence = "This sentence is of a moderate length and ends here. "
        chunks = chunk_page(sentence * 40)

        assert len(chunks) > 1
        for chunk in chunks:
            assert chunk.endswith("here.")

    def test_a_fragment_at_either_end_joins_its_neighbour(self) -> None:
        """A stray fragment retrieves on almost any query and tells a reviewer
        nothing. The leading one is the case that actually occurs: a page
        opening with a heading or "Symptom:" was leaving a chunk of a few
        characters at the front."""
        text = "A. " + "filler " * 200 + "\n\ntail."

        chunks = chunk_page(text)

        assert all(len(chunk) >= MINIMUM_CHARACTERS for chunk in chunks)
        assert chunks[0].startswith("A.")
        assert chunks[-1].endswith("tail.")

    def test_an_empty_page_produces_nothing(self) -> None:
        assert chunk_page("   \n\n  ") == []


class TestTheCorpusChunksTheWayTheAnswerKeySays:
    """The first use of the answer key written in slice 3.0.

    It was written before any of this existed, which is what makes it evidence
    rather than a description of the output.
    """

    def test_the_answer_for_each_symptom_lands_on_the_page_it_should(self) -> None:
        for answer in CORPUS.covered:
            document = CORPUS.document(answer.machine_model)
            parsed = parse(document.path.read_bytes())
            chunks = chunk_document(DocumentId(document.sha256), parsed.pages)

            on_answer_page = [c for c in chunks if c.page in answer.answer_pages]
            assert on_answer_page, f"{answer.symptom_code} produced no chunk on its answer page"

            text = " ".join(chunk.text for chunk in on_answer_page)
            for name, value in answer.correct_figures.items():
                for figure in value if isinstance(value, list) else [value]:
                    written = str(int(figure)) if figure == int(figure) else str(figure)
                    assert written in text, (
                        f"{answer.symptom_code}: {name} ({written}) is not in the chunks "
                        f"of page {list(answer.answer_pages)}"
                    )

    def test_the_running_header_is_gone_from_every_chunk(self) -> None:
        """Left in, the machine model is in every chunk of its manual and a
        search for it matches all of them equally."""
        for document in CORPUS.documents:
            parsed = parse(document.path.read_bytes())
            for chunk in chunk_document(DocumentId(document.sha256), parsed.pages):
                assert document.title not in chunk.text
                assert f"page {chunk.page}" not in chunk.text

    def test_no_chunk_is_wildly_over_the_target(self) -> None:
        """Packing is allowed to overshoot on a long sentence; it is not allowed
        to hand a reviewer a whole page and call it evidence."""
        for document in CORPUS.documents:
            parsed = parse(document.path.read_bytes())
            for chunk in chunk_document(DocumentId(document.sha256), parsed.pages):
                assert len(chunk.text) <= TARGET_CHARACTERS * 1.5


class TestAnEncryptedManual:
    """ADR-098: real manuals arrive AES-encrypted with an empty open password."""

    @staticmethod
    def _encrypted(*, user_password: str) -> bytes:
        from io import BytesIO

        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter(clone_from=PdfReader(CORPUS.documents[0].path))
        writer.encrypt(user_password=user_password, owner_password="owner", algorithm="AES-256")
        out = BytesIO()
        writer.write(out)
        return out.getvalue()

    def test_one_anybody_may_open_is_read_like_any_other(self) -> None:
        parsed = parse(self._encrypted(user_password=""))

        assert len(parsed.pages) == CORPUS.documents[0].pages
        assert "lockout" in parsed.pages[1].text.lower()

    def test_one_that_needs_a_password_is_refused_saying_so(self) -> None:
        with pytest.raises(UnreadableDocument, match="password"):
            parse(self._encrypted(user_password="secret"))

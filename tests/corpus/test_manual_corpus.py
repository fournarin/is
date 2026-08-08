"""The corpus has to agree with the plant, and with itself (ADR-033).

Nothing here tests the pipeline - none of it exists yet. These check the
measuring instrument before anything is measured with it, which is the only
point at which it can be checked honestly. Once retrieval exists, "is this the
right answer page" becomes indistinguishable from "is this what the retriever
returned".

The three that matter:

  * the sha manifest, which is what notices a real manual being dropped into the
    one directory where the NDA ignore rule has a hole
  * the symptom codes agreeing with config/rules.yaml, so the corpus answers the
    questions the system can actually ask
  * the three categories being non-empty, because a corpus where everything is
    answerable makes the fallback ladder unreachable
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fixtures.corpus import CORPUS, Corpus, ManualDocument, PageRef
from fixtures.corpus.pages import MANUALS
from pdm.authoring.parsing import parse
from pdm.platform.config import load_config

REPO_CONFIG = Path("config")


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return CORPUS


def _page_text(machine_model: str, pages: tuple[int, ...]) -> str:
    manual = next(m for m in MANUALS if m.machine_model == machine_model)
    return "\n".join(
        f"{page.heading}\n{page.body}" for page in manual.pages if page.number in pages
    )


def _numeral(value: float) -> str:
    """How the figure would be written on the page: 3.0 as "3", 12.5 as "12.5"."""
    return str(int(value)) if value == int(value) else str(value)


class TestTheBytesAreFrozen:
    def test_every_file_matches_its_recorded_hash(self, corpus: Corpus) -> None:
        """ADR-019 makes the sha256 the document id, so a changed byte is a
        changed identity. This is also the check that fails if anything else
        appears in the directory the .gitignore exception opened."""
        for document in corpus.documents:
            assert document.path.exists(), f"{document.filename} is missing"
            assert document.actual_sha256() == document.sha256, (
                f"{document.filename} does not match the manifest. Regenerating the "
                f"corpus changes every document id and every citation recorded "
                f"against it, so update the manifest deliberately (ADR-033)"
            )

    def test_no_unexpected_pdfs_in_the_corpus_directory(self, corpus: Corpus) -> None:
        declared = {document.filename for document in corpus.documents}
        on_disk = {path.name for path in corpus.documents[0].path.parent.glob("*.pdf")}
        assert on_disk == declared


class TestTheCorpusMatchesThePlant:
    def test_every_manual_is_for_a_machine_model_that_exists(self, corpus: Corpus) -> None:
        config = load_config(REPO_CONFIG)
        in_plant = {
            machine.model
            for line in config.plant.lines
            for st in line.stations
            for machine in st.machines
        }
        for document in corpus.documents:
            assert document.machine_model in in_plant

    def test_every_machine_model_in_the_plant_has_a_manual(self, corpus: Corpus) -> None:
        """A model with no manual has no playbook, so its work has no steps and
        drops out of the demo without anybody noticing."""
        config = load_config(REPO_CONFIG)
        in_plant = {
            machine.model
            for line in config.plant.lines
            for st in line.stations
            for machine in st.machines
        }
        covered = {document.machine_model for document in corpus.documents}
        assert in_plant == covered

    def test_the_corpus_answers_exactly_the_symptoms_the_rules_can_raise(
        self, corpus: Corpus
    ) -> None:
        """Both directions matter. A rule with no entry means the corpus is
        silent about a question the system will ask; an entry with no rule means
        an answer nobody can reach, which looks like coverage and is not."""
        config = load_config(REPO_CONFIG)
        raisable = {rule.symptom_code for rule in config.rules.rules}
        assert corpus.symptom_codes == raisable

    def test_each_symptom_is_filed_against_the_model_its_rule_watches(self, corpus: Corpus) -> None:
        config = load_config(REPO_CONFIG)
        watched_by = {rule.symptom_code: rule.machine_model for rule in config.rules.rules}

        for group in (corpus.covered, corpus.documented_without_procedure, corpus.absent):
            for entry in group:
                assert entry.machine_model == watched_by[entry.symptom_code]

    def test_required_skills_come_from_the_single_vocabulary(self, corpus: Corpus) -> None:
        """Two skill vocabularies fail to match in silence, which is the failure
        ADR-027 exists to prevent."""
        config = load_config(REPO_CONFIG)
        for answer in corpus.covered:
            assert answer.required_skill in config.skills


class TestTheGapsAreDeliberate:
    def test_all_three_categories_are_populated(self, corpus: Corpus) -> None:
        """Each one makes a different path through layer 2 reachable: a repair
        playbook, a fault-finding playbook, and "not found - ask an engineer"."""
        assert corpus.covered
        assert corpus.documented_without_procedure
        assert corpus.absent

    def test_the_symptoms_with_no_procedure_are_the_ones_with_no_component(
        self, corpus: Corpus
    ) -> None:
        """ADR-009: a rule that cannot say which part it watches gets a
        fault-finding playbook. If the corpus documented a repair for one of
        those, layer 2 would be able to serve repair steps for a fault nobody
        has located yet."""
        config = load_config(REPO_CONFIG)
        unknown_component = {
            rule.symptom_code for rule in config.rules.rules if rule.component == "unknown"
        }
        without_procedure = {
            entry.symptom_code
            for group in (corpus.documented_without_procedure, corpus.absent)
            for entry in group
        }
        assert without_procedure == unknown_component

    def test_nothing_is_written_anywhere_about_the_absent_symptom(self, corpus: Corpus) -> None:
        """Declaring a gap is cheap; the gap has to stay real. An edit that adds
        a paragraph about cycle time makes the "not found" path unreachable, and
        this is the only thing that would say so."""
        for absent in corpus.absent:
            for manual in MANUALS:
                for page in manual.pages:
                    text = f"{page.heading} {page.body}".lower()
                    for phrase in absent.forbidden_phrases:
                        assert phrase.lower() not in text, (
                            f"{manual.filename} page {page.number} mentions {phrase!r}, "
                            f"so {absent.symptom_code} is no longer absent from the corpus"
                        )


class TestTheAnswerKeyIsUsable:
    def test_every_cited_page_exists_in_the_document_it_names(self, corpus: Corpus) -> None:
        by_name = {document.filename: document for document in corpus.documents}

        def check(reference: PageRef, within: ManualDocument) -> None:
            filename, page = corpus.resolve(reference, within)
            assert filename in by_name, f"{filename} is not a document in this corpus"
            assert 1 <= page <= by_name[filename].pages

        for answer in corpus.covered:
            own = corpus.document(answer.machine_model)
            for page in (*answer.answer_pages, *answer.supporting_pages):
                assert 1 <= page <= own.pages
            for distractor in answer.distractors:
                check(distractor, own)

        for documented in corpus.documented_without_procedure:
            own = corpus.document(documented.machine_model)
            for page in documented.pages:
                assert 1 <= page <= own.pages

        # never_an_answer names its document outright, so any manual will do as
        # the fallback; what matters is that the filename resolves at all.
        for reference in corpus.never_an_answer:
            check(reference, corpus.documents[0])

    def test_an_answer_page_is_never_also_a_distractor_for_the_same_symptom(
        self, corpus: Corpus
    ) -> None:
        """Compared after resolving, not by whether `document` was left out. A
        distractor that spells out its own manual's filename and points at the
        answer page is the same contradiction written differently."""
        for answer in corpus.covered:
            own = corpus.document(answer.machine_model)
            declared = {corpus.resolve(d, own) for d in answer.distractors}
            answers = {(own.filename, page) for page in answer.answer_pages}
            assert not declared & answers

    def test_every_covered_symptom_declares_a_distractor_from_the_other_manual(
        self, corpus: Corpus
    ) -> None:
        """The wrong-model case is the one ADR-015 says reviewers are worst at,
        because a step from the other manual reads perfectly well. A corpus
        without it lets a retriever that ignores machine model score full marks.

        Checked by resolved filename: `document is not None` is satisfied by a
        distractor naming its own manual, which is not a cross-model case at
        all and leaves this guarantee unenforced.
        """
        for answer in corpus.covered:
            own = corpus.document(answer.machine_model)
            elsewhere = {
                filename
                for filename, _ in (corpus.resolve(d, own) for d in answer.distractors)
                if filename != own.filename
            }
            assert elsewhere, (
                f"{answer.symptom_code} has no distractor from a manual other than {own.filename}"
            )

    def test_the_gate_blind_spot_is_recorded_for_every_covered_symptom(
        self, corpus: Corpus
    ) -> None:
        """Invariant 5 checks that a figure in a drafted step appears in the
        cited evidence. These are the figures that do appear and still make the
        step wrong - the limit of the gate, which the report has to state."""
        for answer in corpus.covered:
            assert answer.figures_on_the_page_that_are_not_the_answer

    def test_every_recorded_blind_spot_is_really_a_numeral_on_the_answer_page(
        self, corpus: Corpus
    ) -> None:
        """A blind spot only exists if the gate would actually let it through,
        which means the numeral has to be on the page the step cites. One
        recorded here read "4 screws" where the page spells the word "four", so
        the gate would have caught it and the entry described a hazard that was
        not there.

        Matched with the unit attached. A bare digit is on almost every page as
        a step number, so searching for one finds something regardless of
        whether the figure exists - which is how the wrong entry survived being
        checked in the first place.
        """
        for answer in corpus.covered:
            text = _page_text(answer.machine_model, answer.answer_pages)
            for figure in answer.figures_on_the_page_that_are_not_the_answer:
                written = f"{_numeral(figure.value)} {figure.unit}"
                assert written in text, (
                    f"{answer.symptom_code}: {written!r} does not appear on page(s) "
                    f"{list(answer.answer_pages)}, so the gate would reject a draft "
                    f"quoting it and this is not a blind spot"
                )

    def test_the_first_page_of_each_manual_is_never_an_answer(self, corpus: Corpus) -> None:
        never = {(ref.document, ref.page) for ref in corpus.never_an_answer}
        for answer in corpus.covered:
            document = corpus.document(answer.machine_model)
            for page in answer.answer_pages:
                assert (document.filename, page) not in never


class TestTheManifestAgreesWithTheText:
    """The manifest repeats what pages.py already says, and the two can drift.

    Nothing else would notice: rebuilding after an edit updates the sha, the
    hash test goes green, and the manifest keeps claiming a page count or a
    title that is no longer true - while every citation recorded against it is
    read as authoritative.
    """

    def test_each_manual_appears_in_both_with_the_same_description(self, corpus: Corpus) -> None:
        by_filename = {manual.filename: manual for manual in MANUALS}
        assert {document.filename for document in corpus.documents} == set(by_filename)

        for document in corpus.documents:
            manual = by_filename[document.filename]
            assert document.title == manual.title
            assert document.machine_model == manual.machine_model
            assert document.edition == manual.edition
            assert document.pages == len(manual.pages)

    def test_page_numbers_run_from_one_without_gaps(self) -> None:
        """The printed footer comes from Page.number while the PDF page index
        comes from position in the list. A citation points at the printed
        number and ingest will read the index, so the two drifting apart makes
        every recorded page reference quietly wrong."""
        for manual in MANUALS:
            assert [page.number for page in manual.pages] == list(range(1, len(manual.pages) + 1))

    def test_the_pdf_itself_has_the_pages_the_manifest_claims(self, corpus: Corpus) -> None:
        """The check that was missing, and the one that mattered.

        The manifest was cross-checked against pages.py and pages.py against the
        manifest, and **neither was ever checked against the PDF**. The footer
        was being written past the auto page-break margin, so every footer
        landed on a page of its own: an eleven-page manual was twenty-two
        physical pages, and every page number in the answer key pointed at the
        wrong one. Both files agreed with each other the whole time.
        """
        for document in corpus.documents:
            parsed = parse(document.path.read_bytes())
            assert len(parsed.pages) == document.pages, (
                f"{document.filename} has {len(parsed.pages)} physical pages, "
                f"the manifest says {document.pages}"
            )

    def test_the_printed_page_number_matches_the_physical_page(self, corpus: Corpus) -> None:
        """A citation names the number printed on the page; ingest resolves it
        through the page's position in the file. If those two disagree, every
        recorded provenance is off and the documents still look fine."""
        for document in corpus.documents:
            for page in parse(document.path.read_bytes()).pages:
                assert page.text.splitlines()[-1] == f"page {page.page}"

    def test_every_page_of_the_corpus_yields_text(self, corpus: Corpus) -> None:
        """The corpus is generated text, so coverage below 1.0 means the layout
        produced a page nothing can read - which is what a scan looks like to
        the parser, and would silently shrink the searchable manual
        (ADR-034)."""
        for document in corpus.documents:
            assert parse(document.path.read_bytes()).coverage == 1.0

    def test_the_lockout_page_is_the_page_about_lockout(self, corpus: Corpus) -> None:
        """Every corrective procedure in the corpus begins by citing it."""
        for document in corpus.documents:
            manual = next(m for m in MANUALS if m.filename == document.filename)
            heading = manual.pages[document.lockout_page - 1].heading.lower()
            assert "lockout" in heading

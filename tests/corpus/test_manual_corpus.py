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

from fixtures.corpus import CORPUS, Corpus
from fixtures.corpus.pages import MANUALS
from pdm.platform.config import load_config

REPO_CONFIG = Path("config")


@pytest.fixture(scope="module")
def corpus() -> Corpus:
    return CORPUS


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

        for answer in corpus.covered:
            own = corpus.document(answer.machine_model)
            for page in (*answer.answer_pages, *answer.supporting_pages):
                assert 1 <= page <= own.pages
            for distractor in answer.distractors:
                document = by_name[distractor.document] if distractor.document else own
                assert 1 <= distractor.page <= document.pages

        for documented in corpus.documented_without_procedure:
            own = corpus.document(documented.machine_model)
            for page in documented.pages:
                assert 1 <= page <= own.pages

    def test_an_answer_page_is_never_also_a_distractor_for_the_same_symptom(
        self, corpus: Corpus
    ) -> None:
        for answer in corpus.covered:
            same_document = {
                distractor.page for distractor in answer.distractors if distractor.document is None
            }
            assert not same_document & set(answer.answer_pages)

    def test_every_covered_symptom_declares_a_cross_model_distractor(self, corpus: Corpus) -> None:
        """The wrong-model case is the one ADR-015 says reviewers are worst at,
        because a step from the other manual reads perfectly well. A corpus
        without it lets a retriever that ignores machine model score full
        marks."""
        for answer in corpus.covered:
            assert any(distractor.document is not None for distractor in answer.distractors), (
                f"{answer.symptom_code} has no distractor from the other manual"
            )

    def test_the_gate_blind_spot_is_recorded_for_every_covered_symptom(
        self, corpus: Corpus
    ) -> None:
        """Invariant 5 checks that a figure in a drafted step appears in the
        cited evidence. These are the figures that do appear and still make the
        step wrong - the limit of the gate, which the report has to state."""
        for answer in corpus.covered:
            assert answer.figures_on_the_page_that_are_not_the_answer

    def test_the_first_page_of_each_manual_is_never_an_answer(self, corpus: Corpus) -> None:
        never = {(ref.document, ref.page) for ref in corpus.never_an_answer}
        for answer in corpus.covered:
            document = corpus.document(answer.machine_model)
            for page in answer.answer_pages:
                assert (document.filename, page) not in never

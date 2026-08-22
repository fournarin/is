"""What "edit and approve" is allowed to be, with no database in sight.

The rule under test is ADR-064's: a reviewer rewords a step, and the citation on
it is not theirs to change. Both halves matter and they fail differently - one
loses the correction, the other keeps the correction and quietly detaches it from
the page it claims to come from, which is the failure invariant 4 exists to make
impossible.
"""

from __future__ import annotations

import pytest

from pdm.contracts import DocumentId, PlaybookStep
from pdm.playbooks.domain import apply_edits, edits_between

MANUAL = DocumentId("a" * 64)
OTHER = DocumentId("b" * 64)

DRAFT = (
    PlaybookStep(
        text="Stop the robot with the emergency stop.", source_doc=MANUAL, page=142, confidence=0.9
    ),
    PlaybookStep(text="Lock out breaker CP-3.", source_doc=MANUAL, page=142, confidence=0.8),
    PlaybookStep(text="Remove the fan cover.", source_doc=OTHER, page=88, confidence=0.5),
)


class TestWhatCountsAsAnEdit:
    def test_an_untouched_draft_produces_no_diff(self) -> None:
        assert edits_between(DRAFT, tuple(step.text for step in DRAFT)) == ()

    def test_only_the_steps_that_changed_appear(self) -> None:
        rewritten = (
            DRAFT[0].text,
            "Lock out breaker CP-3 and apply your personal lock.",
            DRAFT[2].text,
        )

        edits = edits_between(DRAFT, rewritten)

        assert len(edits) == 1
        assert edits[0].index == 1
        assert edits[0].before == "Lock out breaker CP-3."
        assert edits[0].after == "Lock out breaker CP-3 and apply your personal lock."

    def test_whitespace_is_a_change_like_any_other(self) -> None:
        """No normalisation. A reviewer who split a step onto two lines changed
        what a technician reads at a machine, and the diff should say so."""
        rewritten = (DRAFT[0].text + "\n", DRAFT[1].text, DRAFT[2].text)

        assert len(edits_between(DRAFT, rewritten)) == 1

    @pytest.mark.parametrize(
        "rewritten",
        [
            pytest.param((DRAFT[0].text, DRAFT[1].text), id="a step was dropped"),
            pytest.param(
                (DRAFT[0].text, DRAFT[1].text, DRAFT[2].text, "Refit the cover."),
                id="a step was added",
            ),
        ],
    )
    def test_changing_the_shape_of_the_procedure_is_refused(
        self, rewritten: tuple[str, ...]
    ) -> None:
        """ADR-037 section 4 refused the drafter a trimmed procedure, on the
        grounds that one reads as complete. The reviewer gets the same answer,
        and the button for "this is wrong" is send back."""
        with pytest.raises(ValueError, match="sending the draft back"):
            edits_between(DRAFT, rewritten)


class TestTheProvenanceSurvivesTheEdit:
    def test_the_reviewers_words_with_the_drafters_citation(self) -> None:
        edits = edits_between(
            DRAFT, (DRAFT[0].text, "Lock out breaker CP-3 and tag it.", DRAFT[2].text)
        )

        approved = apply_edits(DRAFT, edits)

        assert approved[1].text == "Lock out breaker CP-3 and tag it."
        assert approved[1].source_doc == MANUAL
        assert approved[1].page == 142
        assert approved[1].confidence == 0.8

    def test_the_untouched_steps_are_the_same_objects_of_the_same_shape(self) -> None:
        approved = apply_edits(DRAFT, edits_between(DRAFT, tuple(step.text for step in DRAFT)))

        assert approved == DRAFT

    def test_a_step_from_another_document_keeps_saying_so(self) -> None:
        """The one thing the review screen has to be able to show. If editing
        rewrote provenance, a reviewer correcting the wording of step 3 would
        erase the evidence that it came from a different manual (ADR-015)."""
        edits = edits_between(
            DRAFT, (DRAFT[0].text, DRAFT[1].text, "Remove the fan cover and set it aside.")
        )

        approved = apply_edits(DRAFT, edits)

        assert approved[2].source_doc == OTHER
        assert approved[2].page == 88

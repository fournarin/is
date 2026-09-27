"""Invariant 5, and the rest of what has to be true before a person reviews a
draft (ADR-037).

These tests drive the gate with backends that fabricate on purpose. That is the
point of them: the extractive backend passes every check here by construction,
so a suite that only ran real drafts through the gate would be a suite that
cannot fail - the failure this project has already shipped three times (the
answer-key tests of slice 3.0, the memory test of 3.1, the fake embedder of 3.3).

No database and no model. Everything here is a pure function over text.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from pdm.authoring.drafting import (
    DraftOutcome,
    RejectionReason,
    assemble,
)
from pdm.contracts import DocumentId, MachineModel, SkillId, SymptomCode
from pdm.llm.domain import DraftRequest, Evidence, Proposal, ProposalKind, ProposedStep, figures

R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")
DOC = DocumentId("a" * 64)
OTHER_DOC = DocumentId("b" * 64)
SYM = SymptomCode("SYM-014")

PAGE_4 = (
    "Symptom: belt motor temperature above 85 degrees Celsius.\n"
    "1. Isolate the cell following the lockout procedure on page 2.\n"
    "2. Remove the belt guard. The guard is held by four M6 bolts torqued to 10 Nm.\n"
    "3. Measure belt deflection at the midpoint of the longest span. Deflection must be "
    "4 to 6 mm under 20 N of applied force.\n"
    "4. If deflection is outside that range, slacken the motor mount bolts and reset "
    "tension. Retighten the motor mount bolts to 42 Nm.\n"
    "Required tools: torque wrench 5-60 Nm, belt tension gauge, 10 mm socket.\n"
    "Estimated time: 45 minutes. Required skill: robot mechanical."
)

# The other model's version of the same procedure, which reads perfectly well and
# is wrong (ADR-015). It is offered to the reviewer and must never be cited.
OTHER_MODEL_PAGE_4 = (
    "Symptom: belt motor temperature above 80 degrees Celsius.\n"
    "4. Retighten the motor mount bolts to 28 Nm."
)

EVIDENCE = Evidence(
    document_id=DOC,
    page=4,
    text=PAGE_4,
    title="R-2000iC Maintenance Manual",
    machine_model=R2000IC,
    score=0.75,
)
OTHER_MODEL_EVIDENCE = Evidence(
    document_id=OTHER_DOC,
    page=4,
    text=OTHER_MODEL_PAGE_4,
    title="M-710iC Maintenance Manual",
    machine_model=M710IC,
    score=0.40,
)

REQUEST = DraftRequest(
    symptom_code=SYM,
    machine_model=R2000IC,
    question="belt motor running above 85 degrees, what do I check",
    evidence=(EVIDENCE,),
)

SKILLS = frozenset({"robot_mechanical", "robot_controls", "electrical", "hydraulics"})


def _proposal(
    *texts: str,
    cites: tuple[str, int] | None = None,
    tools: tuple[str, ...] = (),
    required_skill: str | None = None,
    estimated_minutes: int | None = None,
) -> Proposal:
    """A backend's answer, with each step citing page 4 unless told otherwise."""
    reference = cites or (DOC, 4)
    return Proposal(
        kind=ProposalKind.REPAIR,
        steps=tuple(ProposedStep(text=text, cites=reference) for text in texts),
        tools=tools,
        required_skill=required_skill,
        estimated_minutes=estimated_minutes,
    )


class TestWhatCountsAsAFigure:
    """ADR-037 section 2. A figure is a numeric literal, normalised."""

    def test_a_torque_value_is_a_figure(self) -> None:
        assert figures("Retighten the motor mount bolts to 42 Nm.") == {Decimal(42)}

    def test_a_thousands_separator_is_not_part_of_the_number(self) -> None:
        assert figures("A fan below 1,200 rpm") == figures("A fan below 1200 rpm")

    def test_trailing_zeros_do_not_make_a_different_figure(self) -> None:
        assert figures("torque to 42.0 Nm") == figures("torque to 42 Nm")

    def test_a_range_is_two_figures(self) -> None:
        assert figures("Deflection must be 4 to 6 mm under 20 N") == {
            Decimal(4),
            Decimal(6),
            Decimal(20),
        }

    def test_a_hyphenated_range_is_two_figures_not_a_subtraction(self) -> None:
        assert figures("torque wrench 5-60 Nm") == {Decimal(5), Decimal(60)}

    def test_the_number_inside_a_designation_counts_too(self) -> None:
        """`TP-1` yields 1, and that is deliberate.

        The gate asks whether a figure in the step is present in the evidence,
        never the other way round. Counting more things as figures can only make
        the check stricter on the step and never looser, and excluding them would
        need a rule for telling a part number from a torque value - which is the
        judgement the gate exists precisely to avoid making.
        """
        assert figures("Verify zero energy at test points TP-1 and TP-2") == {
            Decimal(1),
            Decimal(2),
        }

    def test_prose_with_no_numbers_has_no_figures(self) -> None:
        assert figures("Inspect the fan shroud for accumulated debris.") == frozenset()


class TestAStepMustComeOutOfThePageItCites:
    """ADR-037 section 1: the model selects spans, it does not write text."""

    def test_a_span_of_the_cited_page_is_accepted(self) -> None:
        result = assemble(
            REQUEST,
            _proposal(
                "Remove the belt guard. The guard is held by four M6 bolts torqued to 10 Nm."
            ),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.REPAIR
        assert result.draft is not None
        assert result.draft.steps[0].page == 4
        assert result.draft.steps[0].source_doc == DOC

    def test_the_leading_step_number_is_not_part_of_the_text(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("2. Remove the belt guard."),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.REPAIR
        assert result.draft is not None
        assert result.draft.steps[0].text == "Remove the belt guard."

    def test_line_breaks_and_double_spaces_do_not_break_containment(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("Measure belt deflection at   the midpoint\nof the longest span."),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.REPAIR

    def test_a_sentence_the_page_does_not_contain_is_rejected(self) -> None:
        """The paraphrase case: true to the page, and not on it."""
        result = assemble(
            REQUEST,
            _proposal("Tighten the mount bolts to the specified torque of 42 Nm."),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.WITHHELD
        assert result.rejected[0].reason is RejectionReason.NOT_IN_EVIDENCE

    def test_citing_a_page_that_was_never_offered_is_rejected(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard.", cites=(DOC, 9)),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.WITHHELD
        assert result.rejected[0].reason is RejectionReason.EVIDENCE_NOT_OFFERED

    def test_citing_the_other_model_is_rejected_even_when_the_span_is_real(self) -> None:
        """ADR-015's one line that does not move, checked at the last moment.

        The service does not put another model's pages in the request, so this
        can only happen if that filtering is one day removed or bypassed. The
        step it would produce is real text from a real manual with 28 Nm in it,
        which is why the check is here as well as there.
        """
        request = DraftRequest(
            symptom_code=SYM,
            machine_model=R2000IC,
            question="belt motor overheating",
            evidence=(EVIDENCE, OTHER_MODEL_EVIDENCE),
        )
        result = assemble(
            request,
            _proposal("Retighten the motor mount bolts to 28 Nm.", cites=(OTHER_DOC, 4)),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.WITHHELD
        assert result.rejected[0].reason is RejectionReason.WRONG_MACHINE_MODEL


class TestFiguresMustBeASubsetOfTheEvidence:
    """Invariant 5 itself, driven by a backend that invents numbers."""

    def test_a_fabricated_torque_value_is_caught(self) -> None:
        result = assemble(
            REQUEST,
            # Containment relaxed to isolate the figure gate: this is the shape a
            # translated step will have, where the words differ and the numbers
            # must not (ADR-037 section 3).
            _proposal("Retighten the motor mount bolts to 33 Nm."),
            skills=SKILLS,
            require_containment=False,
        )
        assert result.outcome is DraftOutcome.WITHHELD
        assert result.rejected[0].reason is RejectionReason.FIGURE_NOT_IN_EVIDENCE
        assert result.rejected[0].figures_not_in_evidence == ("33",)

    def test_the_figure_is_reported_the_way_it_was_written(self) -> None:
        """40 and not `4E+1`.

        Normalising for comparison is right and printing the normalised form is
        not: what the reviewer is being shown is the figure a backend invented,
        and `4E+1` is a sentence about nothing that appears on any page.
        """
        result = assemble(
            REQUEST,
            _proposal("Retighten the motor mount bolts to 40 Nm at 1200 rpm."),
            skills=SKILLS,
            require_containment=False,
        )
        assert result.rejected[0].figures_not_in_evidence == ("40", "1200")

    def test_a_translated_step_keeping_every_figure_passes(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("ขันโบลต์แท่นมอเตอร์กลับที่ 42 Nm"),
            skills=SKILLS,
            require_containment=False,
        )
        assert result.outcome is DraftOutcome.REPAIR

    def test_a_step_using_fewer_figures_than_the_page_is_not_wrong(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard."),
            skills=SKILLS,
        )
        assert result.outcome is DraftOutcome.REPAIR

    def test_the_gates_known_limit_a_real_figure_belonging_to_something_else(self) -> None:
        """The 10 Nm guard-bolt torque, applied to the motor mount.

        Both numbers are on the page, so the subset check passes and the step is
        wrong. This is the limit ADR-037 records and the corpus declares in
        `figures_on_the_page_that_are_not_the_answer`; it is the reviewer's job,
        not the gate's, and the report has to say so rather than discover it.
        """
        result = assemble(
            REQUEST,
            _proposal("Retighten the motor mount bolts to 10 Nm."),
            skills=SKILLS,
            require_containment=False,
        )
        assert result.outcome is DraftOutcome.REPAIR


class TestOneBadStepWithholdsTheWholeDraft:
    """ADR-037 section 4. A procedure with a hole in it reads as complete."""

    def test_the_good_steps_are_not_offered_without_the_bad_one(self) -> None:
        result = assemble(
            REQUEST,
            _proposal(
                "Isolate the cell following the lockout procedure on page 2.",
                "Remove the belt guard.",
                "Retighten the motor mount bolts to 33 Nm.",
                "Inspect the fan shroud for accumulated debris and clear it.",
            ),
            skills=SKILLS,
            require_containment=False,
        )
        assert result.outcome is DraftOutcome.WITHHELD
        assert result.draft is None

    def test_the_rejected_step_travels_with_the_result(self) -> None:
        """The review queue gets the reason, not a silence.

        A withheld draft that says nothing is indistinguishable from a symptom
        nobody drafted, and the second one is a gap somebody should fill while
        the first is a model somebody should stop trusting.
        """
        result = assemble(
            REQUEST,
            _proposal(
                "Remove the belt guard.",
                "Retighten the motor mount bolts to 33 Nm.",
            ),
            skills=SKILLS,
            require_containment=False,
        )
        assert len(result.rejected) == 1
        assert "33" in result.rejected[0].text
        assert result.reason


class TestSkillAndDurationAreExtractedNeverInvented:
    """ADR-037 section 8."""

    def test_a_skill_the_page_states_is_carried_through(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard.", required_skill="robot mechanical"),
            skills=SKILLS,
        )
        assert result.draft is not None
        assert result.draft.proposed_skill == SkillId("robot_mechanical")

    def test_a_skill_outside_the_vocabulary_is_dropped_not_coerced(self) -> None:
        """Invariant 13: the skill list in plant.yaml is the only vocabulary.

        A label the config does not know cannot be assigned to anybody, so
        carrying it forward would put a playbook in the store that dispatch can
        never match to a technician - and it would look complete while doing it.
        """
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard.", required_skill="belt specialist"),
            skills=SKILLS,
        )
        assert result.draft is not None
        assert result.draft.proposed_skill is None
        assert "belt specialist" in result.reason

    def test_no_duration_is_proposed_when_the_page_states_none(self) -> None:
        result = assemble(REQUEST, _proposal("Remove the belt guard."), skills=SKILLS)
        assert result.draft is not None
        assert result.draft.proposed_minutes is None

    def test_a_draft_with_no_duration_cannot_be_turned_into_a_playbook_silently(self) -> None:
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard.", required_skill="robot mechanical"),
            skills=SKILLS,
        )
        assert result.draft is not None
        with pytest.raises(ValueError, match="estimated_minutes"):
            result.draft.into_playbook()


class TestNothingToDraft:
    """ADR-037 section 5. `not_found` is a result, not a failure."""

    def test_no_evidence_at_all_is_reported_as_not_found(self) -> None:
        empty = DraftRequest(
            symptom_code=SymptomCode("SYM-031"),
            machine_model=M710IC,
            question="cycle time drifting above 62 seconds",
            evidence=(),
        )
        result = assemble(empty, Proposal(kind=ProposalKind.NOTHING, steps=()), skills=SKILLS)
        assert result.outcome is DraftOutcome.NOT_FOUND
        assert result.draft is None
        assert result.rejected == ()

    def test_a_backend_claiming_a_procedure_and_giving_no_step_is_withheld(self) -> None:
        """The other half of the same distinction.

        `LlmServerDrafter` drops citations that point at pages it never showed
        the model, so a model fabricating every citation arrives here as "repair,
        no steps". Reporting that as `not_found` would say the manuals are silent
        about a symptom whose page is sitting in the index, and would hide the
        model that is inventing citations behind a sentence about the corpus.
        """
        result = assemble(REQUEST, Proposal(kind=ProposalKind.REPAIR, steps=()), skills=SKILLS)

        assert result.outcome is DraftOutcome.WITHHELD
        assert result.draft is None
        assert "backend" in result.reason

    def test_a_backend_that_returns_no_steps_is_not_a_withheld_draft(self) -> None:
        """Two silences that must not be confused.

        Nothing to draft is a gap in the manual; a withheld draft is a model that
        produced something unusable. Reporting both the same way would put the
        second one in the queue of symptoms nobody has written a playbook for,
        where it would wait for a manual page that already exists.
        """
        result = assemble(REQUEST, Proposal(kind=ProposalKind.NOTHING, steps=()), skills=SKILLS)
        assert result.outcome is DraftOutcome.NOT_FOUND


class TestTheDraftCarriesWhatTheReviewerNeeds:
    def test_step_confidence_is_the_retrieval_score_of_the_page_it_cites(self) -> None:
        """ADR-037 section 6: not a number the model reports about itself."""
        result = assemble(REQUEST, _proposal("Remove the belt guard."), skills=SKILLS)
        assert result.draft is not None
        assert result.draft.steps[0].confidence == pytest.approx(0.75)

    def test_other_model_candidates_are_kept_beside_the_draft(self) -> None:
        """ADR-015: labelled and visible, never silently mixed in."""
        result = assemble(
            REQUEST,
            _proposal("Remove the belt guard."),
            cross_model=(OTHER_MODEL_EVIDENCE,),
            skills=SKILLS,
        )
        assert result.draft is not None
        assert result.draft.cross_model_candidates == (OTHER_MODEL_EVIDENCE,)

    def test_a_completed_draft_becomes_a_playbook_that_is_still_a_draft(self) -> None:
        """Nothing here can produce approved text (ADR-003, invariant 3)."""
        result = assemble(
            REQUEST,
            _proposal(
                "Remove the belt guard.",
                required_skill="robot mechanical",
                estimated_minutes=45,
            ),
            skills=SKILLS,
        )
        assert result.draft is not None
        playbook = result.draft.into_playbook()
        assert playbook.status.value == "draft"
        assert playbook.approved_by is None
        assert playbook.estimated_minutes == 45
        assert playbook.required_skill == SkillId("robot_mechanical")
        assert playbook.source_doc == DOC
        assert playbook.page == 4

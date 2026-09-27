"""The backend tiers 1 and 2 run on: no model, no GPU, no network (ADR-037 §9).

It reads the evidence and picks spans out of it, which is all any backend here is
permitted to do. That makes it a real implementation of the port rather than a
stub, and it is the one the drafting numbers in the report come from - an LLM at
temperature zero is still not reproducible across model versions, and a number
that cannot be reproduced cannot be published.

The pages are the corpus's own (ADR-033), not hand-written here, so a change to
the manuals shows up as a failure in the thing that reads them.
"""

from __future__ import annotations

from fixtures.corpus.answers import CORPUS
from fixtures.corpus.pages import M710IC, R2000IC, Manual
from pdm.contracts import DocumentId, MachineModel, SymptomCode
from pdm.llm.domain import DraftRequest, Evidence, ProposalKind
from pdm.llm.extractive import ExtractiveDrafter

R2000IC_DOC = DocumentId("a" * 64)
M710IC_DOC = DocumentId("b" * 64)


def _page(manual: Manual, number: int, *, document_id: DocumentId, score: float) -> Evidence:
    page = next(candidate for candidate in manual.pages if candidate.number == number)
    return Evidence(
        document_id=document_id,
        page=number,
        text=f"{page.heading}\n\n{page.body}",
        title=manual.title,
        machine_model=MachineModel(manual.machine_model),
        score=score,
    )


def _question(symptom: str) -> str:
    """The question the answer key asks for this symptom, in English.

    Page choice now reads the figures in the question (ADR-089), so a test that
    offers the interlock page under a question about 85 degrees would be testing
    a mismatch it did not mean to. A symptom the key does not know gets a
    question with no figures, which ranks by score alone.
    """
    for group in (CORPUS.covered, CORPUS.documented_without_procedure, CORPUS.absent):
        for entry in group:
            if entry.symptom_code == symptom:
                return entry.queries.en
    return "what does the manual say about this"


def _request(
    *evidence: Evidence,
    symptom: str = "SYM-014",
    model: str = "R-2000iC",
    question: str | None = None,
) -> DraftRequest:
    return DraftRequest(
        symptom_code=SymptomCode(symptom),
        machine_model=MachineModel(model),
        question=question if question is not None else _question(symptom),
        evidence=evidence,
    )


class TestARepairProcedureIsReadOffThePage:
    def test_every_numbered_instruction_becomes_a_step_in_order(self) -> None:
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        proposal = ExtractiveDrafter().propose(_request(answer))

        assert proposal.kind is ProposalKind.REPAIR
        assert len(proposal.steps) == 6
        assert proposal.steps[0].text.startswith("Isolate the cell")
        assert proposal.steps[-1].text.startswith("Refit the guard")

    def test_every_step_cites_the_page_it_was_taken_from(self) -> None:
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        proposal = ExtractiveDrafter().propose(_request(answer))

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 4)}

    def test_no_step_says_anything_the_page_does_not(self) -> None:
        """The property that makes this backend safe by construction.

        Not a substitute for the gate in `authoring/drafting.py`: that gate has
        to hold for backends this one cannot vouch for.
        """
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        proposal = ExtractiveDrafter().propose(_request(answer))

        collapsed = " ".join(answer.text.split())
        for step in proposal.steps:
            assert " ".join(step.text.split()) in collapsed

    def test_tools_time_and_skill_come_off_the_page_when_it_states_them(self) -> None:
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        proposal = ExtractiveDrafter().propose(_request(answer))

        assert proposal.estimated_minutes == 45
        assert proposal.required_skill == "robot mechanical"
        assert proposal.tools == (
            "torque wrench 5-60 Nm",
            "belt tension gauge",
            "10 mm socket",
        )

    def test_the_note_after_the_list_is_not_folded_into_the_last_step(self) -> None:
        """Every step but the last is bounded by the marker after it.

        The lockout page has no tools block to end the procedure at, so the
        warning that follows the list - "The 5 minute wait is a minimum. Do not
        shorten it..." - would otherwise arrive as part of step 4, attributed to
        an instruction that does not say it.
        """
        lockout = _page(R2000IC, 2, document_id=R2000IC_DOC, score=0.9)
        proposal = ExtractiveDrafter().propose(_request(lockout, symptom="SYM-000"))

        assert len(proposal.steps) == 4
        assert proposal.steps[-1].text == (
            "Verify zero energy at test points TP-1 and TP-2 before proceeding."
        )

    def test_a_sentence_that_continues_the_last_step_is_kept(self) -> None:
        """The other direction: page 4's last step is two sentences on one line,
        and cutting at the first full stop would lose the temperature to confirm
        the repair against."""
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        proposal = ExtractiveDrafter().propose(_request(answer))

        assert "settles below 70 degrees" in proposal.steps[-1].text

    def test_a_page_that_states_no_duration_proposes_none(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=0.5)
        proposal = ExtractiveDrafter().propose(_request(overview))

        assert proposal.estimated_minutes is None
        assert proposal.required_skill is None


class TestChoosingWhichPageToDraftFrom:
    def test_the_highest_scoring_page_wins_not_the_first_one_listed(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=0.4)
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.9)
        proposal = ExtractiveDrafter().propose(_request(overview, answer))

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 4)}

    def test_a_page_from_another_model_is_never_drafted_from(self) -> None:
        """The service filters these out; this is the second place it holds.

        M-710iC page 4 is the same procedure with 28 Nm where this model wants
        42 Nm, and it outscores the right page here on purpose.
        """
        other_model = _page(M710IC, 4, document_id=M710IC_DOC, score=0.95)
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.5)
        proposal = ExtractiveDrafter().propose(_request(other_model, answer))

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 4)}

    def test_nothing_at_all_when_no_evidence_belongs_to_this_model(self) -> None:
        other_model = _page(M710IC, 4, document_id=M710IC_DOC, score=0.95)
        proposal = ExtractiveDrafter().propose(_request(other_model))

        assert proposal.kind is ProposalKind.NOTHING
        assert proposal.steps == ()


class TestAPageThatDocumentsWithoutPrescribing:
    """ADR-033's middle category, and ADR-009's diagnostic playbook."""

    def test_prose_with_no_numbered_steps_drafts_as_diagnostic(self) -> None:
        interlocks = _page(R2000IC, 11, document_id=R2000IC_DOC, score=0.9)
        proposal = ExtractiveDrafter().propose(
            _request(interlocks, symptom="SYM-002"),
        )

        assert proposal.kind is ProposalKind.DIAGNOSTIC
        assert proposal.steps

    def test_the_prohibition_on_the_page_is_carried_into_the_draft(self) -> None:
        """The one thing a draft off this page must never lose.

        "Bypassing an interlock to continue production is prohibited under all
        circumstances" is the sentence a technician most needs to see, and a
        drafter that kept only the sentences shaped like instructions would drop
        it - it is a prohibition, not an instruction.
        """
        interlocks = _page(R2000IC, 11, document_id=R2000IC_DOC, score=0.9)
        proposal = ExtractiveDrafter().propose(
            _request(interlocks, symptom="SYM-002"),
        )

        assert any("prohibited" in step.text for step in proposal.steps)


class TestTheSameEvidenceAlwaysDraftsTheSameWay:
    """Tier 2 requires it: an eval that moves on its own measures nothing."""

    def test_two_runs_of_the_same_request_are_identical(self) -> None:
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        request = _request(answer)
        drafter = ExtractiveDrafter()

        assert drafter.propose(request) == drafter.propose(request)

    def test_two_instances_of_the_backend_agree(self) -> None:
        answer = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.8)
        request = _request(answer)

        assert ExtractiveDrafter().propose(request) == ExtractiveDrafter().propose(request)


class TestThePageIsChosenByWhatTheQuestionStates:
    """ADR-089: the figures in the question decide which pages can answer it.

    Each case is a failure `docs/drafting-baseline.md` measured on the real
    retriever, reproduced here with the scores in the order it produced them.
    """

    def test_the_procedure_beats_the_overview_that_outscored_it(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=1.0)
        procedure = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.9)

        proposal = ExtractiveDrafter().propose(_request(overview, procedure, symptom="SYM-014"))

        assert proposal.kind is ProposalKind.REPAIR
        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 4)}

    def test_the_axis_the_question_names_beats_its_neighbour(self) -> None:
        axis_2 = _page(R2000IC, 8, document_id=R2000IC_DOC, score=0.99)
        axis_1 = _page(R2000IC, 7, document_id=R2000IC_DOC, score=0.95)

        proposal = ExtractiveDrafter().propose(_request(axis_2, axis_1, symptom="SYM-021"))

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 7)}
        assert any("90 g" in step.text for step in proposal.steps)

    def test_the_thai_question_chooses_the_same_page(self) -> None:
        axis_2 = _page(R2000IC, 8, document_id=R2000IC_DOC, score=0.99)
        axis_1 = _page(R2000IC, 7, document_id=R2000IC_DOC, score=0.95)

        proposal = ExtractiveDrafter().propose(
            _request(
                axis_2,
                axis_1,
                symptom="SYM-021",
                question=CORPUS.answer(SymptomCode("SYM-021")).queries.th,
            )
        )

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 7)}

    def test_a_symptom_no_page_states_is_not_found_at_any_score(self) -> None:
        """SYM-031: nothing in the corpus mentions a 62-second cycle time, and
        the fan page scored 0.95 against it. Principle 5 wants "not found"."""
        pages = [
            _page(M710IC, number, document_id=M710IC_DOC, score=0.95 - number / 100)
            for number in (3, 4, 5, 6)
        ]

        proposal = ExtractiveDrafter().propose(_request(*pages, symptom="SYM-031", model="M-710iC"))

        assert proposal.kind is ProposalKind.NOTHING
        assert proposal.steps == ()

    def test_a_question_with_no_figures_still_ranks_by_score(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=1.0)
        procedure = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.9)

        proposal = ExtractiveDrafter().propose(
            _request(overview, procedure, question="the belt motor is overheating")
        )

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 3)}


class TestARelevanceScoredRequest:
    """ADR-097: when scores are reranker relevances, a procedure page scored
    nearly as high as the best comes before a page that prescribes nothing."""

    def test_the_procedure_beats_the_overview_it_nearly_ties(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=0.99)
        procedure = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.87)

        proposal = ExtractiveDrafter().propose(
            _request(overview, procedure, question="the belt motor is overheating").model_copy(
                update={"relevance_scored": True}
            )
        )

        assert proposal.kind is ProposalKind.REPAIR
        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 4)}

    def test_a_weakly_relevant_procedure_does_not_beat_a_strong_answer(self) -> None:
        overview = _page(R2000IC, 3, document_id=R2000IC_DOC, score=0.99)
        procedure = _page(R2000IC, 4, document_id=R2000IC_DOC, score=0.2)

        proposal = ExtractiveDrafter().propose(
            _request(overview, procedure, question="the belt motor is overheating").model_copy(
                update={"relevance_scored": True}
            )
        )

        assert {step.cites for step in proposal.steps} == {(R2000IC_DOC, 3)}


class TestWhatIsNotAStep:
    """ADR-098: shapes from a real manual that are numbered and are not steps."""

    @staticmethod
    def _proposal(text: str):  # type: ignore[no-untyped-def]
        page = Evidence(
            document_id=R2000IC_DOC,
            page=66,
            text=text,
            title="manual",
            machine_model=MachineModel("R-2000iC"),
            score=0.9,
        )
        return ExtractiveDrafter().propose(_request(page, question="bearing noise"))

    def test_parenthesised_section_numbers_are_not_steps(self) -> None:
        proposal = self._proposal(
            "(1) Inspection It is recommended to make the following checks periodically. "
            "(a) Check the bearings for unusual noise. (2) Life The following parts must be "
            "changed periodically as listed below."
        )

        assert proposal.kind is ProposalKind.DIAGNOSTIC

    def test_numbered_footnotes_are_not_steps(self) -> None:
        proposal = self._proposal(
            "Note 1. There is no manual release mechanism, so use a separate supply. "
            "2. The value for initial ON gap at 20 degrees. 3. The brake gap will increase "
            "as the lining wears."
        )

        assert proposal.kind is ProposalKind.DIAGNOSTIC

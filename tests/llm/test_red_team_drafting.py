"""Red team: drafts that read as complete and are not (ADR-108).

Each case is a way a plausible, wrong procedure could reach a technician. They
were written before the fix, as failing tests, and each states what must happen
instead. The page texts are made up to carry one shape each; the shapes are
ones real manuals have.
"""

from __future__ import annotations

from pdm.contracts import DocumentId, MachineModel, SymptomCode
from pdm.llm.domain import DraftRequest, Evidence, ProposalKind
from pdm.llm.extractive import ExtractiveDrafter

DOC = DocumentId("c" * 64)


def _propose(text: str):  # type: ignore[no-untyped-def]
    page = Evidence(
        document_id=DOC,
        page=12,
        text=text,
        title="manual",
        machine_model=MachineModel("R-2000iC"),
        score=0.9,
    )
    return ExtractiveDrafter().propose(
        DraftRequest(
            symptom_code=SymptomCode("SYM-900"),
            machine_model=MachineModel("R-2000iC"),
            question="hydraulic unit pressure loss",
            evidence=(page,),
        )
    )


STEPS = (
    "1. Switch off the hydraulic unit and lock the isolator in the off position. "
    "2. Open the drain valve and bleed the line until the gauge reads zero. "
    "3. Replace the filter element and tighten the housing to 25 Nm. "
    "4. Close the drain valve, restore power and check for leaks at the housing."
)


class TestAWarningOnThePageReachesTheDraft:
    """A warning printed before the steps is part of doing them safely. A draft
    that keeps the steps and drops the warning reads as complete."""

    def test_a_warning_before_the_steps_leads_the_draft(self) -> None:
        proposal = _propose(
            "WARNING: Stored pressure remains in the accumulator after shutdown. "
            "Bleeding the line is required before any fitting is opened. " + STEPS
        )

        assert proposal.kind is ProposalKind.REPAIR
        assert proposal.steps[0].text.startswith("WARNING: Stored pressure remains")
        assert len(proposal.steps) == 5

    def test_a_caution_after_the_steps_is_kept_too(self) -> None:
        proposal = _propose(
            STEPS + "\nCAUTION: Do not reuse the housing O-ring; fit the new one "
            "supplied with the element."
        )

        assert proposal.steps[0].text.startswith("CAUTION: Do not reuse")
        assert "CAUTION" not in proposal.steps[-1].text

    def test_a_page_with_no_warning_drafts_its_steps_alone(self) -> None:
        proposal = _propose(STEPS)

        assert len(proposal.steps) == 4
        assert proposal.steps[0].text.startswith("Switch off the hydraulic unit")


class TestAProcedureCutShortIsNotARepair:
    """A page that ends inside a step, with no "continued", has lost the rest of
    the procedure. Drafting what is left would hand over a repair without its
    last steps."""

    def test_a_last_step_that_stops_mid_sentence_is_refused(self) -> None:
        proposal = _propose(
            "1. Switch off the hydraulic unit and lock the isolator in the off position. "
            "2. Open the drain valve and bleed the line until the gauge reads zero. "
            "3. Replace the filter element and tighten the housing to"
        )

        assert proposal.kind is not ProposalKind.REPAIR


class TestNumberingOutOfOrderIsNotAProcedure:
    """A list numbered 1, 2, 4, 3 has been scrambled by extraction or is two
    lists interleaved. Reading it as 1, 2, 3 silently drops or merges a step."""

    def test_a_skipped_then_late_number_is_refused(self) -> None:
        proposal = _propose(
            "1. Switch off the hydraulic unit and lock the isolator in the off position. "
            "2. Open the drain valve and bleed the line until the gauge reads zero. "
            "4. Close the drain valve, restore power and check for leaks at the housing. "
            "3. Replace the filter element and tighten the housing to 25 Nm."
        )

        assert proposal.kind is not ProposalKind.REPAIR

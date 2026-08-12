"""Parsing what a model server sends back, with no model server (ADR-037 §9).

The transport is injected, so these run in tier 1. What is tested is the part
that will actually go wrong in the plant: a reply that is almost right. A model
that cites a page label it was never given, one that answers with prose instead
of JSON, one that reports a duration as a string - none of those raise anything
by themselves, and each of them would otherwise become a draft.

What the model *says* is not tested here and cannot be: that needs the model,
which is tier 3.
"""

from __future__ import annotations

import json

import pytest

from pdm.contracts import DocumentId, MachineModel, SymptomCode
from pdm.llm.domain import DraftRequest, Evidence, ProposalKind
from pdm.llm.server import LlmServerDrafter, ModelServerError

DOC = DocumentId("a" * 64)
OTHER = DocumentId("b" * 64)

EVIDENCE = Evidence(
    document_id=DOC,
    page=4,
    text="4. Retighten the motor mount bolts to 42 Nm.",
    title="R-2000iC Maintenance Manual",
    machine_model=MachineModel("R-2000iC"),
    score=0.8,
)
REQUEST = DraftRequest(
    symptom_code=SymptomCode("SYM-014"),
    machine_model=MachineModel("R-2000iC"),
    question="belt motor running above 85 degrees",
    evidence=(EVIDENCE,),
)


def _answering(content: object) -> LlmServerDrafter:
    """A drafter whose server replies with this, whatever it is asked."""
    payload = content if isinstance(content, str) else json.dumps(content)

    def transport(url: str, body: bytes, timeout: float) -> bytes:
        return json.dumps({"message": {"content": payload}}).encode()

    return LlmServerDrafter(model="test", transport=transport)


class TestAWellFormedReply:
    def test_a_step_is_resolved_to_the_page_its_label_stood_for(self) -> None:
        drafter = _answering(
            {
                "kind": "repair",
                "steps": [{"text": "Retighten the motor mount bolts to 42 Nm.", "evidence": 1}],
                "tools": ["torque wrench 5-60 Nm"],
                "required_skill": "robot mechanical",
                "estimated_minutes": 45,
            }
        )
        proposal = drafter.propose(REQUEST)

        assert proposal.kind is ProposalKind.REPAIR
        assert proposal.steps[0].cites == (DOC, 4)
        assert proposal.estimated_minutes == 45
        assert proposal.required_skill == "robot mechanical"

    def test_nothing_is_a_valid_answer(self) -> None:
        proposal = _answering({"kind": "nothing", "steps": []}).propose(REQUEST)
        assert proposal.kind is ProposalKind.NOTHING


class TestARepliesThatIsAlmostRight:
    def test_a_label_pointing_at_a_page_that_was_never_offered_is_dropped(self) -> None:
        """Not resolved to "probably page 4". A citation is checkable or it is
        not, and a guessed one is the kind of provenance principle 2 exists to
        make impossible."""
        proposal = _answering(
            {"kind": "repair", "steps": [{"text": "Retighten the bolts.", "evidence": 7}]}
        ).propose(REQUEST)

        assert proposal.steps == ()

    def test_prose_instead_of_json_is_an_error_not_an_empty_draft(self) -> None:
        with pytest.raises(ModelServerError, match="JSON"):
            _answering("Here is the procedure you asked for:").propose(REQUEST)

    def test_a_kind_nobody_defined_is_an_error(self) -> None:
        with pytest.raises(ModelServerError, match="kind="):
            _answering({"kind": "maintenance", "steps": []}).propose(REQUEST)

    def test_an_empty_step_is_dropped_rather_than_becoming_an_empty_instruction(self) -> None:
        proposal = _answering(
            {"kind": "repair", "steps": [{"text": "   ", "evidence": 1}]}
        ).propose(REQUEST)

        assert proposal.steps == ()

    def test_a_duration_that_is_not_a_number_is_left_unset(self) -> None:
        proposal = _answering(
            {
                "kind": "repair",
                "steps": [{"text": "Retighten the motor mount bolts to 42 Nm.", "evidence": 1}],
                "estimated_minutes": "about an hour",
            }
        ).propose(REQUEST)

        assert proposal.estimated_minutes is None


class TestTheServerItself:
    def test_a_server_that_cannot_be_reached_says_so(self) -> None:
        def transport(url: str, body: bytes, timeout: float) -> bytes:
            raise ModelServerError(f"{url}: connection refused")

        drafter = LlmServerDrafter(model="test", transport=transport)
        with pytest.raises(ModelServerError, match="connection refused"):
            drafter.propose(REQUEST)

    def test_no_request_is_made_when_there_is_no_evidence(self) -> None:
        """A GPU is not asked to look at nothing.

        Drafting runs over a list of symptoms; the ones the corpus is silent
        about would otherwise each cost a model call to be told what retrieval
        already said.
        """
        calls: list[str] = []

        def transport(url: str, body: bytes, timeout: float) -> bytes:
            calls.append(url)
            return b"{}"

        empty = DraftRequest(
            symptom_code=SymptomCode("SYM-031"),
            machine_model=MachineModel("M-710iC"),
            question="cycle time drifting",
            evidence=(),
        )
        proposal = LlmServerDrafter(model="test", transport=transport).propose(empty)

        assert proposal.kind is ProposalKind.NOTHING
        assert calls == []

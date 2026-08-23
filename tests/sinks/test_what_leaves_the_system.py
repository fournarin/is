"""The port, with no destination present at all (ADR-012, ADR-068).

`Ticket` and `OwnSystemSink` are pure, which is the whole argument for building
layer 4 before anybody knows what is on the other side: the shape of what leaves
can be settled, and tested, without a CMMS, a chat client or a network.

The assertions worth having here are about what a destination is *not* told and
what it is never told without - not about field-by-field copying, which would
only restate the code.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    DocumentId,
    MachineId,
    PlaybookStep,
    Severity,
    SkillId,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
)
from pdm.sinks import DeliveryFailed, OwnSystemSink, Receipt, Ticket, TicketSink

REF = WorkOrderRef("WO-000123")
NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)

STEPS = (
    PlaybookStep(
        text="Lock out the cell at the main isolator before opening the fence.",
        source_doc=DocumentId("R-2000iC maintenance"),
        page=41,
        confidence=0.92,
    ),
    PlaybookStep(
        text="Torque the J2 reducer bolts to 45 Nm in a crosswise order.",
        source_doc=DocumentId("R-2000iC maintenance"),
        page=42,
        confidence=0.88,
    ),
)


def an_order(**overrides: object) -> WorkOrder:
    fields: dict[str, object] = {
        "origin": WorkOrderOrigin.MANUAL,
        "machine_id": MachineId("MC-012"),
        "severity": Severity.HIGH,
        "reason": "reported by an operator: grinding from the J2 axis",
        "priority_reason": "the shift is at 64% (normal load), bottleneck station",
        "estimated_minutes": 45,
        "required_skill": SkillId("robot_mechanical"),
        "required_technicians": 1,
        "assignees": (Assignee(user=UserId("tech-ana"), role=AssigneeRole.PRIMARY),),
        "playbook_snapshot": STEPS,
    }
    fields.update(overrides)
    return WorkOrder(**fields)  # type: ignore[arg-type]


class TestWhatADestinationIsTold:
    def test_the_steps_and_their_warning_travel_together(self) -> None:
        """ADR-018 serves a playbook awaiting review on the argument that an
        out-of-date procedure beats none - which holds only while the person
        holding it can tell which they have. A destination given the steps
        without the warning breaks that where somebody is at a machine."""
        warned = an_order(playbook_warning="the manual this came from was replaced on 12 March")

        ticket = Ticket.of(REF, warned)

        assert ticket.steps == STEPS
        assert ticket.playbook_warning == "the manual this came from was replaced on 12 March"

    def test_both_reasons_leave_because_they_answer_different_questions(self) -> None:
        """`reason` is why the job exists and `priority_reason` is why it is
        ranked here (ADR-005, ADR-041). A destination given one of them answers
        whichever question was asked last."""
        ticket = Ticket.of(REF, an_order())

        assert "grinding from the J2 axis" in ticket.reason
        assert "bottleneck station" in ticket.priority_reason

    def test_the_scheduler_s_own_arithmetic_does_not_leave(self) -> None:
        """`priority_score` is layer 3's internal number. A CMMS has no column
        for it and a technician cannot act on it, and a destination that stored
        it would invite somebody to compare two systems' scores."""
        assert "priority_score" not in Ticket.model_fields

    def test_a_ticket_cannot_be_built_without_a_reason(self) -> None:
        """Principle 3 in the one place it would be easiest to lose: the copy
        made on the way out."""
        with pytest.raises(ValueError):
            Ticket.of(REF, an_order(reason=""))


class TestTheDestinationThatIsAlreadyHere:
    def test_it_satisfies_the_port(self) -> None:
        sink: TicketSink = OwnSystemSink()
        assert sink.destination == "own-system"

    def test_the_receipt_points_back_at_the_order(self) -> None:
        """A destination with no identifier of its own says so by returning the
        work order's ref, rather than by returning nothing (ADR-068 §1)."""
        receipt = OwnSystemSink().deliver(Ticket.of(REF, an_order()))

        assert receipt == Receipt(external_ref="WO-000123")

    def test_delivering_twice_says_the_same_thing(self) -> None:
        """At-least-once is what ADR-068 chose, so every adapter has to be safe
        to call again. The thin one is where that is cheapest to prove."""
        ticket = Ticket.of(REF, an_order())
        sink = OwnSystemSink()

        assert sink.deliver(ticket) == sink.deliver(ticket)


class TestRefusalIsRaisedRatherThanReturned:
    def test_a_refusal_is_an_exception(self) -> None:
        """ADR-068 §3. An adapter that returned a status would let a forgotten
        check report success, which is a silent hole rather than a loud one."""
        assert issubclass(DeliveryFailed, Exception)

    def test_the_message_is_what_somebody_reads_days_later(self) -> None:
        error = DeliveryFailed("the CMMS answered 503 for work order WO-000123")

        assert "503" in str(error)

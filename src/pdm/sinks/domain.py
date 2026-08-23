"""Layer 4's port: what a destination is given, and what it says back (ADR-012, ADR-068).

Nothing here touches a database or a network. The port is a shape, the ticket is
a copy, and both are testable with no destination present at all - which is the
point, because the destination is the one thing this project does not yet know
(ADR-012).
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    Assignee,
    MachineId,
    PlaybookStep,
    Severity,
    SkillId,
    WorkOrder,
    WorkOrderRef,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Ticket(BaseModel):
    """What leaves the system, which is less than a work order.

    A CMMS has no column for `priority_score` and a chat client has no columns
    at all. What every destination needs is the same short list: which machine,
    what to do, why now, who it is for, and how long it should take. The order
    keeps the rest, and `work_order_ref` is how anything out there points back
    at it.

    `steps` and `playbook_warning` travel together and always. ADR-018 serves a
    playbook that is awaiting review on the argument that a technician with an
    out-of-date procedure is better off than one with none - which holds only
    while they can tell which they have. A destination that received the steps
    without the warning would break that in the one place where somebody is
    standing at a machine.
    """

    model_config = _FROZEN

    work_order_ref: WorkOrderRef
    machine_id: MachineId
    severity: Severity
    # Why the job exists, and why it is ranked here. Two questions, two people,
    # and one field would answer whichever was asked last (ADR-005, ADR-041).
    reason: str = Field(min_length=1)
    priority_reason: str

    estimated_minutes: int = Field(gt=0)
    required_skill: SkillId | None
    required_technicians: int = Field(ge=1)
    assignees: tuple[Assignee, ...]

    steps: tuple[PlaybookStep, ...]
    playbook_warning: str | None

    @classmethod
    def of(cls, work_order_ref: WorkOrderRef, order: WorkOrder) -> Ticket:
        """Copy an order into the shape a destination is handed.

        Built here rather than by each adapter, so that adding a destination
        cannot quietly change what a destination is told.
        """
        return cls(
            work_order_ref=work_order_ref,
            machine_id=order.machine_id,
            severity=order.severity,
            reason=order.reason,
            priority_reason=order.priority_reason,
            estimated_minutes=order.estimated_minutes,
            required_skill=order.required_skill,
            required_technicians=order.required_technicians,
            assignees=order.assignees,
            steps=order.playbook_snapshot,
            playbook_warning=order.playbook_warning,
        )


class Receipt(BaseModel):
    """What the destination says back, and the reason delivery has a return value.

    `external_ref` is the destination's own identifier - a CMMS work-order
    number, a chat message id. It is stored because it is the only thing that
    can ever reconcile the two systems: without it, "did this ticket reach the
    CMMS" is answered by our own record of having tried, which is exactly the
    answer nobody believes during an incident.

    A destination with no identifier of its own returns the work order's ref.
    That is honest rather than empty: it says the ticket is where it started.
    """

    model_config = _FROZEN

    external_ref: str = Field(min_length=1)


class DeliveryFailed(Exception):
    """The destination did not take the ticket.

    Raised rather than returned, so that an adapter which forgets to check a
    status code fails loudly instead of reporting success. The message is stored
    on the delivery record and is what somebody reads when they ask why a ticket
    never arrived, so it should name the destination and what it said.
    """


class TicketSink(Protocol):
    """Layer 4. One method, and a name for the record.

    The scheduler never learns which implementation is behind this (ADR-012),
    and `.importlinter` forbids `pdm.dispatch` and `pdm.work` from importing
    this module at all - not merely from importing a concrete sink. Delivery is
    a step the composition root takes after a round, which is what makes that
    ban possible to state absolutely.
    """

    @property
    def destination(self) -> str:
        """Recorded on every delivery. Short, stable, and written in the log."""

    def deliver(self, ticket: Ticket) -> Receipt:
        """Hand the ticket over, or raise `DeliveryFailed`.

        Must be safe to call again for the same ticket. At-least-once is what
        ADR-068 chose, so a destination that cannot deduplicate will one day see
        the same ticket twice.
        """

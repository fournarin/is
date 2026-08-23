"""The destination that is already here (ADR-012, ADR-068).

A ticket placed by a round is written on the work order, and the technician's
screen reads it from there. So for our own system, delivery has nothing to
carry: the receipt is the work order's own ref, and the delivery record says
where the ticket went and when.

That is a thin adapter, and it is thin for the right reason. ADR-012's argument
is that the outbound layer must be cheap to change while the CMMS question is
open; the first destination happening to be the same database is what makes this
one short, not a weakness in the port. What the slice actually builds is the
record and the retry - and those have to exist before the destination is
somebody else's system, because that is not a week in which to design them.
"""

from __future__ import annotations

from pdm.sinks.domain import Receipt, Ticket


class OwnSystemSink:
    """Delivers by confirming. Never raises, and cannot.

    Deliberately not given a connection. A sink that could write to the work
    order would be a second place that decides what a technician sees, and the
    round is already that place.
    """

    @property
    def destination(self) -> str:
        return "own-system"

    def deliver(self, ticket: Ticket) -> Receipt:
        return Receipt(external_ref=str(ticket.work_order_ref))

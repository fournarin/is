"""Layer 4 in a process: the step that takes placed tickets to their destination.

Called by the composition root after a scheduling round, never by layer 3.
`dispatch()` decides who does what and when; whether the ticket arrived is a
different question with a different answer, and ADR-012's claim that the
scheduler does not know where tickets land is only checkable as an absolute
import ban if this step lives outside it.

Everything here runs in the caller's transaction, so a round's placements and
the record of what left because of them commit together (ADR-017).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from psycopg import Connection

from pdm.contracts import WorkOrderRef
from pdm.platform.clock import Clock
from pdm.sinks import repo
from pdm.sinks.domain import DeliveryFailed, Ticket, TicketSink
from pdm.work import repo as work_repo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryReport:
    """What one pass did, for the log and for a test to assert on."""

    delivered: tuple[WorkOrderRef, ...] = ()
    failed: tuple[WorkOrderRef, ...] = ()

    @property
    def worth_reporting(self) -> bool:
        return bool(self.delivered or self.failed)


class Deliveries:
    """One sink, and the outstanding tickets it has not taken yet.

    Takes its sink rather than choosing one, so the composition root stays the
    only place that decides what talks to what - and so slice 12.2 can make the
    choice configuration rather than an edit here.
    """

    def __init__(self, sink: TicketSink, clock: Clock, *, batch: int = 50) -> None:
        self.sink = sink
        self.clock = clock
        # A cap, not a rate limit. A destination that has been down all night
        # leaves a backlog, and a round that tried to drain it in one pass would
        # hold its transaction open across hundreds of calls to somebody else's
        # system while the next round waited. The rest go out next round, in the
        # order they were decided.
        self.batch = batch

    def run(self, conn: Connection[Any], *, placed: Sequence[WorkOrderRef] = ()) -> DeliveryReport:
        """Queue this round's placements, then take what is outstanding.

        Queueing and sending are separate on purpose. The queue row is written
        in the same transaction as the placement that caused it, so a ticket can
        never be placed without something knowing it has to go out; sending then
        works from the table rather than from this round's list, which is what
        makes a failure last round indistinguishable from a placement this one.
        """
        repo.queue(conn, placed, at=self.clock.now())

        delivered: list[WorkOrderRef] = []
        failed: list[WorkOrderRef] = []

        for ref in repo.outstanding(conn, limit=self.batch):
            order = work_repo.get(conn, str(ref))
            if order is None:
                # The foreign key should make this unreachable - deleting an
                # order takes its delivery row with it. Recorded as a failure
                # rather than skipped, because a row whose attempts climb while
                # nothing is wrong with the destination is how somebody finds
                # out that something else is (ADR-068: there is no attempt cap).
                self._refuse(conn, ref, error=f"no work order {ref} to send")
                failed.append(ref)
                continue

            try:
                receipt = self.sink.deliver(Ticket.of(ref, order))
            except DeliveryFailed as error:
                # Only this one. Anything else is a defect rather than a
                # destination saying no, and it takes the round's transaction
                # down so the job queue retries the whole thing (ADR-068).
                self._refuse(conn, ref, error=str(error) or error.__class__.__name__)
                failed.append(ref)
                continue

            repo.record_delivered(
                conn,
                ref,
                destination=self.sink.destination,
                external_ref=receipt.external_ref,
                at=self.clock.now(),
            )
            delivered.append(ref)

        return DeliveryReport(delivered=tuple(delivered), failed=tuple(failed))

    def _refuse(self, conn: Connection[Any], ref: WorkOrderRef, *, error: str) -> None:
        repo.record_failed(
            conn, ref, destination=self.sink.destination, error=error, at=self.clock.now()
        )


def describe(report: DeliveryReport) -> str:
    """One line, for the worker's log."""
    parts = [f"{len(report.delivered)} delivered"]
    if report.failed:
        parts.append(f"{len(report.failed)} refused, retried next round")
    return ", ".join(parts)

"""A destination that is a directory (ADR-012, ADR-069).

The second sink, and the reason it exists is that one implementation never
proves an interface. With a single sink `TicketSink` was a class with one
subclass; this is what makes "swappable" a property something can fail on.

It is also the shape a real outbound integration has and `OwnSystemSink` does
not: a ticket leaves this process, lands somewhere this process does not own,
and can fail on the way. A directory that is not writable is the cheapest
honest version of a CMMS that is down.

Nothing here touches the database. A sink that could write to a work order
would be a second place deciding what a technician sees, and the round is
already that place.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pdm.platform.clock import Clock
from pdm.sinks.domain import DeliveryFailed, Receipt, Ticket


class FileSink:
    """One ticket, one file, named for the work order.

    Named for the work order rather than for the time, so that delivering the
    same ticket twice overwrites rather than accumulates. At-least-once is what
    ADR-068 chose, and a destination that grows a file per attempt turns a
    retry loop into a full disk.
    """

    def __init__(self, directory: Path, clock: Clock) -> None:
        self.directory = directory
        self.clock = clock

    @property
    def destination(self) -> str:
        return "file"

    def deliver(self, ticket: Ticket) -> Receipt:
        path = self.directory / f"{ticket.work_order_ref}.json"
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            path.write_text(self._document(ticket, at=self.clock.now()), encoding="utf-8")
        except OSError as error:
            # The message is stored on the delivery record and is what somebody
            # reads days later when they ask why a ticket never arrived, so it
            # names the path rather than only the errno (ADR-068 §1).
            raise DeliveryFailed(f"could not write {path}: {error}") from error
        return Receipt(external_ref=str(path))

    def _document(self, ticket: Ticket, *, at: datetime) -> str:
        """The ticket as JSON, plus when it was written.

        `written_at` is the sink's own, not the ticket's: it is a fact about the
        delivery rather than about the work, and the work order already holds
        every time that belongs to the job.
        """
        return json.dumps(
            {"written_at": at.isoformat(), "ticket": ticket.model_dump(mode="json")},
            ensure_ascii=False,  # Thai in `reason` and the steps, readable as itself
            indent=2,
        )

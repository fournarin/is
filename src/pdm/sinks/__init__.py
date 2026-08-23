"""Ticket destinations behind an adapter interface (layer 4).

The scheduler never learns whether a ticket lands in a CMMS, in our own system
or in a chat client (ADR-012). `.importlinter` states that as an absolute ban -
`pdm.dispatch` and `pdm.work` may not import this package at all - which is
possible only because delivery is a step the composition root takes after a
round rather than something layer 3 does (ADR-068).
"""

from pdm.sinks.domain import DeliveryFailed, Receipt, Ticket, TicketSink
from pdm.sinks.file import FileSink
from pdm.sinks.own_system import OwnSystemSink
from pdm.sinks.service import Deliveries, DeliveryReport, describe

__all__ = [
    "Deliveries",
    "DeliveryFailed",
    "DeliveryReport",
    "FileSink",
    "OwnSystemSink",
    "Receipt",
    "Ticket",
    "TicketSink",
    "describe",
]

"""Put an order where a confirmed round leaves it: released to the floor.

ADR-101: a technician may take only work a person released. Tests that are about
working a job, not about dispatching it, start from there.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from pdm.contracts import WorkOrderStatus
from pdm.work import repo


def released(conn: Connection[Any], ref: str) -> str:
    repo.set_status(conn, ref, status=WorkOrderStatus.ASSIGNED)
    return ref

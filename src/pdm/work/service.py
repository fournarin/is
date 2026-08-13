"""Issuing work orders: bind the playbook, price the job, write the row.

The one module that turns a source of work into something a technician can be
sent. It opens no connection - the caller supplies one - so that the order and
whatever produced it commit together (ADR-017).

**It reads the playbook store and layer 3 never will.** Everything the scheduler
needs is copied onto the order here (ADR-041), which is what keeps `dispatch()` a
pure function of its inputs (invariant 10).
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from pdm.contracts import (
    Finding,
    FindingRef,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PMTask,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
)
from pdm.platform.clock import Clock
from pdm.playbooks import repo as playbooks
from pdm.work import domain, repo


class Issued:
    """A written order and the ticket number it was given.

    Two values rather than a field on the contract: the reference is the
    database's, and a `WorkOrder` that carried one could be built without it
    ever having been written down.
    """

    __slots__ = ("order", "ref")

    def __init__(self, ref: str, order: WorkOrder) -> None:
        self.ref = ref
        self.order = order

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"Issued({self.ref!r}, {self.order.origin.value})"


class WorkOrders:
    """Creation and lifecycle. One instance per process, no state between calls."""

    def __init__(self, clock: Clock, *, fallback_minutes: dict[str, dict[Severity, int]]) -> None:
        self.clock = clock
        # From policy.yaml, held rather than read: a second reader would be a
        # second answer to how long an unpriced job takes (design.md 3.2).
        self.fallback_minutes = fallback_minutes

    def _playbook(
        self, conn: Connection[Any], symptom_code: SymptomCode, machine_model: MachineModel
    ) -> Playbook | None:
        """The approved playbook for this pair, or nothing.

        A `needs_review` playbook is still bound. It was approved once, it is
        still served with a warning (ADR-018), and refusing it here would leave
        the job unpriced and unschedulable the moment a manual is replaced -
        turning a warning into an outage.
        """
        found = playbooks.get(conn, symptom_code, machine_model)
        if found is None:
            return None
        playbook, _ = found
        return playbook if playbook.status is not PlaybookStatus.DRAFT else None

    def from_finding(
        self,
        conn: Connection[Any],
        finding: Finding,
        *,
        finding_ref: FindingRef,
        machine_model: MachineModel,
    ) -> Issued:
        """A Finding becomes a ticket. Layer 1 will call this; nothing does yet."""
        order = domain.from_finding(
            finding,
            finding_ref,
            playbook=self._playbook(conn, finding.symptom_code, machine_model),
            machine_model=machine_model,
            fallback_minutes=self.fallback_minutes,
        )
        return Issued(repo.issue(conn, order, now=self.clock.now()), order)

    def from_pm_task(
        self,
        conn: Connection[Any],
        task: PMTask,
        *,
        machine_model: MachineModel,
        severity: Severity = domain.PM_SEVERITY,
    ) -> Issued:
        order = domain.from_pm_task(
            task,
            playbook=self._playbook(conn, task.symptom_code, machine_model),
            machine_model=machine_model,
            fallback_minutes=self.fallback_minutes,
            severity=severity,
        )
        return Issued(repo.issue(conn, order, now=self.clock.now()), order)

    def from_report(
        self,
        conn: Connection[Any],
        *,
        machine_id: MachineId,
        machine_model: MachineModel,
        severity: Severity,
        reported_by: UserId,
        description: str,
        symptom_code: SymptomCode | None = None,
    ) -> Issued:
        """Somebody saw something.

        `symptom_code` is optional because the person reporting may not know
        which one it is - and a report with no code still has to become a ticket,
        or the system quietly requires a diagnosis before it will accept a
        problem.
        """
        playbook = (
            self._playbook(conn, symptom_code, machine_model) if symptom_code is not None else None
        )
        now = self.clock.now()
        order = domain.from_report(
            machine_id=machine_id,
            severity=severity,
            reported_by=reported_by,
            description=description,
            playbook=playbook,
            machine_model=machine_model,
            fallback_minutes=self.fallback_minutes,
            now=now,
        )
        return Issued(repo.issue(conn, order, now=now), order)

    def open_orders(self, conn: Connection[Any]) -> list[tuple[str, WorkOrder]]:
        """What the dispatch tick will be given (design.md 6.2)."""
        return repo.open_orders(conn)

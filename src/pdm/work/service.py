"""Issuing work orders: bind the playbook, price the job, write the row.

The one module that turns a source of work into something a technician can be
sent. It opens no connection - the caller supplies one - so that the order and
whatever produced it commit together (ADR-017).

**It reads the playbook store and layer 3 never will.** Everything the scheduler
needs is copied onto the order here (ADR-041), which is what keeps `dispatch()` a
pure function of its inputs (invariant 10).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection

from pdm.contracts import (
    Assignee,
    BlockedReason,
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
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.platform.clock import Clock
from pdm.playbooks import repo as playbooks
from pdm.work import domain, repo


class NoSuchOrder(LookupError):
    """There is no order with that reference."""


class TransitionRefused(Exception):
    """The order is not in a state where this makes sense.

    A conflict rather than a failure: the person pressed a real button on a real
    ticket, and what refuses them is the state the order is in - somebody else
    has it, they never accepted it, it ended an hour ago. The message says which,
    because a technician standing at a machine cannot read a stack trace.
    """


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
    ) -> tuple[Playbook | None, str | None]:
        """The playbook for this pair and the warning that travels with it.

        A `needs_review` playbook is still bound. It was approved once, it is
        still served (ADR-018), and refusing it here would leave the job unpriced
        and unschedulable the moment a manual is replaced - turning a warning
        into an outage.

        **The warning is returned rather than dropped.** The review screen is not
        the serving surface for it; the ticket is, and it is the one a technician
        reads at the machine (ADR-041 section 6).

        The store cannot hold a draft at all - that is a state the table has no
        value for (ADR-038) - so there is nothing to filter here.
        """
        found = playbooks.get(conn, symptom_code, machine_model)
        if found is None:
            return (None, None)
        playbook, review_reason = found
        if playbook.status is PlaybookStatus.NEEDS_REVIEW:
            return (
                playbook,
                review_reason
                or "this procedure is awaiting review and may not match the current manual",
            )
        return (playbook, None)

    def from_finding(
        self,
        conn: Connection[Any],
        finding: Finding,
        *,
        finding_ref: FindingRef,
        machine_model: MachineModel,
    ) -> Issued:
        """A Finding becomes a ticket. Layer 1 will call this; nothing does yet."""
        playbook, warning = self._playbook(conn, finding.symptom_code, machine_model)
        order = domain.from_finding(
            finding,
            finding_ref,
            playbook_warning=warning,
            playbook=playbook,
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
        playbook, warning = self._playbook(conn, task.symptom_code, machine_model)
        order = domain.from_pm_task(
            task,
            playbook_warning=warning,
            playbook=playbook,
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
        playbook, warning = (
            self._playbook(conn, symptom_code, machine_model)
            if symptom_code is not None
            else (None, None)
        )
        now = self.clock.now()
        order = domain.from_report(
            machine_id=machine_id,
            severity=severity,
            reported_by=reported_by,
            description=description,
            playbook=playbook,
            playbook_warning=warning,
            machine_model=machine_model,
            fallback_minutes=self.fallback_minutes,
            now=now,
        )
        return Issued(repo.issue(conn, order, now=now), order)

    # ── the four buttons a technician has (ADR-024, ADR-025, ADR-056) ────
    #
    # Every one of them reads the row under a lock, decides from what it read,
    # and writes. Deciding from a stale read is what puts two primaries on one
    # ticket or two open segments on one person, and both are wrong in a way
    # nothing downstream can detect: the first doubles the capacity the
    # scheduler reserves, the second doubles the minutes the estimate learns
    # from.

    def _live(self, conn: Connection[Any], ref: str) -> WorkOrder:
        order = repo.get_for_update(conn, ref)
        if order is None:
            raise NoSuchOrder(f"no work order {ref}")
        if order.status not in domain.STILL_LIVE:
            raise TransitionRefused(
                f"{ref} is {order.status.value} and nothing moves after that; "
                f"a new problem on this machine is a new ticket"
            )
        if order.status is WorkOrderStatus.PROPOSED:
            # Refused here rather than by the order being invisible (ADR-071 §7).
            # It should not be reachable - `GET /work-orders/mine` does not serve
            # proposals - and a technician who got to it through a link they kept
            # is owed the reason rather than a job that does nothing when pressed.
            raise TransitionRefused(
                f"{ref} is waiting for a supervisor to confirm it and is not yours yet"
            )
        return order

    def _reread(self, conn: Connection[Any], ref: str) -> WorkOrder:
        order = repo.get(conn, ref)
        if order is None:  # pragma: no cover - the row is locked by this transaction
            raise NoSuchOrder(f"no work order {ref}")
        return order

    def accept(self, conn: Connection[Any], ref: str, *, user: UserId) -> WorkOrder:
        """A technician takes the job (ADR-024: technicians, and only them).

        Accepting one they already hold changes nothing rather than failing. The
        button is pressed on a phone at a machine on a network that drops, and a
        second press is not a mistake worth refusing.
        """
        order = self._live(conn, ref)
        if domain.holds_it(order, user):
            return order
        if len(order.assignees) >= order.required_technicians:
            held_by = ", ".join(str(one.user) for one in order.assignees)
            raise TransitionRefused(
                f"{ref} needs {order.required_technicians} and already has {held_by}"
            )
        repo.add_assignee(conn, ref, Assignee(user=user, role=domain.role_for_new_assignee(order)))
        # A helper joining a job somebody is already working must not push it
        # back to `assigned`; a handed-over job somebody picks up must leave that
        # status, or it reads as waiting for a shift that has started.
        if order.status in (WorkOrderStatus.QUEUED, WorkOrderStatus.HANDED_OVER):
            repo.set_status(conn, ref, status=WorkOrderStatus.ASSIGNED)
        return self._reread(conn, ref)

    def start(self, conn: Connection[Any], ref: str, *, user: UserId) -> WorkOrder:
        """Open a segment and put the order in progress.

        Refused for somebody who has not accepted it: the segment is a claim
        about who did the work, and the order has to be able to say whose
        capacity it is spending before it starts spending it.
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"{user} has not accepted {ref}")
        if domain.has_an_open_segment(order, user):
            raise TransitionRefused(
                f"{user} is already working on {ref}; a second segment would count "
                f"the same minutes twice"
            )
        repo.open_segment(conn, ref, user=user, now=self.clock.now())
        repo.set_status(conn, ref, status=WorkOrderStatus.IN_PROGRESS)
        return self._reread(conn, ref)

    def hand_over(self, conn: Connection[Any], ref: str, *, user: UserId, note: str) -> WorkOrder:
        """Put the job down for somebody else, and say how far it got.

        The note is checked before anything is written. ADR-025 asks for it
        because without it the next shift finds an open order and starts from
        step one, and a handover recorded without one would be worse than none -
        it would look complete.

        The handover ends this person's assignment (ADR-056). The order becomes
        `handed_over` only when nobody is left on it: a helper stepping off a job
        the primary is still working has not handed anything over.
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"{user} has not accepted {ref}")
        if not note.strip():
            raise ValueError(
                "handing over needs a note saying how far the job got; without it the "
                "next shift starts again from step one (ADR-025)"
            )

        repo.close_segments(conn, ref, user=user, now=self.clock.now())
        repo.remove_assignee(conn, ref, user)
        remaining = self._reread(conn, ref)
        repo.set_status(
            conn,
            ref,
            status=(WorkOrderStatus.HANDED_OVER if not remaining.assignees else remaining.status),
            handover_note=note.strip(),
        )
        return self._reread(conn, ref)

    def close(
        self,
        conn: Connection[Any],
        ref: str,
        *,
        user: UserId,
        outcome: WorkOutcome,
        blocked_minutes: int = 0,
        blocked_reason: tuple[BlockedReason, ...] = (),
        technician_feedback: str | None = None,
    ) -> WorkOrder:
        """End the job, with how it ended and what held it up.

        `outcome` is mandatory at the signature, so there is no call that can
        forget it. `no_problem_found` is one of the four and the most valuable of
        them: it is the only false-alarm signal the system will ever receive, and
        the loop that tunes rule thresholds does not exist without it (ADR-022).

        Every open segment is closed, not only this person's - one left open
        contributes nothing to `actual_minutes` and would silently discard the
        time somebody worked (ADR-056 §5).
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"{user} has not accepted {ref}")

        now = self.clock.now()
        worked = domain.minutes_worked_if_closed_at(order, now)
        if blocked_minutes > worked:
            # Refused rather than clamped. `repair_minutes` already floors at
            # zero, which keeps the arithmetic safe and hides the input that was
            # wrong - and these are the numbers Loop 1 learns estimates from.
            raise ValueError(
                f"{blocked_minutes} blocked minutes on a job of {worked} minutes: "
                f"waiting cannot be longer than the work it interrupted (ADR-056)"
            )
        if blocked_minutes > 0 and not blocked_reason:
            raise ValueError(
                "blocked minutes need a reason: parts, a line stop, or waiting for help"
            )

        repo.close_segments(conn, ref, now=now)
        repo.close(
            conn,
            ref,
            status=WorkOrderStatus.CLOSED,
            outcome=outcome,
            now=now,
            blocked_minutes=blocked_minutes,
            blocked_reason=blocked_reason,
            technician_feedback=technician_feedback,
        )
        return self._reread(conn, ref)

    def open_orders(self, conn: Connection[Any]) -> list[tuple[str, WorkOrder, datetime]]:
        """What the dispatch tick will be given (design.md 6.2)."""
        return repo.open_orders(conn)

    def assigned_to(self, conn: Connection[Any], user: UserId) -> list[tuple[str, WorkOrder]]:
        """This person's own live work, ranked as layer 3 ranked it (ADR-071 §7).

        The technician's screen reads this rather than recomputing a round, for
        the reason `repo.assigned_to` sets out: a job placed by a round is no
        longer `queued`, and a screen filtering what a fresh round *would* place
        loses it at the moment the system decides to give it to somebody.
        """
        return repo.assigned_to(conn, user)

    def open_finding_refs(self, conn: Connection[Any]) -> set[FindingRef]:
        """Findings that still have an open ticket against them (ADR-044 §6)."""
        return repo.open_finding_refs(conn)

    def withdraw_for_finding(self, conn: Connection[Any], finding_ref: FindingRef) -> list[str]:
        """Cancel the untouched orders for a Finding the world has overtaken.

        Returns what was cancelled, which is not the same as what was found: an
        order somebody has accepted is left where it is (ADR-044 §7).
        """
        return repo.cancel_untouched_for_finding(conn, finding_ref, now=self.clock.now())

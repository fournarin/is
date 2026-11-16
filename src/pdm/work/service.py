"""Issuing work orders: bind the playbook, price the job, write the row.

The one module that turns a source of work into something a technician can be
sent. It opens no connection - the caller supplies one - so that the order and
whatever produced it commit together (ADR-017).

**It reads the playbook store and layer 3 never will.** Everything the scheduler
needs is copied onto the order here (ADR-041), which is what keeps `dispatch()` a
pure function of its inputs (invariant 10).
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection

from pdm.contracts import (
    Assignee,
    BlockedReason,
    Finding,
    FindingRef,
    LockState,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PMTask,
    PMTaskRef,
    Severity,
    StepKind,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.contracts.wording import Wording
from pdm.platform.clock import Clock
from pdm.playbooks import repo as playbooks
from pdm.work import domain, locks, repo


class NoSuchOrder(LookupError):
    """There is no order with that reference."""


class AlreadyOpen(Exception):
    """This machine already has work open, and nobody has said this is different.

    ADR-023's argument at the manual origin. One line stops, four people see it,
    and without this the system dispatches four technicians to one fault. Carries
    the references rather than only a sentence, because the answer the reporter
    actually wants - *does anybody know about this yet?* - is those tickets, and
    the screen offering "this is something else" has to name them (ADR-077
    section 3).
    """

    def __init__(
        self,
        machine_id: MachineId,
        open_refs: Sequence[str],
        reasons: Sequence[str] = (),
        titles: Sequence[str] = (),
    ) -> None:
        self.machine_id = machine_id
        self.open_refs = tuple(open_refs)
        # What each open ticket is about, so the reporter can tell "same fault"
        # from "something else" without knowing a ticket number (ADR-126).
        self.reasons = tuple(reasons)
        # The same, as machine and symptom: one short line each (finding 20).
        self.titles = tuple(titles)
        joined = ", ".join(self.open_refs)
        super().__init__(
            f"{machine_id} already has work open: {joined}. If what you are reporting is "
            f"something else, send it again naming those tickets."
        )


class TransitionRefused(Exception):
    """The order is not in a state where this makes sense.

    A conflict rather than a failure: the person pressed a real button on a real
    ticket, and what refuses them is the state the order is in - somebody else
    has it, they never accepted it, it ended an hour ago. The message says which,
    because a technician standing at a machine cannot read a stack trace.
    """


class PmScan:
    """What one pass over the PM schedule did.

    Counted rather than logged, so a test can read it: a scan that found four
    tasks due and issued none is the unique index doing its job, and a return
    value carrying only the tickets would make it look like a scan where
    nothing was due (the argument `Tick` makes in the trigger loop).
    """

    __slots__ = ("due", "issued", "unpriced")

    def __init__(
        self, *, due: int, issued: tuple[str, ...], unpriced: tuple[PMTaskRef, ...]
    ) -> None:
        self.due = due
        self.issued = issued
        self.unpriced = unpriced

    @property
    def worth_reporting(self) -> bool:
        return bool(self.issued or self.unpriced)

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"PmScan(due={self.due}, issued={len(self.issued)}, unpriced={len(self.unpriced)})"


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


# Released to people: a helper may join, and a handed-over job may be picked up.
_TAKEABLE = frozenset(
    {WorkOrderStatus.ASSIGNED, WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.HANDED_OVER}
)


class WorkOrders:
    """Creation and lifecycle. One instance per process, no state between calls."""

    def __init__(
        self,
        clock: Clock,
        *,
        fallback_minutes: dict[str, dict[Severity, int]],
        wording: Wording | None = None,
    ) -> None:
        self.clock = clock
        # The plant's clock and names for every reason this writes (ADR-093).
        self.wording = wording or Wording()
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
            wording=self.wording,
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
            wording=self.wording,
        )
        return Issued(repo.issue(conn, order, now=self.clock.now()), order)

    def register_pm_tasks(
        self, conn: Connection[Any], tasks: Sequence[repo.PmTaskDefinition]
    ) -> None:
        """Mirror the configured schedule into the table (ADR-083 section 1)."""
        repo.register_pm_tasks(conn, tasks, now=self.clock.now())

    def issue_due_pm(
        self, conn: Connection[Any], *, machine_model: Callable[[MachineId], MachineModel]
    ) -> PmScan:
        """Every task that is due and has nothing in flight becomes one ticket.

        The scan and the tickets share the caller's transaction, so a task and
        the order it produced commit together or not at all (ADR-017). Which
        tasks are due is decided by `domain.due_pm_tasks`, which reads no
        database and no clock, because that is the arithmetic somebody has to be
        able to check (invariant 10).

        **A task that cannot be priced is skipped, not raised.** The whole scan
        is one transaction: letting `NoEstimateAvailable` out would roll back the
        tickets the scan had already written, and one machine model missing from
        `fallback_minutes` would stop the PM schedule for the whole plant, for
        ever. It is the argument `TriggerLoop._issue` makes at the other origin,
        and the failure it prevents is the same one.
        """
        now = self.clock.now()
        due = domain.due_pm_tasks(
            repo.pm_tasks(conn), live_refs=repo.pm_refs_with_live_order(conn), now=now
        )
        issued: list[str] = []
        unpriced: list[PMTaskRef] = []
        for task in due:
            try:
                order = self.from_pm_task(conn, task, machine_model=machine_model(task.machine_id))
            except domain.NoEstimateAvailable:
                unpriced.append(task.pm_task_ref)
                continue
            issued.append(order.ref)
        return PmScan(due=len(due), issued=tuple(issued), unpriced=tuple(unpriced))

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
        distinct_from: Sequence[str] = (),
        reporter_name: str | None = None,
    ) -> Issued:
        """Somebody saw something.

        `symptom_code` is optional because the person reporting may not know
        which one it is - and a report with no code still has to become a ticket,
        or the system quietly requires a diagnosis before it will accept a
        problem.

        Refused while the machine has fault work open, unless the reporter names those
        tickets in `distinct_from` - which is how they say "I have seen them and
        this is something else". The check reads the queue on the caller's
        connection, so a second report arriving in the same moment either sees
        the first row or is written after it, and never both (ADR-077 section 3).

        The refusal is deliberately about the machine rather than the symptom:
        `symptom_code` is not stored on an order at all, because the scheduler
        does not need it (ADR-041), so there is nothing finer to key on yet.
        """
        # Faults only. A PM due on the machine is not the fault somebody is
        # standing in front of, and listing it beside one sent the operator to
        # decide whether a lubrication round was what they saw (fourth trial,
        # finding 20).
        already_open = [
            (ref, order)
            for ref, order in repo.open_for_machine(conn, machine_id)
            if order.origin is not WorkOrderOrigin.SCHEDULED
        ]
        unaccounted = [ref for ref, _ in already_open if ref not in set(distinct_from)]
        if unaccounted:
            raise AlreadyOpen(
                machine_id,
                [ref for ref, _ in already_open],
                [order.reason for _, order in already_open],
                [
                    domain.title(order, repo.symptom_of(conn, order), self.wording)
                    for _, order in already_open
                ],
            )

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
            reporter_name=reporter_name,
            description=description,
            playbook=playbook,
            playbook_warning=warning,
            machine_model=machine_model,
            fallback_minutes=self.fallback_minutes,
            now=now,
            wording=self.wording,
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
            raise NoSuchOrder(f"ไม่พบใบงาน {ref}")
        if order.status not in domain.STILL_LIVE:
            raise TransitionRefused(f"{ref} ปิดไปแล้ว แก้ไม่ได้อีก ถ้าเครื่องนี้มีปัญหาใหม่ ให้แจ้งซ่อมเป็นใบใหม่")
        if order.status is WorkOrderStatus.PROPOSED:
            # Refused here rather than by the order being invisible (ADR-071 §7).
            # It should not be reachable - `GET /work-orders/mine` does not serve
            # proposals - and a technician who got to it through a link they kept
            # is owed the reason rather than a job that does nothing when pressed.
            raise TransitionRefused(f"{ref} ยังรอหัวหน้ากะยืนยัน ยังไม่ได้เป็นงานของคุณ")
        return order

    def _reread(self, conn: Connection[Any], ref: str) -> WorkOrder:
        order = repo.get(conn, ref)
        if order is None:  # pragma: no cover - the row is locked by this transaction
            raise NoSuchOrder(f"ไม่พบใบงาน {ref}")
        return order

    def adopt(
        self, conn: Connection[Any], playbook: Playbook, *, machine_ids: Sequence[str]
    ) -> list[str]:
        """The orders waiting on this symptom now carry its approved steps (ADR-102)."""
        return repo.adopt_playbook(conn, playbook, machine_ids=machine_ids)

    def accept(self, conn: Connection[Any], ref: str, *, user: UserId) -> WorkOrder:
        """A technician takes the job (ADR-024: technicians, and only them).

        Accepting one they already hold changes nothing rather than failing. The
        button is pressed on a phone at a machine on a network that drops, and a
        second press is not a mistake worth refusing.
        """
        order = self._live(conn, ref)
        if domain.holds_it(order, user):
            return order
        # Only work a round placed and a person released can be taken (ADR-101).
        # Queued work includes what the load gate is holding back and what the
        # shift lead has not confirmed; taking it here went round both.
        if order.status not in _TAKEABLE:
            raise TransitionRefused(f"{ref} ยังไม่ได้ถูกจัดให้ช่าง งานนี้ต้องให้หัวหน้ากะยืนยันก่อน")
        if len(order.assignees) >= order.required_technicians:
            held_by = ", ".join(str(one.user) for one in order.assignees)
            raise TransitionRefused(
                f"{ref} ใช้ช่าง {order.required_technicians} คน และมีคนรับไปแล้ว: {held_by}"
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
            raise TransitionRefused(f"คุณยังไม่ได้รับงาน {ref} กด “รับงานและเริ่มทำ” ก่อน")
        if domain.has_an_open_segment(order, user):
            raise TransitionRefused(f"คุณกำลังทำ {ref} อยู่แล้ว ไม่ต้องกดเริ่มซ้ำ")
        repo.open_segment(conn, ref, user=user, now=self.clock.now())
        repo.set_status(conn, ref, status=WorkOrderStatus.IN_PROGRESS)
        return self._reread(conn, ref)

    def reach_step(self, conn: Connection[Any], ref: str, *, user: UserId, step: int) -> int:
        """Mark the step this person has moved on to (ADR-134).

        Only by somebody on the job, and only to a step the snapshot has: the
        mark is what the job page resumes from, so a number outside the steps
        it instructed would resume nowhere.
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"คุณยังไม่ได้รับงาน {ref} กด “รับงานและเริ่มทำ” ก่อน")
        if not 1 <= step <= len(order.playbook_snapshot):
            raise ValueError(f"ใบงาน {ref} มี {len(order.playbook_snapshot)} ขั้น ไม่มีขั้นที่ {step}")
        now = self.clock.now()
        # An isolation, verify or restore step is left only when every point is
        # confirmed, and a waiting hazard only when its time is up (ADR-135,
        # REQ-H-04). Checked here, not only by a disabled button.
        blocked = locks.first_unfinished(
            order.playbook_snapshot, locks.confirmations(conn, ref), before=step, now=now
        )
        if blocked is not None:
            number, _ = blocked
            raise TransitionRefused(f"ขั้นที่ {number} ยังยืนยันไม่ครบ ไปขั้นถัดไปไม่ได้")
        repo.record_step(conn, ref, step=step, user=user, now=now)
        # A wait starts when the step is reached, so leaving the page does not stop the clock.
        if order.playbook_snapshot[step - 1].wait_minutes is not None:
            locks.confirm(
                conn, ref, step=step, point_id="", item=locks.WAIT_STARTED, user=user, now=now
            )
        return step

    def confirm(
        self,
        conn: Connection[Any],
        ref: str,
        *,
        user: UserId,
        step: int,
        point_id: str,
        item: str,
        lock_no: str | None = None,
    ) -> list[locks.Confirmation]:
        """One point of an isolation, verify or restore step, confirmed by the person doing it.

        In order: a point is locked after it is off, and a step's points are
        worked one after another (OSHA 1910.147, REQ-H-04). A lock goes into the
        register as it is confirmed, and comes out only by its owner on a
        restore step (ADR-135).
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"คุณยังไม่ได้รับงาน {ref} กด “รับงานและเริ่มทำ” ก่อน")
        if not 1 <= step <= len(order.playbook_snapshot):
            raise ValueError(f"ใบงาน {ref} ไม่มีขั้นที่ {step}")
        marked = order.playbook_snapshot[step - 1]
        if marked.kind is StepKind.HAZARD and item == locks.WAIT_STARTED and point_id == "":
            locks.confirm(
                conn, ref, step=step, point_id="", item=item, user=user, now=self.clock.now()
            )
            return locks.confirmations(conn, ref)
        if item not in locks.ITEMS.get(marked.kind, ()):
            raise ValueError(f"ขั้นที่ {step} ไม่มีการยืนยัน “{item}”")
        if point_id not in {point.point_id for point in marked.isolation_points}:
            raise ValueError(f"ขั้นที่ {step} ไม่มีจุด {point_id}")

        now = self.clock.now()
        done = locks.confirmations(conn, ref)
        needed = locks.still_needed(marked, step, done, now=now)
        if (point_id, item) not in needed:
            return done  # already confirmed: a second tap is not a second statement
        if needed[0] != (point_id, item):
            first_point, first_item = needed[0]
            raise TransitionRefused(f"ยืนยันตามลำดับ: {first_point} ก่อน ({_SAID[first_item]})")

        if item == "locked":
            if not lock_no or not lock_no.strip():
                raise ValueError("เลือกเลขกุญแจที่ใส่")
            if not locks.apply_lock(
                conn,
                work_order_ref=ref,
                machine_id=order.machine_id,
                point_id=point_id,
                lock_no=lock_no,
                owner=user,
                step=step,
                now=now,
            ):
                raise TransitionRefused(f"กุญแจ {lock_no.strip()} ล็อกอยู่ที่จุดอื่นแล้ว")
        if item == "released" and not locks.release_lock(
            conn, work_order_ref=ref, point_id=point_id, owner=user, now=now
        ):
            raise TransitionRefused(f"ไม่มีกุญแจของคุณที่ {point_id} ปลดได้เฉพาะเจ้าของกุญแจ")
        locks.confirm(conn, ref, step=step, point_id=point_id, item=item, user=user, now=now)
        return locks.confirmations(conn, ref)

    def _lock_answer(
        self,
        conn: Connection[Any],
        ref: str,
        user: UserId,
        answer: LockState | None,
        reason: str | None,
        note: str | None,
    ) -> str | None:
        """Check the answer about locks against the register; return the note with it on top."""
        on_job = locks.open_locks(conn, work_order_ref=ref)
        mine = [one for one in on_job if one.owner == user]
        refused = locks.lock_state_refused(answer, mine=mine, on_this_job=on_job)
        if refused is not None:
            raise TransitionRefused(refused)
        line = locks.lock_line(answer, reason, on_job)
        text = (note or "").strip()
        if line is None:
            return text or None
        return f"{line}\n{text}" if text else line

    def hand_over(
        self,
        conn: Connection[Any],
        ref: str,
        *,
        user: UserId,
        note: str,
        lock_state: LockState | None = None,
        lock_reason: str | None = None,
    ) -> WorkOrder:
        """Put the job down for somebody else, and say how far it got.

        The note is checked before anything is written. ADR-025 asks for it
        because without it the next shift finds an open order and starts from
        step one, and a handover recorded without one would be worse than none -
        it would look complete.

        The handover ends this person's assignment (ADR-056). When nobody is
        left on the order it goes back to the queue with the note on it, and the
        next round offers it to the shift lead like any other job (ADR-120). It
        used to become `handed_over`, a status no round placed and no
        technician's screen listed, so it waited for somebody who could not see
        it. A helper stepping off a job the primary is still working has not
        handed anything over, and the status stays where it is.
        """
        order = self._live(conn, ref)
        if not domain.holds_it(order, user):
            raise TransitionRefused(f"คุณยังไม่ได้รับงาน {ref} กด “รับงานและเริ่มทำ” ก่อน")
        if not note.strip():
            raise ValueError("ส่งต่องานต้องเขียนว่าทำถึงไหนแล้ว ไม่อย่างนั้นคนถัดไปต้องเริ่มใหม่ตั้งแต่ขั้นแรก")
        # A lock left on goes over with the job and stays its owner's (ADR-135).
        note = self._lock_answer(conn, ref, user, lock_state, lock_reason, note) or note

        repo.close_segments(conn, ref, user=user, now=self.clock.now())
        repo.remove_assignee(conn, ref, user)
        remaining = self._reread(conn, ref)
        repo.set_status(
            conn,
            ref,
            status=(WorkOrderStatus.QUEUED if not remaining.assignees else remaining.status),
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
        lock_state: LockState | None = None,
        lock_reason: str | None = None,
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
            raise TransitionRefused(f"คุณยังไม่ได้รับงาน {ref} กด “รับงานและเริ่มทำ” ก่อน")

        now = self.clock.now()
        worked = domain.minutes_worked_if_closed_at(order, now)
        if blocked_minutes > worked:
            # Refused rather than clamped. `repair_minutes` already floors at
            # zero, which keeps the arithmetic safe and hides the input that was
            # wrong - and these are the numbers Loop 1 learns estimates from.
            raise ValueError(
                f"เวลารอ {blocked_minutes} นาที มากกว่าเวลาที่ทำงานนี้ทั้งหมด {worked} นาที "
                f"เวลารอต้องไม่เกินเวลาทำงาน"
            )
        if blocked_minutes > 0 and not blocked_reason:
            raise ValueError("ถ้ามีเวลารอ ต้องเลือกเหตุผลด้วย: รออะไหล่ รอสายหยุด หรือรอคนช่วย")
        # Agreed with the register, and carried at the top of the note (REQ-H-06, ADR-135).
        technician_feedback = self._lock_answer(
            conn, ref, user, lock_state, lock_reason, technician_feedback
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
        # A PM order closing is the only event that moves a task's clock, and it
        # moves it here, in the transaction that closed the order. Recorded
        # anywhere else, a crash between the two would leave a task the plant has
        # maintained still reading as overdue, or one it has not reading as done
        # (ADR-083 section 5). `pm_task_was_done` is why the outcome decides:
        # `not_fixed` is a job that did not happen.
        if order.pm_task_ref is not None and domain.pm_task_was_done(outcome):
            repo.record_pm_done(conn, order.pm_task_ref, at=now)
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

    def finished_finding_refs(
        self, conn: Connection[Any], refs: Collection[FindingRef]
    ) -> set[FindingRef]:
        """Findings whose tickets have all been closed or cancelled (ADR-119)."""
        return repo.finished_finding_refs(conn, refs)

    def follow_forecast(
        self,
        conn: Connection[Any],
        finding_ref: FindingRef,
        *,
        eta: datetime,
        eta_confidence: timedelta,
    ) -> list[str]:
        """Move the open orders of a re-fitted forecast to its new ETA (ADR-115)."""
        return repo.follow_forecast(conn, finding_ref, eta=eta, eta_confidence=eta_confidence)

    def withdraw_for_finding(self, conn: Connection[Any], finding_ref: FindingRef) -> list[str]:
        """Cancel the untouched orders for a Finding the world has overtaken.

        Returns what was cancelled, which is not the same as what was found: an
        order somebody has accepted is left where it is (ADR-044 §7).
        """
        return repo.cancel_untouched_for_finding(conn, finding_ref, now=self.clock.now())


# How a confirmation is said back, for the refusal that names the one to do first.
_SAID = {
    "off": "ตัดพลังงาน",
    "locked": "ใส่กุญแจ",
    "verified": "ตรวจว่าพลังงานเป็นศูนย์",
    "released": "ปลดกุญแจ",
    locks.WAIT_STARTED: "รอให้ครบเวลา",
}

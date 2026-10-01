"""Turning a source of work into a work order. Pure, no I/O (ADR-030 layering).

Three sources, one function each, and a shared core: bind the playbook, price the
job, and say why it exists. What differs between them is which reference is set
and what the sentence reads like - which is the whole of ADR-010 in code.

**The pricing is the part with consequences.** `estimated_minutes` and
`required_technicians` are what the load gate multiplies together (design.md
13.2), so an order priced wrongly does not fail: it makes a shift look busier or
emptier than it is, and the gate then holds back or releases the wrong work with
no error anywhere.
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from datetime import datetime, timedelta

from pdm.contracts import (
    AssigneeRole,
    Finding,
    FindingKind,
    FindingRef,
    MachineId,
    Playbook,
    PlaybookRef,
    PMTask,
    PMTaskRef,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
)
from pdm.contracts.wording import Wording, span

# PM work is the low-priority work a quiet shift is meant to absorb (ADR-010,
# ADR-011). `PMTask` carries no severity of its own, so this is where the
# system's assumption about it is written down rather than left in a caller.
PM_SEVERITY = Severity.LOW


class NoEstimateAvailable(Exception):
    """No playbook, and `policy.yaml` has no fallback for this model and severity.

    Raised rather than defaulted. An order with an invented duration enters
    `load_ratio` as though somebody had measured it, and the whole point of the
    fallback table is that its numbers are declared in one readable place.
    """


# A job somebody can still pick up, put down or finish. `closed` and `cancelled`
# are endings, and an ending is the one state from which nothing moves: a
# transition applied to a closed order would write over the record of a job that
# is already evidence (ADR-018).
STILL_LIVE = (
    WorkOrderStatus.QUEUED,
    # Decided by a round and not yet confirmed (ADR-071). Live, because the work
    # still has to happen - but none of the four buttons apply to it, which
    # `WorkOrders._live` says in its own sentence rather than by leaving it out
    # of this tuple and calling an unconfirmed job "closed".
    WorkOrderStatus.PROPOSED,
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
    WorkOrderStatus.HANDED_OVER,
)


def holds_it(order: WorkOrder, user: UserId) -> bool:
    """Whether this person is on the order now.

    `assignees` is the present tense; `work_segments` is the record of who
    worked. Handing over takes somebody out of the first and leaves them in the
    second (ADR-056).
    """
    return any(one.user == user for one in order.assignees)


def has_an_open_segment(order: WorkOrder, user: UserId) -> bool:
    return any(one.user == user and one.ended_at is None for one in order.work_segments)


def role_for_new_assignee(order: WorkOrder) -> AssigneeRole:
    """First on is the primary, everybody after is a helper (ADR-056 §4).

    By count rather than by skill: layer 3 already matched the skill against the
    primary when it placed the order, and re-deriving it here would mean two
    answers to one question, disagreeing on the shift where it matters.
    """
    return AssigneeRole.PRIMARY if not order.assignees else AssigneeRole.HELPER


def minutes_worked_if_closed_at(order: WorkOrder, now: datetime) -> int:
    """What `actual_minutes` will read once the open segments are closed.

    Computed before anything is written, because the checks that can refuse a
    close - blocked minutes larger than the job - have to refuse without leaving
    the order half ended. An `HTTPException` commits the request's transaction
    (api/deps.py), so "raise and let it roll back" is not available here.
    """
    total = timedelta(0)
    for segment in order.work_segments:
        ended = segment.ended_at if segment.ended_at is not None else now
        total += max(ended - segment.started_at, timedelta(0))
    return int(total.total_seconds() // 60)


def playbook_ref_for(symptom_code: SymptomCode, machine_model: str) -> PlaybookRef:
    """The key a playbook is looked up by, as one string.

    One row per (symptom_code, machine_model) is the whole of ADR-018, so the
    reference is those two values and nothing else - no surrogate id that could
    point at a row that has since been overwritten.
    """
    return PlaybookRef(f"{symptom_code}/{machine_model}")


def _priced(
    playbook: Playbook | None,
    *,
    machine_model: str,
    severity: Severity,
    fallback_minutes: dict[str, dict[Severity, int]],
) -> tuple[int, bool, PlaybookRef | None]:
    """(minutes, is_fallback, playbook_ref).

    The fallback is coarse on purpose and labelled as coarse (design.md 3.2).
    Without it, work with no playbook has no duration, cannot be queued, and
    disappears from the system with nothing reporting its absence - which is the
    long-tail work the advisor asked to be released on a quiet shift.
    """
    if playbook is not None:
        return (
            playbook.estimated_minutes,
            False,
            playbook_ref_for(playbook.symptom_code, playbook.machine_model),
        )

    by_severity = fallback_minutes.get(machine_model)
    if by_severity is None or severity not in by_severity:
        raise NoEstimateAvailable(
            f"no playbook for this job and policy.yaml has no fallback_minutes for "
            f"{machine_model}/{severity.value}; a duration invented here would enter "
            f"load_ratio as though somebody had measured it (design.md 3.2)"
        )
    return (by_severity[severity], True, None)


_PLAIN = Wording()


def reason_for(finding: Finding, wording: Wording = _PLAIN) -> str:
    """Why this job exists, in the words a technician needs, in Thai (ADR-093).

    The two kinds read differently because a person decides differently: a
    machine already over its limit is one to run to, and one expected to reach
    it in about six hours is one to plan for. **The interval is never dropped** -
    "in about 6 hours" reads as more trustworthy than "in about 6 hours, give or
    take 2", and the second one is the truth (ADR-020).

    Times are on the plant's clock. `reason` is written once and never
    corrected, so a UTC stamp here would stay wrong on the ticket for good.
    """
    where = f"{wording.symptom(finding.symptom_code)} ที่เครื่อง {finding.machine_id}"
    unknown = " · ยังไม่ทราบว่าเป็นที่ชิ้นส่วนไหน ต้องไล่หาสาเหตุก่อน" if finding.component == "unknown" else ""
    if finding.kind is FindingKind.DETECTED:
        return f"{where} · ตรวจพบเมื่อ {wording.day_and_clock(finding.detected_at)}{unknown}"

    # A predicted Finding always carries both (the contract refuses one without
    # the other), so this cannot render half an interval.
    assert finding.eta is not None and finding.eta_confidence is not None
    return (
        f"{where} · ยังไม่เกินเกณฑ์ แต่คาดว่าจะถึงเกณฑ์ราว "
        f"{wording.day_and_clock(finding.eta)} (คลาดเคลื่อนได้ ± {span(finding.eta_confidence)})"
        f"{unknown}"
    )


def from_finding(
    finding: Finding,
    finding_ref: FindingRef,
    *,
    playbook: Playbook | None,
    playbook_warning: str | None = None,
    machine_model: str,
    fallback_minutes: dict[str, dict[Severity, int]],
    wording: Wording = _PLAIN,
) -> WorkOrder:
    """A condition order: something crossed a threshold, or is about to.

    Everything layer 3 needs is copied here and nothing is left behind a
    reference. `finding_ref` stays for tracing back - the screen showing "seen N
    times" reads through it - and the scheduler never follows it (ADR-030).
    """
    minutes, is_fallback, playbook_ref = _priced(
        playbook,
        machine_model=machine_model,
        severity=finding.severity,
        fallback_minutes=fallback_minutes,
    )
    return WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=finding_ref,
        machine_id=finding.machine_id,
        severity=finding.severity,
        finding_kind=finding.kind,
        eta=finding.eta,
        eta_confidence=finding.eta_confidence,
        playbook_ref=playbook_ref,
        playbook_snapshot=playbook.steps if playbook else (),
        snapshot_approved_by=playbook.approved_by if playbook else None,
        snapshot_approved_at=playbook.approved_at if playbook else None,
        playbook_warning=playbook_warning,
        estimated_minutes=minutes,
        required_skill=playbook.required_skill if playbook else None,
        required_technicians=playbook.required_technicians if playbook else 1,
        estimate_is_fallback=is_fallback,
        reason=reason_for(finding, wording),
    )


def from_pm_task(
    task: PMTask,
    *,
    playbook: Playbook | None,
    playbook_warning: str | None = None,
    machine_model: str,
    fallback_minutes: dict[str, dict[Severity, int]],
    severity: Severity = PM_SEVERITY,
    wording: Wording = _PLAIN,
) -> WorkOrder:
    """A scheduled order: the work a quiet shift is meant to absorb.

    Reaches layer 2 through the ordinary lookup, because `PMTask.symptom_code`
    carries the `PM-` prefix and the playbook table is keyed the same way for
    every kind of work - so layer 2 never learns the word "PM" (design.md 13.3).
    """
    minutes, is_fallback, playbook_ref = _priced(
        playbook,
        machine_model=machine_model,
        severity=severity,
        fallback_minutes=fallback_minutes,
    )
    return WorkOrder(
        origin=WorkOrderOrigin.SCHEDULED,
        pm_task_ref=task.pm_task_ref,
        machine_id=task.machine_id,
        severity=severity,
        playbook_ref=playbook_ref,
        playbook_snapshot=playbook.steps if playbook else (),
        snapshot_approved_by=playbook.approved_by if playbook else None,
        snapshot_approved_at=playbook.approved_at if playbook else None,
        playbook_warning=playbook_warning,
        estimated_minutes=minutes,
        required_skill=playbook.required_skill if playbook else None,
        required_technicians=playbook.required_technicians if playbook else 1,
        estimate_is_fallback=is_fallback,
        reason=(
            f"บำรุงรักษาตามแผน: {wording.symptom(task.symptom_code)} ที่เครื่อง {task.machine_id}"
            f" · ครบกำหนด {wording.day(task.due_at)} · "
            + (
                f"ทำครั้งล่าสุด {wording.day(task.last_done_at)} "
                f"ทำทุก {_interval_in_hours(task.interval)}"
                if task.last_done_at is not None
                # The honest half of "due now". A task nobody has recorded as
                # done is due from the moment it was registered, which is a
                # fact about this system rather than about the machine, and the
                # person holding the ticket is the one who can say otherwise
                # (ADR-083 section 4).
                else "ยังไม่มีบันทึกว่าเคยทำ จึงถือว่าครบกำหนดตั้งแต่ลงทะเบียนเข้าระบบ "
                f"(ทำทุก {_interval_in_hours(task.interval)})"
            )
        ),
    )


def _interval_in_hours(interval: timedelta) -> str:
    """An interval as the manual states it. Manuals state hours, and a reason
    that said "333 days" would have to be converted back by whoever checks it
    against the page it came from."""
    hours = interval.total_seconds() / 3600
    return f"{hours:,.0f} ชั่วโมงทำงาน"


def due_pm_tasks(
    tasks: Sequence[PMTask], *, live_refs: Collection[PMTaskRef], now: datetime
) -> tuple[PMTask, ...]:
    """The tasks that are due and have no live order against them.

    Pure, and separate from the scan for invariant 10's reason: which tasks fall
    due is arithmetic somebody has to be able to check against dates written out
    by hand, and `now` is an argument because this module may not read a clock
    (ADR-028).

    **A task whose order is still live is skipped rather than stacked.** An
    order that is queued, proposed, assigned, in progress or handed over is work
    the shift has not finished; issuing a second one would put two tickets for
    one job in front of two technicians, and push `load_ratio` up by a job that
    does not exist (ADR-083 section 3). Skipping is not silent: the task stays
    overdue, and the health screen counts it every day it stays that way.
    """
    held = frozenset(live_refs)
    return tuple(task for task in tasks if task.pm_task_ref not in held and task.is_due(now))


def pm_task_was_done(outcome: WorkOutcome) -> bool:
    """Whether closing an order this way means the maintenance happened.

    Only `fixed`. A PM order closed `not_fixed` or `temporary_fix` is a job that
    did not get done - the part was missing, the line could not stop - and
    advancing the interval would hide that for the length of the interval.
    `no_problem_found` is the same answer for a different reason: on a PM task it
    says the technician found nothing to do, not that the procedure was carried
    out (ADR-083 section 5).

    The cost is stated rather than hidden: a task closed any of those three ways
    is still due, so the next scan issues it again. That is a ticket a person
    closed reappearing, which is the right direction - the work is still owed -
    and it is why the reason on the new ticket says when it was last actually
    done.
    """
    return outcome is WorkOutcome.FIXED


def from_report(
    *,
    machine_id: MachineId,
    severity: Severity,
    reported_by: UserId,
    description: str,
    playbook: Playbook | None,
    playbook_warning: str | None = None,
    machine_model: str,
    fallback_minutes: dict[str, dict[Severity, int]],
    now: datetime,
    alongside: Sequence[str] = (),
    wording: Wording = _PLAIN,
    reporter_name: str | None = None,
) -> WorkOrder:
    """A manual order: a person saw something.

    The description is the reason, in their words, with who and when around it.
    Rewriting it into the system's phrasing would lose the only account of the
    machine that came from somebody standing next to it.

    `alongside` names the tickets that were already open on this machine when the
    reporter said this was something else. It goes in the reason because that is
    the sentence read by whoever picks the job up, and the question they will
    have - "isn't somebody already on this machine?" - is one the ticket should
    answer before they ask it (ADR-077 section 3).
    """
    minutes, is_fallback, playbook_ref = _priced(
        playbook,
        machine_model=machine_model,
        severity=severity,
        fallback_minutes=fallback_minutes,
    )
    return WorkOrder(
        origin=WorkOrderOrigin.MANUAL,
        machine_id=machine_id,
        severity=severity,
        playbook_ref=playbook_ref,
        playbook_snapshot=playbook.steps if playbook else (),
        snapshot_approved_by=playbook.approved_by if playbook else None,
        snapshot_approved_at=playbook.approved_at if playbook else None,
        playbook_warning=playbook_warning,
        estimated_minutes=minutes,
        required_skill=playbook.required_skill if playbook else None,
        required_technicians=playbook.required_technicians if playbook else 1,
        estimate_is_fallback=is_fallback,
        reported_by=reported_by,
        reason=(
            f"แจ้งโดย {reporter_name or reported_by} เมื่อ {wording.day_and_clock(now)} "
            f"ที่เครื่อง {machine_id}: "
            f"{description}"
            + (f" (เครื่องนี้มีใบงานเปิดอยู่แล้ว: {', '.join(alongside)})" if alongside else "")
        ),
    )

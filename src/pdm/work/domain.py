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

from datetime import UTC, datetime, timedelta

from pdm.contracts import (
    AssigneeRole,
    Finding,
    FindingKind,
    FindingRef,
    MachineId,
    Playbook,
    PlaybookRef,
    PMTask,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)

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


def reason_for(finding: Finding) -> str:
    """Why this job exists, in the words a technician needs.

    Every timestamp is converted before it is formatted. A Finding's `eta` is
    source time and may arrive in the plant's own offset (ADR-028); formatted
    without converting, its local wall clock would be stamped "UTC" into a string
    the order can never correct, because `reason` is written once.

    The two kinds read differently because a person decides differently: "over
    threshold for twenty minutes" is a machine that is already wrong, and
    "expected to reach it in about six hours" is one that is not yet. **The
    interval is never dropped** - "in about 6 hours" reads as more trustworthy
    than "in about 6 hours, give or take 2", and the second one is the truth
    (ui.md 2.2, ADR-020).
    """
    where = f"{finding.machine_id} {finding.component}"
    if finding.kind is FindingKind.DETECTED:
        seen = f", seen {finding.occurrence_count} times" if finding.occurrence_count > 1 else ""
        return f"{where}: {finding.symptom_code} detected by {finding.rule_id}{seen}"

    # A predicted Finding always carries both (the contract refuses one without
    # the other), so this cannot render half an interval.
    assert finding.eta is not None and finding.eta_confidence is not None
    return (
        f"{where}: {finding.symptom_code} predicted by {finding.rule_id}, expected to reach "
        f"the threshold at {finding.eta.astimezone(UTC):%Y-%m-%d %H:%M} UTC, give or take "
        f"{_hours(finding.eta_confidence)}"
    )


def _hours(interval: timedelta) -> str:
    minutes = int(interval.total_seconds() // 60)
    if minutes < 90:
        return f"{minutes} minutes"
    return f"{minutes / 60:.1f} hours".replace(".0 ", " ")


def from_finding(
    finding: Finding,
    finding_ref: FindingRef,
    *,
    playbook: Playbook | None,
    playbook_warning: str | None = None,
    machine_model: str,
    fallback_minutes: dict[str, dict[Severity, int]],
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
        reason=reason_for(finding),
    )


def from_pm_task(
    task: PMTask,
    *,
    playbook: Playbook | None,
    playbook_warning: str | None = None,
    machine_model: str,
    fallback_minutes: dict[str, dict[Severity, int]],
    severity: Severity = PM_SEVERITY,
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
            f"{task.machine_id}: {task.symptom_code} scheduled maintenance, "
            f"due {task.due_at.astimezone(UTC):%Y-%m-%d %H:%M} UTC"
        ),
    )


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
) -> WorkOrder:
    """A manual order: a person saw something.

    The description is the reason, in their words, with who and when around it.
    Rewriting it into the system's phrasing would lose the only account of the
    machine that came from somebody standing next to it.
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
        reason=(
            f"{machine_id}: reported by {reported_by} at "
            f"{now.astimezone(UTC):%Y-%m-%d %H:%M} UTC - {description}"
        ),
    )

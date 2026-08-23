"""Loop 1: what the finished jobs say the estimate should have been (ADR-066).

`estimated_minutes` on the playbook is what the scheduler prices a shift with;
`repair_minutes` on a closed order is what the job actually took, with the
waiting removed. ADR-006 keeps the two apart precisely so the second can correct
the first, and this module is that correction - arithmetic a person can check,
with no machine learning anywhere in it.

**It proposes and it writes nothing.** ADR-022 gives the duration loop an
exception the others do not have, letting it adjust within a bound on its own;
ADR-066 declines that exception and keeps the bound as a cap on the proposal. A
number that moves by itself is a number nobody can explain in the week somebody
asks why the shift filled up.

Pure by construction: no connection reaches this file, so the whole of it can be
tested against durations written out by hand (invariant 10, ADR-030).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import (
    MachineModel,
    RuleId,
    SymptomCode,
    WorkOrder,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ClosedJob(BaseModel):
    """One closed order, reduced to what the loop may learn from.

    `rule_id` is carried for the false-alarm count and for nothing else: a job
    closed `no_problem_found` says nothing about how long a repair takes and
    everything about the rule that raised it (ADR-022).
    """

    model_config = _FROZEN

    work_order_ref: WorkOrderRef
    repair_minutes: int = Field(ge=0)
    outcome: WorkOutcome
    # None for scheduled and manual work, which no rule raised (ADR-010).
    rule_id: RuleId | None = None

    @classmethod
    def from_order(
        cls,
        work_order_ref: WorkOrderRef,
        order: WorkOrder,
        *,
        rule_id: RuleId | None = None,
    ) -> ClosedJob:
        """Built through `WorkOrder.repair_minutes`, never beside it.

        The subtraction of blocked time has one definition in this system
        (ADR-025). A second one here would be the version that decides what every
        future estimate is, and the two would drift the first time a kind of
        waiting is added.
        """
        if order.status is not WorkOrderStatus.CLOSED or order.outcome is None:
            raise ValueError(
                "only a closed order is evidence: an open one has segments still running, "
                "and its repair time is a duration that has not finished happening"
            )
        return cls(
            work_order_ref=work_order_ref,
            repair_minutes=order.repair_minutes,
            outcome=order.outcome,
            rule_id=rule_id,
        )


class EstimateProposal(BaseModel):
    """What the evidence says, what may be done about it, and how to check both.

    Everything a reviewer needs is on the record itself. A proposal that reports
    only its new value asks to be believed, and ADR-022 asks for the opposite:
    the count, the spread and the orders behind it, so the person approving can
    look at the three jobs that made the middle move.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel

    current_minutes: int = Field(gt=0)
    # What the loop asks for, after the cap. Never zero: a job that takes no time
    # is not a job, and an estimate of zero removes the work from `load_ratio`
    # while leaving the technician's afternoon full.
    proposed_minutes: int = Field(gt=0)
    # What the evidence said before the cap was applied. Kept beside the proposal
    # rather than folded into it, so a reviewer can see that the loop wanted to
    # move further than it was allowed to - which is the signal that the estimate
    # is wrong by more than one cycle can fix.
    median_minutes: int = Field(gt=0)
    capped: bool

    observations: int = Field(gt=0)
    shortest_minutes: int = Field(ge=0)
    longest_minutes: int = Field(ge=0)
    evidence: tuple[WorkOrderRef, ...]

    # Counted, not silently dropped. The first is the only false-alarm signal the
    # system will ever receive; the second is orders nobody recorded work
    # segments against, which is a gap in the close-out rather than a fast job.
    no_problem_found: int = Field(default=0, ge=0)
    without_repair_time: int = Field(default=0, ge=0)

    reason: str = Field(min_length=1)


def _round_half_up(value: float) -> int:
    """Python rounds halves to even; a median of 47.5 would round to 48 and one
    of 46.5 to 46. Minutes are read by people, and a rule that rounds one way
    half the time is a rule nobody can reproduce with a pencil."""
    return math.floor(value + 0.5)


def propose(
    jobs: Sequence[ClosedJob],
    *,
    symptom_code: SymptomCode,
    machine_model: MachineModel,
    current_minutes: int,
    min_observations: int,
    max_change_ratio: float,
) -> EstimateProposal | None:
    """What the closed jobs for one (symptom_code, machine_model) say, or nothing.

    Nothing, in three cases, and each of them is a decision rather than an
    omission (ADR-066):

    - fewer usable observations than the floor, because a middle taken from two
      jobs is one technician's morning;
    - no usable observations at all;
    - a proposal that lands on the value already in the playbook, which is a
      queue item asking somebody to approve no change.

    `min_observations` and `max_change_ratio` have no defaults here. Both come
    from `policy.yaml`, where the provenance of every constant is written down;
    a default in this signature would be a number that answers even when the file
    does not (ADR-066).
    """
    usable = [
        job
        for job in jobs
        if job.outcome is not WorkOutcome.NO_PROBLEM_FOUND and job.repair_minutes > 0
    ]
    no_problem_found = sum(1 for job in jobs if job.outcome is WorkOutcome.NO_PROBLEM_FOUND)
    without_repair_time = sum(
        1
        for job in jobs
        if job.outcome is not WorkOutcome.NO_PROBLEM_FOUND and job.repair_minutes == 0
    )

    if len(usable) < min_observations:
        return None

    minutes = sorted(job.repair_minutes for job in usable)
    middle = _round_half_up(median(minutes))

    lowest_allowed = current_minutes * (1 - max_change_ratio)
    highest_allowed = current_minutes * (1 + max_change_ratio)
    bounded = min(max(float(middle), lowest_allowed), highest_allowed)
    proposed = max(1, _round_half_up(bounded))
    capped = proposed != middle

    if proposed == current_minutes:
        return None

    direction = "longer" if proposed > current_minutes else "shorter"
    reason = (
        f"{len(usable)} closed jobs for {symptom_code} on {machine_model} took a median of "
        f"{middle} minutes of repair time, against an estimate of {current_minutes}. "
        f"Proposing {proposed} minutes, {direction}"
    )
    if capped:
        reason += (
            f" - the evidence says {middle}, and one cycle may move the estimate by at most "
            f"{round(max_change_ratio * 100)}% (ADR-022, ADR-066)"
        )
    reason += "."

    return EstimateProposal(
        symptom_code=symptom_code,
        machine_model=machine_model,
        current_minutes=current_minutes,
        proposed_minutes=proposed,
        median_minutes=middle,
        capped=capped,
        observations=len(usable),
        shortest_minutes=minutes[0],
        longest_minutes=minutes[-1],
        evidence=tuple(job.work_order_ref for job in usable),
        no_problem_found=no_problem_found,
        without_repair_time=without_repair_time,
        reason=reason,
    )


class FalseAlarmCount(BaseModel):
    """How often a rule sent somebody to a machine that turned out to be fine.

    Per rule and per symptom, never per person (ADR-022). The count is the input
    Loop 2 needs before any threshold can be discussed, and this is where it
    starts being collected - reported, not acted on: ADR-022 forbids any loop
    from proposing that a safety-linked threshold be loosened, whatever this
    number says.
    """

    model_config = _FROZEN

    # Both None for work no rule raised - a scheduled PM or a reported fault that
    # closed `no_problem_found`. Reported rather than dropped, because it is not
    # a false alarm of anything and counting it against a rule would be wrong.
    symptom_code: SymptomCode | None
    rule_id: RuleId | None
    orders: int = Field(gt=0)

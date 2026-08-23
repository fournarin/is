"""Loop 2: what the false alarms say a rule's threshold should have been (ADR-073).

`no_problem_found` is the only false-alarm signal this system will ever receive
(ADR-022), and ADR-066 started counting it. This module is what the count is for:
a rule that keeps sending somebody to a machine that turns out to be fine is a
rule whose threshold is too tight, and the closed orders are the only place that
has ever been written down.

**It proposes and it writes nothing**, and for one rule it may not even propose:
ADR-022 forbids any loop from asking that a safety-linked threshold be loosened,
whatever the count grows to. The prohibition is enforced here rather than trusted
to a reviewer, because it is the one refusal nobody should have to remember.

The number proposed is a **separating threshold**, not a percentage of the old
one: the tightest value that would still have fired on every order where a
technician found something, chosen to exclude as many false alarms as the
evidence allows. Its property is that it cannot silence a confirmed fault, and
the proposal lists by reference the orders it still fires on so that property can
be checked rather than believed (ADR-073 section 3).

What it cannot see is written on every proposal it makes. Nothing in this system
counts the fault a higher threshold would have missed, so this evidence can only
say "too tight" and never "too loose" - which is why the person approving is the
only part of this loop that knows what the loop does not (ADR-073 section 6).

Pure by construction: no connection reaches this file, so the whole of it is
tested against readings written out by hand (invariant 10, ADR-030).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import FindingKind, RuleId, WorkOrderRef, WorkOutcome

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Carried on every proposal rather than left in the ADR. It is read by somebody
# looking at a number, not by somebody reading records, and a caveat that lives
# only in a document is one that is absent at the moment it matters (ADR-073 §6).
ONE_SIDED_EVIDENCE = (
    "This rests only on orders the rule did fire on. Nothing in this system records "
    "the fault a higher threshold would have missed, so this evidence can say a "
    "threshold is too tight and can never say it is too loose (ADR-022, ADR-073). "
    "The reading kept is the one the rule fired on rather than the peak of the "
    "excursion, so a signal still climbing might have crossed the proposed threshold "
    "a minute later instead of not at all."
)


class NoProposalCause(StrEnum):
    """Why nothing is proposed. Each of these is a different thing to do next.

    Loop 1 returns nothing when it has nothing to say. This loop always answers,
    because its refusals are the interesting half: "the evidence says this
    threshold is fine" and "there is no evidence" are not the same sentence, and
    a screen that rendered both as an empty row would hide the difference
    (ADR-073 section 5, principle 5).
    """

    # ADR-022, and no count changes it.
    SAFETY_CRITICAL = "safety_critical"
    # Not enough closed work behind this rule yet.
    BELOW_FLOOR = "below_floor"
    # Nobody has been sent out for nothing. That is an answer, not an absence.
    NO_FALSE_ALARMS = "no_false_alarms"
    # Every order behind this rule found nothing. A threshold above all of them
    # silences the rule, which is a decision to stop watching a machine.
    NO_CONFIRMED_FAULT = "no_confirmed_fault"
    # The false alarms and the real faults overlap: no threshold tells them apart.
    NO_SEPARATING_THRESHOLD = "no_separating_threshold"
    # The evidence separates, and one cycle may not move far enough to reach it.
    CAP_EXCLUDES_NOTHING = "cap_excludes_nothing"


class RuleFiring(BaseModel):
    """One closed order behind one rule, and the reading the rule fired on.

    The unit of evidence is the order, never the Finding's `occurrence_count`.
    ADR-023's suppression key makes one Finding stand for an unbroken run of
    breaching samples, so weighting by occurrences would let a single flapping
    sensor supply a whole evidence set on its own while reading as though dozens
    of jobs supported it (ADR-073 section 2).
    """

    model_config = _FROZEN

    work_order_ref: WorkOrderRef
    outcome: WorkOutcome
    # `evidence.value` on the Finding: what the metric read when the rule fired
    # (ADR-042 section 5).
    value: float
    # Predicted Findings are excluded rather than dropped. A forecast that came to
    # nothing is evidence about the trend fit, not about the threshold - what it
    # carries is a slope, not a reading (ADR-043, ADR-073 section 2).
    finding_kind: FindingKind = FindingKind.DETECTED


class ThresholdProposal(BaseModel):
    """A threshold that would have fired less, and everything needed to check it.

    Both lists of references are here on purpose. `would_not_have_fired` is what
    the proposal buys and `still_fires_on` is what it does not cost, and a
    reviewer who can open both is a reviewer who does not have to take the
    arithmetic on trust (ADR-022).
    """

    model_config = _FROZEN

    rule_id: RuleId
    comparison: str = Field(pattern="^(above|below)$")

    current_threshold: float
    proposed_threshold: float
    # Where the evidence actually separated, before the cap. Kept beside the
    # proposal rather than folded into it, so a reviewer can see the loop wanted
    # to move further than one cycle allows - which is the signal that the
    # threshold is wrong by more than this loop can fix.
    separating_threshold: float
    capped: bool

    # Closed orders behind this rule, after predictions are set aside.
    observations: int = Field(gt=0)
    false_alarms: int = Field(gt=0)
    faults_found: int = Field(gt=0)
    excluded_predictions: int = Field(default=0, ge=0)

    would_not_have_fired: tuple[WorkOrderRef, ...]
    still_fires_on: tuple[WorkOrderRef, ...]

    reason: str = Field(min_length=1)
    # Never empty, never a default a caller can talk it out of.
    limitation: str = Field(min_length=1)


class NoProposal(BaseModel):
    """Why this rule gets no proposal, in a form a screen can group by."""

    model_config = _FROZEN

    rule_id: RuleId
    cause: NoProposalCause
    observations: int = Field(ge=0)
    false_alarms: int = Field(ge=0)
    faults_found: int = Field(ge=0)
    excluded_predictions: int = Field(default=0, ge=0)
    reason: str = Field(min_length=1)


def propose(
    firings: Sequence[RuleFiring],
    *,
    rule_id: RuleId,
    comparison: str,
    current_threshold: float,
    safety_critical: bool,
    min_observations: int,
    max_change_ratio: float,
) -> ThresholdProposal | NoProposal:
    """What the closed orders behind one rule say about its threshold.

    The rule's own facts are arguments rather than a `RuleConfig`: the arithmetic
    is then tested against rules written out by hand, and `work/` keeps its
    distance from the file layer 1 boots from (ADR-073 section 7).

    `min_observations` and `max_change_ratio` have no defaults, for ADR-066's
    reason: both come from `policy.yaml`, where the provenance of every constant
    is written down, and a default here would answer even when the file does not.
    They are **not** the estimate loop's two numbers, and ADR-073 section 4 says
    why a floor that is enough to reprice a job is not enough to loosen a
    threshold.
    """
    if comparison not in ("above", "below"):
        raise ValueError(f"a rule fires above or below its threshold, not {comparison!r}")
    above = comparison == "above"

    usable = [firing for firing in firings if firing.finding_kind is FindingKind.DETECTED]
    predictions = len(firings) - len(usable)
    alarms = [firing for firing in usable if firing.outcome is WorkOutcome.NO_PROBLEM_FOUND]
    faults = [firing for firing in usable if firing.outcome is not WorkOutcome.NO_PROBLEM_FOUND]

    def refused(cause: NoProposalCause, reason: str) -> NoProposal:
        return NoProposal(
            rule_id=rule_id,
            cause=cause,
            observations=len(usable),
            false_alarms=len(alarms),
            faults_found=len(faults),
            excluded_predictions=predictions,
            reason=reason,
        )

    if safety_critical:
        return refused(
            NoProposalCause.SAFETY_CRITICAL,
            f"{rule_id} is safety-linked. ADR-022 forbids any loop from proposing that its "
            f"threshold be loosened, however many false alarms it produces: the answer there "
            f"is a condition that makes it more precise, never one that makes it less "
            f"sensitive.",
        )

    if len(usable) < min_observations:
        return refused(
            NoProposalCause.BELOW_FLOOR,
            f"{len(usable)} closed orders behind {rule_id}, and {min_observations} is the "
            f"floor. A separating threshold rests on the two observations either side of it, "
            f"and this set is not yet large enough to say where they are (ADR-073).",
        )

    if not alarms:
        return refused(
            NoProposalCause.NO_FALSE_ALARMS,
            f"None of the {len(usable)} closed orders behind {rule_id} closed "
            f"no_problem_found. The evidence says this threshold is not firing on nothing - "
            f"which is an answer, and not the same as having no evidence.",
        )

    if not faults:
        return refused(
            NoProposalCause.NO_CONFIRMED_FAULT,
            f"All {len(usable)} closed orders behind {rule_id} closed no_problem_found, so "
            f"there is no reading this rule must keep firing on. A threshold past all of them "
            f"silences the rule, and a loop may not propose that a machine stop being "
            f"watched (ADR-073).",
        )

    # The boundary the proposal may not cross: the mildest reading behind an order
    # where somebody found something. Anything the proposal excludes has to sit on
    # the near side of it.
    mildest_fault = min(f.value for f in faults) if above else max(f.value for f in faults)
    separable = [
        alarm
        for alarm in alarms
        if (alarm.value < mildest_fault if above else alarm.value > mildest_fault)
    ]
    if not separable:
        return refused(
            NoProposalCause.NO_SEPARATING_THRESHOLD,
            f"Every one of the {len(alarms)} false alarms behind {rule_id} read further past "
            f"the threshold than the mildest confirmed fault ({mildest_fault}). No threshold "
            f"separates them, so this rule needs another condition rather than a looser one "
            f"(ADR-022).",
        )

    # A rule fires strictly above or strictly below and never at its threshold
    # (triggers.domain.breaches), so a threshold set exactly to a reading excludes
    # that reading.
    separating = (
        max(alarm.value for alarm in separable)
        if above
        else min(alarm.value for alarm in separable)
    )
    # On the magnitude, so a threshold that is negative or zero does not invert the
    # bound. A threshold of zero cannot move by a ratio at all, which is a boundary
    # rather than a case - the same kind ADR-066 wrote down for short estimates.
    room = abs(current_threshold) * max_change_ratio
    bounded = (
        min(separating, current_threshold + room)
        if above
        else max(separating, current_threshold - room)
    )
    capped = bounded != separating

    excluded = [
        alarm for alarm in alarms if (alarm.value <= bounded if above else alarm.value >= bounded)
    ]
    if not excluded:
        return refused(
            NoProposalCause.CAP_EXCLUDES_NOTHING,
            f"The evidence behind {rule_id} separates at {separating}, and one cycle may move "
            f"a threshold by at most {round(max_change_ratio * 100)}% of {current_threshold}. "
            f"The move that allows would still have fired on every false alarm, so there is "
            f"nothing to propose this cycle (ADR-073).",
        )

    reason = (
        f"{len(alarms)} of {len(usable)} closed orders behind {rule_id} found nothing wrong. "
        f"The rule fires {comparison} {current_threshold}; at {bounded} it would not have "
        f"fired on {len(excluded)} of them, and it still fires on all {len(faults)} orders "
        f"where a fault was found - the mildest of those read {mildest_fault}"
    )
    if capped:
        reason += (
            f". The evidence separates at {separating}, and one cycle may move a threshold by "
            f"at most {round(max_change_ratio * 100)}% of it (ADR-073)"
        )
    reason += "."

    return ThresholdProposal(
        rule_id=rule_id,
        comparison=comparison,
        current_threshold=current_threshold,
        proposed_threshold=bounded,
        separating_threshold=separating,
        capped=capped,
        observations=len(usable),
        false_alarms=len(alarms),
        faults_found=len(faults),
        excluded_predictions=predictions,
        would_not_have_fired=tuple(alarm.work_order_ref for alarm in excluded),
        still_fires_on=tuple(fault.work_order_ref for fault in faults),
        reason=reason,
        limitation=ONE_SIDED_EVIDENCE,
    )


class RuleFirings(BaseModel):
    """Everything closed behind one rule, as the reader hands it over.

    `without_a_reading` is counted rather than dropped, on ADR-066's argument
    about jobs that carried no duration: a Finding whose evidence recorded no
    numeric value is a gap in what layer 1 wrote down, and it should be visible
    as one rather than quietly shrinking the evidence set.
    """

    model_config = _FROZEN

    rule_id: RuleId
    firings: tuple[RuleFiring, ...]
    without_a_reading: int = Field(default=0, ge=0)

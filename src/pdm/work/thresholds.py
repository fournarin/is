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
    title: str | None = None,
    predictions_without_a_reading: int = 0,
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

    `title` is what the rule watches for in the plant's words, and the sentences
    a person reads name the rule by it (ADR-093); the id is the fallback.
    `predictions_without_a_reading` counts forecast jobs that carried a slope
    rather than a reading: they are set aside like every prediction, and said so,
    because a forecast job closed behind a rule that then reads "0 closed jobs"
    is what the fourth trial's engineer could not reconcile with `/notes`.
    """
    if comparison not in ("above", "below"):
        raise ValueError(f"a rule fires above or below its threshold, not {comparison!r}")
    above = comparison == "above"

    usable = [firing for firing in firings if firing.finding_kind is FindingKind.DETECTED]
    predictions = len(firings) - len(usable) + predictions_without_a_reading
    name = title or rule_id
    # Predictions are set aside (ADR-043, ADR-073 section 2), and a count that
    # leaves them out has to say so, or it reads as work that never happened.
    set_aside = (
        f" (ไม่นับใบงานจากการพยากรณ์ล่วงหน้า {predictions} ใบ ข้อเสนอเรื่องเกณฑ์นับเฉพาะใบงาน"
        f"ที่ตรวจพบจากค่าที่อ่านได้จริง เพราะการพยากรณ์บอกแนวโน้ม ไม่ได้บอกค่าที่อ่านได้)"
        if predictions
        else ""
    )
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
            reason=reason + set_aside,
        )

    if safety_critical:
        return refused(
            NoProposalCause.SAFETY_CRITICAL,
            # ADR-022. What a person reads is Thai and cites no record (ADR-093).
            f"“{name}” เกี่ยวกับความปลอดภัย ระบบไม่เสนอให้ผ่อนเกณฑ์ของกฎนี้ ไม่ว่าจะแจ้งเตือน"
            f"ผิดกี่ครั้ง ถ้าแจ้งเตือนผิดบ่อย ให้เพิ่มเงื่อนไขให้แม่นขึ้น ไม่ใช่ลดความไว",
        )

    if len(usable) < min_observations:
        return refused(
            NoProposalCause.BELOW_FLOOR,
            # ADR-073.
            f"ใบงานที่ปิดแล้วของ “{name}” ที่ตรวจพบจากค่าที่อ่านได้จริงมี {len(usable)} ใบ ต้องมีอย่างน้อย "
            f"{min_observations} ใบจึงจะบอกได้ว่าเกณฑ์ควรอยู่ตรงไหน",
        )

    if not alarms:
        return refused(
            NoProposalCause.NO_FALSE_ALARMS,
            f"ใบงานที่ปิดแล้วของ “{name}” ทั้ง {len(usable)} ใบ ไม่มีใบไหนปิดว่า "
            f"“ไม่พบปัญหา” แปลว่าเกณฑ์นี้ไม่ได้แจ้งเตือนผิด ซึ่งเป็นคำตอบ ไม่ใช่การไม่มีข้อมูล",
        )

    if not faults:
        return refused(
            NoProposalCause.NO_CONFIRMED_FAULT,
            # ADR-073.
            f"ใบงานที่ปิดแล้วของ “{name}” ทั้ง {len(usable)} ใบ ปิดว่า “ไม่พบปัญหา” ทั้งหมด "
            f"ยังไม่มีครั้งไหนที่พบความเสียจริง เกณฑ์ที่เลยทุกค่านี้ไปจะทำให้กฎนี้เงียบ "
            f"ระบบไม่เสนอให้เลิกเฝ้าเครื่อง",
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
            # ADR-022.
            f"การแจ้งเตือนผิดทั้ง {len(alarms)} ครั้งของ “{name}” อ่านค่าเกินเกณฑ์มากกว่า"
            f"ความเสียจริงที่เบาที่สุด ({mildest_fault}) จึงไม่มีเกณฑ์ใดแยกสองกลุ่มนี้ได้ "
            f"กฎนี้ต้องเพิ่มเงื่อนไข ไม่ใช่ผ่อนเกณฑ์",
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
            # ADR-073.
            f"ข้อมูลของ “{name}” แยกกันที่ {separating} แต่แต่ละรอบขยับเกณฑ์ได้ไม่เกิน "
            f"{round(max_change_ratio * 100)}% ของ {current_threshold} ซึ่งยังแจ้งเตือนผิด"
            f"ทุกครั้งอยู่ดี รอบนี้จึงไม่มีอะไรเสนอ",
        )

    fires = "เกิน" if above else "ต่ำกว่า"
    reason = (
        f"ใบงานที่ปิดแล้วของ “{name}” {len(usable)} ใบ มี {len(alarms)} ใบที่ไม่พบปัญหา "
        f"กฎนี้แจ้งเตือนเมื่อค่า{fires} {current_threshold} ถ้าเปลี่ยนเป็น {bounded} จะไม่แจ้ง"
        f"เตือนผิด {len(excluded)} ครั้งในนั้น และยังแจ้งเตือนครบทั้ง {len(faults)} ใบที่พบ"
        f"ความเสียจริง ซึ่งค่าที่เบาที่สุดคือ {mildest_fault}"
    )
    if capped:
        # ADR-073.
        reason += (
            f" ข้อมูลแยกกันที่ {separating} แต่แต่ละรอบขยับเกณฑ์ได้ไม่เกิน {round(max_change_ratio * 100)}%"
        )
    reason += set_aside

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
    # Forecast jobs whose Finding carried a slope rather than a reading - every
    # trend Finding (`triggers.trend.evidence_for`). Not a gap in what layer 1
    # wrote: a prediction is set aside whatever it carries (ADR-073 section 2).
    predictions_without_a_reading: int = Field(default=0, ge=0)


def together(rule_id: RuleId, groups: Sequence[RuleFirings | None]) -> RuleFirings:
    """One rule's evidence gathered from every id its Findings were filed under.

    A forecast is filed under `<rule_id>/trend` (ADR-043 section 4), so the
    reader hands its closed jobs over as a group of their own. Left there, the
    rule's row counted none of them and said "0 closed jobs" beside a job
    `/notes` showed closed (fourth trial).
    """
    present = [group for group in groups if group is not None]
    return RuleFirings(
        rule_id=rule_id,
        firings=tuple(firing for group in present for firing in group.firings),
        without_a_reading=sum(group.without_a_reading for group in present),
        predictions_without_a_reading=sum(group.predictions_without_a_reading for group in present),
    )

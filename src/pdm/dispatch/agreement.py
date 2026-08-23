"""What the confirmation record says, and what it may not be read to say (ADR-075).

ADR-071 §8 wrote `dispatch_proposal` down as the answer to "ต้องดู performance
ไปก่อน" - the advisor's condition for ever turning confirmation off - and then
deliberately stopped, because a threshold deciding when a plant may stop
reviewing its own work orders is not a number this project may invent. This
module is the other half: the figures somebody would argue from, and nothing
resembling the argument.

Four readings, and the second is the one this file exists to protect:

  * **how often the shift lead agreed with the scheduler**, over the proposals a
    person actually answered;
  * **how much was never answered at all**, listed in full rather than counted,
    because a confirmation step nobody reaches is a queue with a person-shaped
    hole in it and is as strong an argument for `automatic` as agreement is;
  * **how long a decision took**, over confirmations and rejections only - an
    expiry's `decided_at` is the sweep noticing, not a person deciding;
  * **the same four figures per shift and per band**, because "the shift lead
    disagrees on heavy shifts" and "the shift lead disagrees" are different
    findings and only one of them can be acted on.

Pure by construction: no connection reaches this file, the reading is a function
of the rows handed to it, and every case is tested against proposals written out
by hand (invariant 10, ADR-030). The SQL that fetches them is in `repo.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from statistics import mean, median

from pydantic import BaseModel, ConfigDict, Field

from pdm.contracts import Role, ShiftId, UserId
from pdm.dispatch.domain import Band
from pdm.dispatch.proposals import Proposal, ProposalState

_FROZEN = ConfigDict(frozen=True, extra="forbid")

# Carried on every report rather than left in the ADR, for ADR-073 §6's reason:
# a caveat that lives only in a document is absent at the moment somebody is
# looking at a number, and this number is the one that would be quoted to argue
# for taking a person out of the path of every ticket.
WHAT_THE_RECORD_CANNOT_SAY = (
    "These figures say how often a shift lead agreed with the scheduler, not whether "
    "either was right: nothing here records what a confirmed placement went on to cost, "
    "and a supervisor who confirms everything to clear a screen is indistinguishable from "
    "one who read each proposal. They are also silent about the mode they would be used to "
    "argue for - in `automatic` no proposal is written, so this record cannot say what "
    "would have happened without the step it measures (ADR-071 section 8, ADR-075)."
)


class Counts(BaseModel):
    """How a set of proposals ended, with each ending kept as itself.

    `answered` and `settled` are two different denominators and both are here
    rather than left to a caller, because picking the wrong one is the whole way
    this report can mislead. Agreement is over what a person answered - an expiry
    is nobody's opinion about the placement. The expiry share is over everything
    that reached an ending, because that is the set somebody could have reached
    in time and did not.
    """

    model_config = _FROZEN

    proposed: int = Field(ge=0)
    pending: int = Field(ge=0)
    confirmed: int = Field(ge=0)
    rejected: int = Field(ge=0)
    expired: int = Field(ge=0)

    answered: int = Field(ge=0)
    settled: int = Field(ge=0)

    # Absent rather than zero when there is nothing to divide by. "Nobody
    # confirmed anything" and "nothing has been answered yet" are opposite
    # findings, and one of them is not evidence at all (principle 5).
    confirmed_share: float | None = None
    expired_share: float | None = None


class DecisionTime(BaseModel):
    """How long a person took, over the proposals a person answered.

    Expiries are left out on purpose. Their `decided_at` is always the window
    closing, so including them would pull every figure towards
    `proposal_expires_minutes` and report the setting back as a measurement.
    """

    model_config = _FROZEN

    answered: int = Field(ge=0)
    median_minutes: float | None = None
    mean_minutes: float | None = None
    longest_minutes: float | None = None


class Segment(BaseModel):
    """One shift, or one band, and the same reading over it.

    `key` is empty where the proposal recorded none - a round with no capacity to
    compute a ratio from records no band (ADR-045 §3). Those rows are reported
    under an empty key rather than dropped, so the segments always add up to the
    total; segments that quietly disagreed with the overall figure would leave a
    reader unable to tell which of the two was wrong.
    """

    model_config = _FROZEN

    key: str | None = None
    counts: Counts
    decision_time: DecisionTime


class Rejection(BaseModel):
    """A shift lead saying no, with everything needed to read it back later.

    The reason is carried in full and never summarised. A count answers how often
    the scheduler was overruled; the words answer what about, and only the second
    can be acted on. The band and shift come with it because "not now" means one
    thing on a heavy shift and another on a quiet one (ADR-059).
    """

    model_config = _FROZEN

    work_order_ref: str
    proposed_at: datetime
    # Optional for the same reason `minutes_to_decide` is: migration 0012 refuses
    # a settled row that cannot say when, so both are absent only on a proposal
    # assembled in memory - and an absence reads as one rather than as a decision
    # taken in no time at all (principle 5).
    decided_at: datetime | None = None
    minutes_to_decide: float | None = None
    decided_by: UserId | None = None
    decided_role: Role | None = None
    reason: str | None = None

    band: Band | None = None
    load_ratio: float | None = None
    shift_id: ShiftId | None = None
    priority_score: float
    priority_reason: str


class Expiry(BaseModel):
    """A proposal nobody answered, listed as loudly as a rejection.

    ADR-071 §8 makes this the second finding rather than a footnote, so it gets
    the same treatment: every row, with the round it was decided against, rather
    than a number a reader has to take on trust.
    """

    model_config = _FROZEN

    work_order_ref: str
    proposed_at: datetime
    expired_at: datetime | None = None
    waited_minutes: float | None = None

    band: Band | None = None
    load_ratio: float | None = None
    shift_id: ShiftId | None = None
    priority_score: float
    priority_reason: str


class AgreementReport(BaseModel):
    """Everything the confirmation record can be read to say, and nothing else."""

    model_config = _FROZEN

    overall: Counts
    decision_time: DecisionTime
    by_shift: tuple[Segment, ...] = ()
    by_band: tuple[Segment, ...] = ()
    rejections: tuple[Rejection, ...] = ()
    expiries: tuple[Expiry, ...] = ()
    # Never empty, never a default a caller can talk it out of (ADR-073 §6).
    limitation: str = Field(default=WHAT_THE_RECORD_CANNOT_SAY, min_length=1)


def agreement(proposals: Sequence[Proposal]) -> AgreementReport:
    """Read the confirmation record. It proposes nothing and writes nothing.

    Takes the rows rather than a connection so the arithmetic is testable against
    proposals written out by hand, and so the window a caller chose stays the
    caller's decision: this function has no opinion about how much history is
    enough, because ADR-071 §8 refuses to let this project invent one.
    """
    ordered = sorted(proposals, key=lambda one: (one.proposed_at, one.work_order_ref))
    return AgreementReport(
        overall=_counts(ordered),
        decision_time=_decision_time(ordered),
        by_shift=_segments(ordered, key=lambda one: str(one.shift_id) if one.shift_id else None),
        by_band=_segments(ordered, key=lambda one: one.band.value if one.band else None),
        rejections=tuple(_rejection(one) for one in ordered if one.state is ProposalState.REJECTED),
        expiries=tuple(_expiry(one) for one in ordered if one.state is ProposalState.EXPIRED),
    )


def _counts(proposals: Sequence[Proposal]) -> Counts:
    def how_many(state: ProposalState) -> int:
        return sum(1 for one in proposals if one.state is state)

    confirmed = how_many(ProposalState.CONFIRMED)
    rejected = how_many(ProposalState.REJECTED)
    expired = how_many(ProposalState.EXPIRED)
    answered = confirmed + rejected
    settled = answered + expired
    return Counts(
        proposed=len(proposals),
        pending=how_many(ProposalState.PENDING),
        confirmed=confirmed,
        rejected=rejected,
        expired=expired,
        answered=answered,
        settled=settled,
        confirmed_share=confirmed / answered if answered else None,
        expired_share=expired / settled if settled else None,
    )


def _decision_time(proposals: Sequence[Proposal]) -> DecisionTime:
    taken = [
        minutes
        for one in proposals
        if one.state in (ProposalState.CONFIRMED, ProposalState.REJECTED)
        and (minutes := _minutes_between(one)) is not None
    ]
    if not taken:
        return DecisionTime(answered=0)
    return DecisionTime(
        answered=len(taken),
        median_minutes=median(taken),
        mean_minutes=mean(taken),
        longest_minutes=max(taken),
    )


def _segments(
    proposals: Sequence[Proposal], *, key: Callable[[Proposal], str | None]
) -> tuple[Segment, ...]:
    """Group by one recorded fact, keys in order and the unrecorded one last.

    Sorted rather than left in encounter order so two runs over the same record
    produce the same document, and the row a reader is least likely to expect -
    the proposals that recorded no key at all - is where they will look last
    rather than in the middle.
    """
    grouped: dict[str | None, list[Proposal]] = {}
    for one in proposals:
        grouped.setdefault(key(one), []).append(one)
    named = sorted(name for name in grouped if name is not None)
    order: list[str | None] = [*named, *([None] if None in grouped else [])]
    return tuple(
        Segment(
            key=name, counts=_counts(grouped[name]), decision_time=_decision_time(grouped[name])
        )
        for name in order
    )


def _rejection(proposal: Proposal) -> Rejection:
    return Rejection(
        work_order_ref=proposal.work_order_ref,
        proposed_at=proposal.proposed_at,
        decided_at=proposal.decided_at,
        minutes_to_decide=_minutes_between(proposal),
        decided_by=proposal.decided_by,
        decided_role=proposal.decided_role,
        reason=proposal.reason,
        band=proposal.band,
        load_ratio=proposal.load_ratio,
        shift_id=proposal.shift_id,
        priority_score=proposal.priority_score,
        priority_reason=proposal.priority_reason,
    )


def _expiry(proposal: Proposal) -> Expiry:
    return Expiry(
        work_order_ref=proposal.work_order_ref,
        proposed_at=proposal.proposed_at,
        expired_at=proposal.decided_at,
        waited_minutes=_minutes_between(proposal),
        band=proposal.band,
        load_ratio=proposal.load_ratio,
        shift_id=proposal.shift_id,
        priority_score=proposal.priority_score,
        priority_reason=proposal.priority_reason,
    )


def _minutes_between(proposal: Proposal) -> float | None:
    """Minutes from the proposal to its ending, and nothing where nothing ended it.

    A settled row with no `decided_at` cannot reach the database - migration 0012
    refuses it - so the absent case is a row assembled in memory rather than one
    with a meaning. It is reported as absent rather than as zero, because a
    decision taken in no time at all is a figure somebody would read.
    """
    if proposal.decided_at is None:
        return None
    return (proposal.decided_at - proposal.proposed_at).total_seconds() / 60

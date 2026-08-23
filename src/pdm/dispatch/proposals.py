"""What a round leaves for a supervisor, and what their answer leaves behind (ADR-071).

A proposal is one round's decision about one order, held still until a person
agrees to it. It exists because the advisor asked for somebody to press the
button before a ticket reaches a technician, and asked for that requirement to
be removable later "once there is something to judge it by" - which is the whole
reason this is a record rather than a flag. What can be judged is here: what the
scheduler said, what the shift lead said, how far apart they were, and how much
was never answered at all.

The round it was decided against is copied on rather than looked up, for
ADR-050's reason and ADR-059's: a round is never stored, so the band, the ratio
and the shift exist only while somebody is looking at them. Same pattern as
`playbook_snapshot` - copy what is needed to where it is needed.

No I/O in this module. The SQL is in `repo.py` beside the rest of layer 3's.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.contracts import Assignee, Role, ShiftId, UserId
from pdm.dispatch.domain import Band

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class ProposalState(StrEnum):
    """How a proposal ended, or that it has not.

    Four values rather than a confirmed/not flag, because the three endings are
    read as different evidence. A rejection is an argument about the score. An
    expiry is an argument about the confirmation step itself - a queue with a
    person-shaped hole in it - and collapsing it into "not confirmed" would hide
    the strongest reason there is to turn the switch to `automatic`.
    """

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Proposal(BaseModel):
    """One order a round decided on, as it is written and as it is read back."""

    model_config = _FROZEN

    work_order_ref: str = Field(min_length=1)
    proposed_at: datetime
    # Who the round crewed it with. A proposal with nobody on it is not a
    # question anybody can answer, and `_assign` never produces one: an order
    # the gate admitted and nobody could take is reported as `unassigned`
    # instead, which is a different sentence for a different reader.
    assignees: tuple[Assignee, ...] = Field(min_length=1)
    priority_score: float
    priority_reason: str

    # The round it was decided against. `load_ratio` is empty where there was no
    # capacity to compute one from, which the band then names (ADR-045 section 3).
    band: Band | None = None
    load_ratio: float | None = None
    shift_id: ShiftId | None = None
    on_date: date | None = None

    state: ProposalState = ProposalState.PENDING
    decided_at: datetime | None = None
    # Empty on an expiry: nobody decided, the window did. Filling it with a
    # system name would put a decision in a person's column and make the table
    # unreadable as evidence about how often people agreed with the scheduler.
    decided_by: UserId | None = None
    decided_role: Role | None = None
    reason: str | None = None

    @property
    def answered(self) -> bool:
        return self.state is not ProposalState.PENDING


class Rejection(BaseModel):
    """A supervisor saying no, and why.

    Separate from `Objection` in the API because the two are not the same act:
    an objection is recorded and changes nothing (ADR-059), and this puts the
    order back in the queue for the next round to rank against what is true
    then. The reason is required in both, for the same reason.
    """

    model_config = _FROZEN

    reason: str = Field(min_length=1)

    @field_validator("reason")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", which is the same absence the record was
        written to refuse - it just gets past the schema."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("a rejection needs a reason (ADR-005, ADR-071)")
        return stripped

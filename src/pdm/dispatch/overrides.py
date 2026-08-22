"""What a person overruling layer 3 leaves behind (ADR-005, ADR-011).

Two overrides are in the design and they are not symmetrical:

  a **disagreement** is a technician saying the queue put the wrong job first.
  It records and changes nothing. Re-ranking on an objection would make the
  queue negotiable and defeat the load gate, so the value of the button is the
  record and not the effect;

  a **release** is a shift lead taking one ticket out of the gate's hands. It
  changes the next round, because that is what the supervisor pressed it for.

Both are written down the first day they are possible. The round they were taken
against is computed when asked and never stored (ADR-050), so what a reader
would need six weeks later - which band, what ratio, which shift - is copied
onto the record here rather than looked up from a round that no longer exists.
Same pattern as `playbook_snapshot`: copy what is needed to where it is needed.

No I/O in this module. The SQL is in `repo.py` beside the rest of layer 3's.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from pdm.contracts import Role, ShiftId, UserId
from pdm.dispatch.domain import Band


class OverrideKind(StrEnum):
    """The two ways a person overrules the scheduler.

    Two values rather than one flag, because they are read by different people
    for different reasons: a disagreement is evidence about the score and a
    release is evidence about the gate, and the report argues about them
    separately.
    """

    PRIORITY_DISAGREEMENT = "priority_disagreement"
    RELEASE_HELD = "release_held"


class Override(BaseModel):
    """One recorded override, as it is written and as it is read back.

    `reason` is required and cannot be empty. An override with no reason is
    indistinguishable from a bug when somebody reads it later, which is the one
    thing this record exists to prevent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: OverrideKind
    work_order_ref: str = Field(min_length=1)
    user: UserId
    role: Role
    at: datetime
    reason: str = Field(min_length=1)

    # The round this was decided against. Empty on a disagreement, which is
    # about one ticket's rank and not about the shift; `load_ratio` is empty on
    # a release taken where there was no capacity to compute one from, which the
    # band then names (ADR-045 §3).
    band: Band | None = None
    load_ratio: float | None = None
    shift_id: ShiftId | None = None
    on_date: date | None = None

    @field_validator("reason")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """`min_length` admits "   ", and a reason of spaces is the same absence
        the record was written to refuse - it just gets past the schema."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("an override needs a reason (ADR-005)")
        return stripped

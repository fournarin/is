"""What the closed jobs say, on request (ADR-087).

Loop 1 (durations, ADR-066) and Loop 2 (thresholds, ADR-073) were built as pure
functions and merged with nothing calling them. This module is the caller. It
computes both loops when an engineer asks, from rows that are already there,
stores nothing and schedules nothing - the reading ADR-066 pointed at when it
said "a proposal is computed when asked", and ADR-050's argument that a read path
which recomputes cannot disagree with the thing it reports on.

**Nothing here writes, and there is no route that would.** Loop 1's number lives
on a playbook row that carries an engineer's approval (ADR-024) and Loop 2's
lives in `config/rules.yaml`, which is a file. Both are carried across by a
person, in the paths that already record who did it; a button here that wrote
either would be an approval with no approver (ADR-087 section 3).

Read by an engineer, who decides, and by a shift lead, who does not: the review
queue's argument (ADR-064) - somebody who cannot see a queue cannot ask why it is
not moving - and the same refusal at the endpoint rather than a hidden button
(invariant 6).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from pdm.api.deps import Db, Plant, requires
from pdm.contracts import MachineModel, PlaybookStatus, Role, RuleId, SymptomCode
from pdm.platform.auth.domain import Account
from pdm.playbooks import repo as playbooks
from pdm.work import repo as work
from pdm.work.domain import playbook_ref_for
from pdm.work.estimates import EstimateProposal
from pdm.work.estimates import propose as propose_estimate
from pdm.work.thresholds import NoProposal, ThresholdProposal
from pdm.work.thresholds import propose as propose_threshold

router = APIRouter(tags=["loops"])

_FROZEN = ConfigDict(frozen=True, extra="forbid")

_MAY_READ = (Role.ENGINEER, Role.SUPERVISOR)


class EstimateLine(BaseModel):
    """One playbook, and what its closed jobs did or did not ask for.

    The pairs with nothing to propose are on the list rather than filtered out of
    it. `propose()` returns one `None` for three different situations - too few
    usable jobs, none at all, and a median that lands on the estimate already
    there - and it does that deliberately (ADR-066). Distinguishing them here
    would mean a second copy of its filter for what counts as usable, so this
    says what it actually knows: how many closed orders were read, and that no
    change was proposed (principle 5, ADR-087 section 4).
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    # The symptom as the plant names it; the code alone was what the third
    # trial's engineer read here (ADR-126).
    symptom_title: str | None = None
    machine_model: MachineModel
    current_minutes: int
    # A needs_review playbook is still served, and still prices work (ADR-018),
    # so it is still worth a proposal - with the reviewer told which it is.
    playbook_status: PlaybookStatus
    closed_orders: int
    proposal: EstimateProposal | None


class FloorNote(BaseModel):
    """What a technician wrote when they closed a job (ADR-117)."""

    model_config = _FROZEN

    work_order_ref: str
    machine_id: str
    symptom_code: str | None
    symptom_title: str | None = None
    playbook_ref: str | None
    outcome: str | None
    closed_at: datetime
    note: str


class FloorNotes(BaseModel):
    """The notes, and the clock to read their times on (ADR-093)."""

    model_config = _FROZEN

    timezone: str
    notes: list[FloorNote]


class ThresholdLine(BaseModel):
    """One rule, and either a proposal or the named reason there is none.

    Every rule in `rules.yaml` appears, including the ones no work has ever
    closed behind. A rule missing from this list would read as a rule nobody had
    to think about, when what it means is that the evidence is empty - and for a
    safety-linked rule the refusal is the whole point of the row (invariant 11).
    """

    model_config = _FROZEN

    rule_id: RuleId
    # What the rule watches for, in the plant's words (`rules.yaml` title).
    title: str | None = None
    machine_model: MachineModel
    metric_name: str
    comparison: str
    current_threshold: float
    safety_critical: bool
    # Counted rather than dropped, as the reader hands it over: a Finding whose
    # evidence recorded no number is a gap in what layer 1 wrote down (ADR-073).
    without_a_reading: int
    proposal: ThresholdProposal | None
    refusal: NoProposal | None


@router.get("/loops/estimates", response_model=list[EstimateLine])
def estimates(
    conn: Db,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_estimate_proposals"))],
) -> list[EstimateLine]:
    """Loop 1 over every playbook that prices work, computed now.

    The two constants come from `policy.yaml` and are passed in rather than
    defaulted, which is how ADR-066 wrote the signature: a default here would
    answer even when the file did not.

    Proposals first. The question this screen is opened with is "is there
    anything to approve", and an answer read from the top is one somebody
    finishes reading (ADR-060).
    """
    policy = plant.policy.estimates
    wording = plant.wording()
    lines = []
    for pair in playbooks.priced_pairs(conn):
        jobs = work.closed_jobs_for(
            conn, playbook_ref=str(playbook_ref_for(pair.symptom_code, pair.machine_model))
        )
        lines.append(
            EstimateLine(
                symptom_code=pair.symptom_code,
                symptom_title=wording.symptom(pair.symptom_code),
                machine_model=pair.machine_model,
                current_minutes=pair.estimated_minutes,
                playbook_status=pair.status,
                closed_orders=len(jobs),
                proposal=propose_estimate(
                    jobs,
                    symptom_code=pair.symptom_code,
                    machine_model=pair.machine_model,
                    current_minutes=pair.estimated_minutes,
                    min_observations=policy.min_observations,
                    max_change_ratio=policy.max_change_ratio,
                ),
            )
        )
    return sorted(
        lines,
        key=lambda line: (line.proposal is None, line.machine_model, line.symptom_code),
    )


@router.get("/loops/thresholds", response_model=list[ThresholdLine])
def thresholds(
    conn: Db,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_threshold_proposals"))],
) -> list[ThresholdLine]:
    """Loop 2 over every configured rule, computed now.

    This is where `safety_critical` stops being a field with a name that happens
    to match a parameter and becomes a value carried from `rules.yaml` into the
    refusal it was written for (invariant 11, ADR-022). The rule's own facts go
    in one at a time rather than as a `RuleConfig`, because ADR-073 section 7
    keeps `work/` away from the file layer 1 boots from.
    """
    policy = plant.policy.thresholds
    behind = {firings.rule_id: firings for firings in work.firings_behind_rules(conn)}

    lines = []
    for rule in plant.rules.rules:
        firings = behind.get(rule.rule_id)
        outcome = propose_threshold(
            firings.firings if firings else (),
            rule_id=rule.rule_id,
            comparison=rule.comparison,
            current_threshold=rule.threshold,
            safety_critical=rule.safety_critical,
            min_observations=policy.min_observations,
            max_change_ratio=policy.max_change_ratio,
        )
        proposal: ThresholdProposal | None = None
        refusal: NoProposal | None = None
        if isinstance(outcome, ThresholdProposal):
            proposal = outcome
        else:
            refusal = outcome
        lines.append(
            ThresholdLine(
                rule_id=rule.rule_id,
                title=rule.title,
                machine_model=rule.machine_model,
                metric_name=rule.metric_name,
                comparison=rule.comparison,
                current_threshold=rule.threshold,
                safety_critical=rule.safety_critical,
                without_a_reading=firings.without_a_reading if firings else 0,
                proposal=proposal,
                refusal=refusal,
            )
        )
    return sorted(lines, key=lambda line: (line.proposal is None, line.rule_id))


# The page shows the latest notes, not an archive; the full record stays on each
# closed order.
_NOTES_SHOWN = 200


@router.get("/loops/notes", response_model=FloorNotes)
def notes(
    conn: Db,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_technician_notes"))],
) -> FloorNotes:
    """The notes technicians left at close, newest first (ADR-117).

    Read by the engineer who owns the procedures and the shift lead who assigns
    them. Nothing here changes a playbook: a note that should become a step goes
    through the review queue, which records who approved it (ADR-064).
    """
    wording = plant.wording()
    return FloorNotes(
        timezone=plant.plant.timezone,
        notes=[
            FloorNote(
                work_order_ref=str(row["work_order_ref"]),
                machine_id=str(row["machine_id"]),
                symptom_code=row["symptom_code"],
                symptom_title=(
                    wording.symptom(row["symptom_code"]) if row["symptom_code"] else None
                ),
                playbook_ref=row["playbook_ref"],
                outcome=row["outcome"],
                closed_at=row["closed_at"],
                note=str(row["note"]),
            )
            for row in work.notes_from_the_floor(conn, limit=_NOTES_SHOWN)
        ],
    )

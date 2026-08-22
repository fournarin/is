"""What the system has no answer for yet (design.md 4, ADR-038, ADR-060).

A symptom arriving with no playbook is queued for authoring and ordered by how
often it is seen, so the system works out for itself which playbook is worth
writing next. That mechanism has been built for several slices and there has been
nowhere to look at it, which leaves an engineer choosing what to write next by
memory - and that choice is the one that decides whether the store ever covers
the long tail.

Three lists, and every figure on them is a count of rows that already exist:
Findings that were raised, proposals that are pending, playbooks the withdrawal
cascade flagged. **Nothing here computes an aggregate in order to have something
to display** (ADR-050): no summary table, no scheduled recomputation, and no
number a reader cannot act on. The test for each list is the same one the
overview screen has to pass - *when this number is bad, who does what
immediately?* - and each answers it with an identifier that takes somebody
straight to the queue.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from pdm.api.deps import Db, Plant, Time, requires
from pdm.contracts import MachineId, MachineModel, Role, SymptomCode
from pdm.platform.auth.domain import Account
from pdm.playbooks import repo as playbooks
from pdm.playbooks.domain import PendingForPair
from pdm.triggers import repo as triggers
from pdm.triggers.domain import SymptomSeen

router = APIRouter(tags=["overview"])

# An engineer decides what to write next; a shift lead is the person who asks
# why the queue is not moving (ADR-024). Neither list is a technician's: what a
# technician needs from a missing playbook is the honest "not found" on their own
# ticket, which is principle 5 and a different screen.
_MAY_READ = (Role.ENGINEER, Role.SUPERVISOR)

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class SymptomGap(BaseModel):
    """One symptom, on one machine model, with nothing approved to serve for it.

    `machine_model` is half the identifier of a playbook (ADR-018) and half of
    what a drafting request takes, so this row is what the overview's
    "[ Write it ]" button posts to `/playbooks/drafts`.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel

    # Findings raised, then firings within them. Ranked on the first, for the
    # reason `SymptomSeen` records: one channel stuck over its threshold all
    # morning is one event, however many times the rule fired.
    findings: int
    occurrences: int
    machines: tuple[MachineId, ...]

    first_seen: datetime
    last_seen: datetime

    # Whether somebody has already asked for this one. Without it the row reads
    # as "nobody has done anything", and the button posts a second drafting job
    # for work that is already queued behind the one GPU (ADR-029, ADR-040).
    proposals_waiting: int = 0


class ModelQueue(BaseModel):
    """The review queue for one machine model, which is how it is worked.

    Grouped rather than listed because a reviewer stays in one context: reading
    two manuals alternately is how a step from the wrong model gets waved
    through, which is the one thing ADR-015's recall setting does not relax.
    """

    model_config = _FROZEN

    machine_model: MachineModel
    waiting: int
    oldest: datetime


class FlaggedPlaybook(BaseModel):
    """A playbook being served right now with a warning on it (ADR-018).

    On this screen because it is the only list that says how much of what
    technicians are working from is out of date. The row is not a fault; it is a
    debt, and one an engineer clears in the same queue as everything else.
    """

    model_config = _FROZEN

    symptom_code: SymptomCode
    machine_model: MachineModel
    revision: int
    review_reason: str | None = None


class Unanswered(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[SymptomGap, ...]


class AwaitingReview(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[ModelQueue, ...]


class ManualChanged(BaseModel):
    model_config = _FROZEN

    count: int
    rows: tuple[FlaggedPlaybook, ...]


class Gaps(BaseModel):
    """The three lists, each with its total beside the rows returned.

    The totals are of everything found, not of what fits: a list truncated to the
    first twenty rows still reports that there are sixty, because a silent cap
    reads as "that is all there is" (ADR-045's rule about what a summary owes its
    reader, one screen up).
    """

    model_config = _FROZEN

    at: datetime
    no_playbook: Unanswered
    awaiting_review: AwaitingReview
    manual_changed: ManualChanged

    # Machines that raised Findings and are not in `plant.yaml` any more.
    # Reported rather than dropped, for ADR-048's reason: their symptoms cannot
    # be filed under a machine model, so they cannot be drafted for, and a gap
    # list that quietly discarded them would say the store covers work it does
    # not. Every round already counts the same drift.
    unplaced_machines: tuple[MachineId, ...] = ()


@dataclass
class _Fold:
    """One gap being accumulated across the machines of one model.

    Mutable, private, and never returned: the row that leaves this module is a
    frozen `SymptomGap`. Folding into a dict of dicts was the first version and
    cost more in casts than the class costs in lines.
    """

    findings: int
    occurrences: int
    machines: set[MachineId]
    first_seen: datetime
    last_seen: datetime

    def absorb(self, row: SymptomSeen) -> None:
        self.findings += row.findings
        self.occurrences += row.occurrences
        self.machines.add(row.machine_id)
        self.first_seen = min(self.first_seen, row.first_seen)
        self.last_seen = max(self.last_seen, row.last_seen)


def rank_gaps(
    seen: Iterable[SymptomSeen],
    *,
    model_of: Callable[[MachineId], MachineModel],
    served: set[tuple[SymptomCode, MachineModel]],
    pending: Iterable[PendingForPair],
) -> tuple[list[SymptomGap], list[MachineId]]:
    """Fold what was seen onto machine models, drop what is answered, rank.

    Pure, and separate from the handler for the usual reason (invariant 10): the
    ordering is the whole content of the first list, and it should be testable
    without a database, a session and a plant.

    What is ranked, and what counts as answered, is ADR-060. Findings are per
    machine and playbooks are per model (ADR-018), so the fold is where the two
    meet. A symptom on four machines of one model is one gap
    worth four events, not four gaps - the playbook that answers it is one row.
    """
    waiting = {(row.symptom_code, row.machine_model): row.waiting for row in pending}
    folded: dict[tuple[SymptomCode, MachineModel], _Fold] = {}
    unplaced: set[MachineId] = set()

    for row in seen:
        try:
            model = model_of(row.machine_id)
        except KeyError:
            # The layout moved on and this machine went with it. Named, not
            # silently discarded (ADR-048 section 3).
            unplaced.add(row.machine_id)
            continue

        pair = (row.symptom_code, model)
        if pair in served:
            continue

        gathered = folded.get(pair)
        if gathered is None:
            folded[pair] = _Fold(
                findings=row.findings,
                occurrences=row.occurrences,
                machines={row.machine_id},
                first_seen=row.first_seen,
                last_seen=row.last_seen,
            )
            continue
        gathered.absorb(row)

    rows = [
        SymptomGap(
            symptom_code=symptom_code,
            machine_model=model,
            findings=gathered.findings,
            occurrences=gathered.occurrences,
            machines=tuple(sorted(gathered.machines)),
            first_seen=gathered.first_seen,
            last_seen=gathered.last_seen,
            proposals_waiting=waiting.get((symptom_code, model), 0),
        )
        for (symptom_code, model), gathered in folded.items()
    ]
    # Most often seen first, then the most recent: two symptoms seen twice each
    # are not equally worth writing if one of them stopped in March. The pair
    # itself is the last key so that the same data always ranks the same way and
    # a test can say what the order is rather than what it is not.
    rows.sort(
        key=lambda gap: (
            -gap.findings,
            -gap.occurrences,
            -gap.last_seen.timestamp(),
            gap.symptom_code,
            gap.machine_model,
        )
    )
    return rows, sorted(unplaced)


def group_by_model(pending: Iterable[PendingForPair]) -> list[ModelQueue]:
    """The pending proposals as the reviewer meets them: one model at a time."""
    counted: dict[MachineModel, ModelQueue] = {}
    for row in pending:
        current = counted.get(row.machine_model)
        if current is None:
            counted[row.machine_model] = ModelQueue(
                machine_model=row.machine_model, waiting=row.waiting, oldest=row.oldest
            )
            continue
        counted[row.machine_model] = ModelQueue(
            machine_model=row.machine_model,
            waiting=current.waiting + row.waiting,
            oldest=min(current.oldest, row.oldest),
        )
    # Oldest queue first: the model nobody has looked at for three weeks is the
    # one the screen should name, not the one whose name sorts first.
    return sorted(counted.values(), key=lambda group: (group.oldest, group.machine_model))


@router.get("/overview/gaps", response_model=Gaps)
def gaps(
    conn: Db,
    clock: Time,
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_gaps"))],
    # Bounded like every other list route, and the total is returned beside it so
    # the bound is visible rather than silent.
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> Gaps:
    """Three questions an engineer otherwise answers from memory.

    Read-only, computed from the rows as they stand at the moment of asking, and
    stamped with when that was - a screen reporting a queue has to say whether it
    is describing now or five minutes ago (ADR-050).
    """
    pending = playbooks.pending_by_pair(conn)
    ranked, unplaced = rank_gaps(
        triggers.symptoms_seen(conn),
        model_of=plant.model_of,
        served=playbooks.served_pairs(conn),
        pending=pending,
    )
    flagged = [
        FlaggedPlaybook(
            symptom_code=playbook.symptom_code,
            machine_model=playbook.machine_model,
            revision=playbook.revision,
            review_reason=review_reason,
        )
        for playbook, review_reason in playbooks.needing_review(conn)
    ]
    by_model = group_by_model(pending)

    return Gaps(
        at=clock.now(),
        no_playbook=Unanswered(count=len(ranked), rows=tuple(ranked[:limit])),
        awaiting_review=AwaitingReview(
            count=sum(group.waiting for group in by_model), rows=tuple(by_model[:limit])
        ),
        manual_changed=ManualChanged(count=len(flagged), rows=tuple(flagged[:limit])),
        unplaced_machines=tuple(unplaced),
    )

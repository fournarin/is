"""Serving approved playbooks, and the review queue that fills them (ADR-038).

Two audiences with opposite needs, which is why they are two methods and not one
with a flag. Runtime asks "what may I put in front of a technician"; the review
screen asks "what is waiting for me". Nothing here can answer the first question
with the second's data - the table it reads holds no drafts.

It opens no connection: the caller supplies one, so that applying a proposal, the
row it overwrites and the access log entry commit together.
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection

from pdm.contracts import (
    MachineModel,
    Playbook,
    PlaybookStatus,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.platform.clock import Clock
from pdm.playbooks import repo
from pdm.playbooks.domain import Proposal, ProposalStatus, Served


class NotAnEngineer(Exception):
    """Only an engineer may approve a playbook (ADR-024, invariant 6)."""


class PlaybookStore:
    """The one way in and out of the playbook table."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def serve(
        self,
        conn: Connection[Any],
        symptom_code: SymptomCode,
        machine_model: MachineModel,
    ) -> Served | None:
        """What a technician may be given for this symptom, or nothing.

        `None` is a real answer and the caller owes the technician the honest
        version of it - "not found, see the manual or ask an engineer" - rather
        than the nearest thing in the queue (principle 5, invariant 3).
        """
        found = repo.get(conn, symptom_code, machine_model)
        if found is None:
            return None

        playbook, review_reason = found
        if playbook.status is PlaybookStatus.NEEDS_REVIEW:
            return Served(
                playbook=playbook,
                # Shown to the technician, not only logged. A superseded
                # procedure that looks identical to a current one is how the
                # cascade in ADR-018 stops being a safety mechanism.
                warning=(
                    review_reason
                    or "this playbook is waiting for review and may not match the current manual"
                ),
            )
        return Served(playbook=playbook)

    def review_queue(self, conn: Connection[Any], *, limit: int = 50) -> list[Proposal]:
        return repo.queue(conn, limit=limit)

    def flagged(self, conn: Connection[Any]) -> list[tuple[Playbook, str | None]]:
        return repo.needing_review(conn)

    def approve(
        self,
        conn: Connection[Any],
        proposal_id: int,
        *,
        approver: UserId,
        approver_role: Role,
        required_skill: SkillId | None = None,
        estimated_minutes: int | None = None,
        note: str | None = None,
    ) -> Playbook:
        """Apply a pending proposal to the served row.

        The role check is here as well as at the endpoint. The endpoint is what
        invariant 6 names, because that is where a person is refused; this one
        exists because the worker and the seed script never touch an endpoint,
        and a rule enforced in one of the two places is a rule with a way round
        it.

        `required_skill` and `estimated_minutes` are what the engineer filled in
        where the manual stated nothing. Passing neither uses what the page said,
        and a proposal that has neither raises rather than inventing a figure the
        scheduler would compute with (ADR-037 section 8).
        """
        if approver_role is not Role.ENGINEER:
            raise NotAnEngineer(
                f"{approver} holds {approver_role.value}; only an engineer may approve a "
                "playbook (ADR-024)"
            )

        pending = repo.proposal(conn, proposal_id)
        if pending is None:
            raise repo.NothingToApply(f"there is no proposal {proposal_id}")
        if not pending.can_be_applied:
            raise repo.NothingToApply(
                f"proposal {proposal_id} is {pending.status.value} and has "
                f"{len(pending.steps)} step(s); there is nothing to approve"
            )

        now = self.clock.now()
        skill = required_skill or pending.proposed_skill
        minutes = estimated_minutes or pending.proposed_minutes
        if skill is None or minutes is None:
            raise ValueError(
                f"proposal {proposal_id} states "
                f"{'no skill' if skill is None else 'no duration'} and none was supplied; "
                "the approver has to say which, because a value invented here would carry "
                "the authority of the manual and the provenance of nothing"
            )

        # Built through the contract, so invariant 4 - every step in an approved
        # playbook carries its source document and page - is checked by the same
        # validator wherever a playbook is approved from, and cannot be skipped
        # by an endpoint that forgot (ADR-015).
        playbook = Playbook(
            symptom_code=pending.symptom_code,
            machine_model=pending.machine_model,
            steps=pending.steps,
            tools=pending.tools,
            estimated_minutes=minutes,
            required_skill=skill,
            source_doc=pending.steps[0].source_doc,
            page=pending.steps[0].page,
            status=PlaybookStatus.APPROVED,
            approved_by=approver,
            approved_at=now,
            approver_role=approver_role,
        )

        saved = repo.save_approved(
            conn,
            playbook,
            approved_by=approver,
            approved_at=now,
            approver_role=approver_role,
        )
        repo.decide(
            conn,
            proposal_id,
            status=ProposalStatus.APPLIED,
            decided_by=approver,
            decided_at=now,
            note=note,
        )
        # Deliberately not touching the pair's other pending proposals. A
        # re-draft that quietly closed a technician's objection would lose the
        # one report in this system that came from somebody at the machine
        # (ADR-038 section 4).
        return saved

    def dismiss(
        self,
        conn: Connection[Any],
        proposal_id: int,
        *,
        decided_by: UserId,
        decided_role: Role,
        note: str,
    ) -> Proposal:
        """Turn a proposal down, on the record.

        A note is required rather than optional. The dismissals are what answer
        "why does this symptom still have no playbook when three people have
        looked at it", and a queue of unexplained refusals answers nothing.
        """
        if decided_role is not Role.ENGINEER:
            raise NotAnEngineer(
                f"{decided_by} holds {decided_role.value}; only an engineer may decide on a "
                "proposal (ADR-024)"
            )
        if not note.strip():
            raise ValueError("a dismissal has to say why")

        return repo.decide(
            conn,
            proposal_id,
            status=ProposalStatus.DISMISSED,
            decided_by=decided_by,
            decided_at=self.clock.now(),
            note=note,
        )

"""Serving approved playbooks, and the review queue that fills them (ADR-038).

Two audiences with opposite needs, which is why they are two methods and not one
with a flag. Runtime asks "what may I put in front of a technician"; the review
screen asks "what is waiting for me". Nothing here can answer the first question
with the second's data - the table it reads holds no drafts.

It opens no connection: the caller supplies one, so that applying a proposal, the
row it overwrites and the access log entry commit together.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from psycopg import Connection

from pdm.contracts import (
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.contracts.wording import figures, quantities
from pdm.platform.clock import Clock
from pdm.playbooks import repo
from pdm.playbooks.domain import (
    Proposal,
    ProposalOrigin,
    ProposalStatus,
    Served,
    apply_edits,
    edits_between,
    energy_problems,
    primary_source,
)


class NotAnEngineer(Exception):
    """Only an engineer may approve a playbook (ADR-024, invariant 6)."""


class NotADraft(Exception):
    """Sending back asks the drafter to try again, and only a draft has one.

    A technician's objection came from a person standing at a machine (ADR-038
    section 4). There is nothing to re-run it through, and answering it with a
    drafting job would file the model's opinion as a reply to somebody who saw
    the fault.
    """


class PlaybookStore:
    """The one way in and out of the playbook table."""

    def __init__(self, clock: Clock, *, skills: Iterable[str] = ()) -> None:
        self.clock = clock
        # The vocabulary from plant.yaml. An approver types a skill where the
        # manual stated none, and a typo there produces an approved playbook
        # dispatch can never assign to anybody - the silent failure invariant 13
        # exists to prevent (ADR-027). `Drafting` already refuses labels the
        # config does not know; approval is the other way in.
        self.skills = frozenset(skills)

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

    def opened(self, conn: Connection[Any], proposal_id: int) -> None:
        """Stamp when a reviewer opened this, from the Clock and nowhere else.

        The measurement ADR-064 wants is how long a decision took, and the only
        honest way to have it without a timer on the screen is to note the open
        here and subtract at the decision. A number the browser sends would be a
        number the browser can be wrong about, and this one goes in the report.
        """
        repo.opened(conn, proposal_id, at=self.clock.now())

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
        required_technicians: int | None = None,
        note: str | None = None,
        rewritten_steps: tuple[str, ...] | None = None,
        thai_steps: tuple[str, ...] | None = None,
        thai_tools: tuple[str, ...] | None = None,
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

        `rewritten_steps` is "edit and approve": the reviewer's wording, position
        for position, with the drafter's provenance carried across untouched. The
        difference is stored on the proposal, so an approval that changed what the
        manual said names the person who changed it and what they changed
        (ADR-064). The figure gate is deliberately **not** re-run over the result:
        it exists to stop a model quoting a torque the page does not carry, and
        the engineer approving here is the authority ADR-003 put in the model's
        way. Refusing their correction on the strength of the check the model has
        to pass would make the reviewer the least trusted party in the system.
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
        # Raises before anything is claimed when the lists do not line up: a
        # reviewer who added or dropped a step is asking for something the
        # approval path does not do, and finding that out after the proposal has
        # been marked applied would leave a decided row with no playbook.
        edits = () if rewritten_steps is None else edits_between(pending.steps, rewritten_steps)
        steps = apply_edits(pending.steps, edits)
        if thai_steps is not None:
            steps = in_thai(steps, thai_steps)
        tools_th = tools_in_thai(pending.tools, thai_tools) if thai_tools is not None else ()

        skill = required_skill or pending.proposed_skill
        minutes = estimated_minutes or pending.proposed_minutes
        if skill is None or minutes is None:
            raise ValueError(
                f"proposal {proposal_id} states "
                f"{'no skill' if skill is None else 'no duration'} and none was supplied; "
                "the approver has to say which, because a value invented here would carry "
                "the authority of the manual and the provenance of nothing"
            )
        # Energy marks that would leave a point unverified or unrestored, or a
        # restore step that also runs the machine, are not approved (REQ-H-05, ADR-136).
        energy = energy_problems(steps)
        if energy:
            raise ValueError("; ".join(energy))
        if self.skills and skill not in self.skills:
            raise ValueError(
                f"'{skill}' is not one of the skills declared in plant.yaml "
                f"({', '.join(sorted(self.skills))}); a playbook asking for a skill nobody "
                "holds is one dispatch can never assign (invariant 13)"
            )

        # Claimed before anything is written. Two engineers approving the same
        # proposal at the same moment both got here; the UPDATE ... WHERE status
        # = 'pending' matches for exactly one, and the other raises before it can
        # overwrite the row. Written the other way round - save then claim - the
        # loser's approval had already landed, and the 409 it was handed was a
        # sentence about a change that had happened anyway (`deps.connection`
        # commits on HTTPException, deliberately, so the access log survives).
        repo.decide(
            conn,
            proposal_id,
            status=ProposalStatus.APPLIED,
            decided_by=approver,
            decided_at=now,
            note=note,
            edits=edits,
        )

        # Built through the contract, so invariant 4 - every step in an approved
        # playbook carries its source document and page - is checked by the same
        # validator wherever a playbook is approved from, and cannot be skipped
        # by an endpoint that forgot (ADR-015).
        source_doc, page = primary_source(steps)
        playbook = Playbook(
            symptom_code=pending.symptom_code,
            machine_model=pending.machine_model,
            steps=steps,
            tools=pending.tools,
            tools_th=tools_th,
            estimated_minutes=minutes,
            required_skill=skill,
            # Not carried on the proposal: nothing drafts it yet, and ADR-025
            # makes the default of one the number that reads the shift's capacity
            # low. The approver is the person who knows, so the field is theirs.
            required_technicians=required_technicians or 1,
            source_doc=source_doc,
            page=page,
            status=PlaybookStatus.APPROVED,
            approved_by=approver,
            approved_at=now,
            approver_role=approver_role,
        )

        # Deliberately not touching the pair's other pending proposals. A
        # re-draft that quietly closed a technician's objection would lose the
        # one report in this system that came from somebody at the machine
        # (ADR-038 section 4).
        return repo.save_approved(
            conn,
            playbook,
            approved_by=approver,
            approved_at=now,
            approver_role=approver_role,
        )

    def send_back(
        self,
        conn: Connection[Any],
        proposal_id: int,
        *,
        decided_by: UserId,
        decided_role: Role,
        note: str,
    ) -> Proposal:
        """This draft is wrong; ask again, with the reviewer's note as the question.

        The note is required and it is not a formality: the caller turns it into
        the question the next drafting job is given, and "no" retrieves the same
        pages as the attempt that has just been refused (ADR-039 section 7,
        ADR-064). Queuing that job is the endpoint's business, not this method's -
        the queue is the API's to write, and a store that enqueued would be layer
        2 deciding when the one GPU is spent (ADR-026).

        Only a drafted proposal can be sent back. `NotADraft` says why.
        """
        if decided_role is not Role.ENGINEER:
            raise NotAnEngineer(
                f"{decided_by} holds {decided_role.value}; only an engineer may decide on a "
                "proposal (ADR-024)"
            )
        if not note.strip():
            raise ValueError("sending a draft back has to say what is wrong with it")

        pending = repo.proposal(conn, proposal_id)
        if pending is None:
            raise repo.NothingToApply(f"there is no proposal {proposal_id}")
        if pending.origin is not ProposalOrigin.DRAFTED:
            raise NotADraft(
                f"proposal {proposal_id} came from {pending.origin.value}, not from the "
                "drafter; there is nothing to send it back to, and a report from somebody "
                "at the machine is dismissed with a reason or acted on (ADR-038)"
            )

        return repo.decide(
            conn,
            proposal_id,
            status=ProposalStatus.SENT_BACK,
            decided_by=decided_by,
            decided_at=self.clock.now(),
            note=note,
        )

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


def in_thai(steps: tuple[PlaybookStep, ...], thai: tuple[str, ...]) -> tuple[PlaybookStep, ...]:
    """The approver's Thai for each step, position for position (ADR-095).

    A blank entry leaves that step without Thai, and the technician reads the
    manual's words. **Every figure in the Thai must be a figure in the step it
    renders, and the other way round.** A translation is where a 42 becomes a
    24 with nobody noticing, because the person checking reads the language
    they are fluent in and trusts the numbers. Unlike an edit of the English
    (ADR-064), this has an exact answer, so it is checked.
    """
    if len(thai) != len(steps):
        raise ValueError(
            f"มีคำแปล {len(thai)} ขั้น แต่ขั้นตอนมี {len(steps)} ขั้น ต้องแปลตามลำดับขั้นให้ครบ "
            "(ขั้นไหนไม่แปลให้เว้นว่างไว้)"
        )
    rendered = []
    for number, (step, text) in enumerate(zip(steps, thai, strict=True), start=1):
        text = text.strip()
        if not text:
            rendered.append(step)
            continue
        _same_figures(step.text, text, where=f"ขั้นที่ {number}")
        rendered.append(step.model_copy(update={"text_th": text}))
    return tuple(rendered)


def tools_in_thai(tools: tuple[str, ...], thai: tuple[str, ...]) -> tuple[str, ...]:
    """The approver's Thai for each tool, position for position (ADR-130).

    The same rule as a step's Thai: "torque wrench 5-60 Nm" rendered as a
    wrench of 5-50 is a technician fetching the wrong tool, so every figure and
    every stated unit must come through. A blank keeps the manual's words.
    """
    if len(thai) != len(tools):
        raise ValueError(
            f"มีชื่อเครื่องมือภาษาไทย {len(thai)} รายการ แต่เครื่องมือมี {len(tools)} รายการ "
            "ต้องใส่ตามลำดับให้ครบ (รายการไหนไม่แปลให้เว้นว่างไว้)"
        )
    rendered = []
    for number, (tool, text) in enumerate(zip(tools, thai, strict=True), start=1):
        text = text.strip()
        if text:
            _same_figures(tool, text, where=f"เครื่องมือรายการที่ {number}")
        rendered.append(text)
    # All blank is no rendering at all, not a list of blanks to carry around.
    return tuple(rendered) if any(rendered) else ()


def _same_figures(original: str, text: str, *, where: str) -> None:
    """Every figure in the Thai is a figure in the original and the other way
    round, and every unit the original states comes through (ADR-095, ADR-108)."""
    wanted, got = figures(original), figures(text)
    if wanted != got:
        missing = ", ".join(sorted(f"{one:f}" for one in wanted - got)) or "-"
        extra = ", ".join(sorted(f"{one:f}" for one in got - wanted)) or "-"
        raise ValueError(
            f"{where}: ตัวเลขในคำแปลไม่ตรงกับต้นฉบับ "
            f"(ขาด {missing} · เกิน {extra}) ตรวจค่าแรงบิดและตัวเลขอีกครั้ง"
        )
    # A unit the manual states must come through unchanged (ADR-108): the
    # figure check alone passed a torque of 3 Nm rendered as 3 มม.
    lost = quantities(original) - quantities(text)
    if lost:
        named = ", ".join(sorted(f"{figure:f} {unit}" for figure, unit in lost))
        raise ValueError(
            f"{where}: หน่วยในคำแปลไม่ตรงกับต้นฉบับ ({named}) ใส่ตัวเลขพร้อมหน่วยเดิม เช่น Nm หรือ นิวตันเมตร"
        )

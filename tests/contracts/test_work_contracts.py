"""Rules the work contracts refuse to break.

These are not field-presence tests. Each one covers a way the system has been
documented to fail silently, where the contract is the last place the mistake
can still be caught cheaply.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pdm.contracts import (
    Assignee,
    Finding,
    FindingKind,
    FindingRef,
    MachineId,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    PMTaskRef,
    Role,
    RuleId,
    Severity,
    Signal,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.contracts.enums import BlockedReason
from pdm.contracts.ids import ComponentLabel, DocumentId, MachineModel, PlaybookRef, SkillId

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-012")


def _step(page: int = 142) -> PlaybookStep:
    return PlaybookStep(
        text="Stop the robot using the emergency stop button",
        source_doc=DocumentId("a" * 64),
        page=page,
        confidence=0.9,
    )


def _finding(**overrides: object) -> Finding:
    base: dict[str, object] = {
        "machine_id": MOTOR,
        "component": ComponentLabel("belt_motor"),
        "symptom_code": SymptomCode("SYM-014"),
        "severity": Severity.HIGH,
        "rule_id": RuleId("R-motor-temp"),
        "detected_at": NOW,
        "evidence": {"metric": "temp_c", "value": 92.0, "threshold": 85.0},
    }
    return Finding(**(base | overrides))  # type: ignore[arg-type]


def _order(**overrides: object) -> WorkOrder:
    base: dict[str, object] = {
        "origin": WorkOrderOrigin.MANUAL,
        "machine_id": MOTOR,
        "severity": Severity.HIGH,
        # The scheduler-facing copies (ADR-041). Required, because an order the
        # load gate cannot price is an order that cannot be scheduled, and a
        # default here would let one exist.
        "estimated_minutes": 45,
        "reason": "reported by a technician on the floor",
    }
    return WorkOrder(**(base | overrides))  # type: ignore[arg-type]


class TestEverythingIsFrozen:
    """A pure dispatch() cannot stay pure if callers can edit its inputs."""

    def test_a_finding_cannot_be_mutated(self) -> None:
        with pytest.raises(ValidationError):
            _finding().machine_id = MachineId("MC-999")

    def test_a_work_order_cannot_be_mutated(self) -> None:
        with pytest.raises(ValidationError):
            _order().severity = Severity.LOW

    def test_an_unexpected_field_is_rejected_rather_than_ignored(self) -> None:
        """A typo in a field name must fail, not silently store nothing."""
        with pytest.raises(ValidationError):
            _finding(machnie_id=MOTOR)


class TestPredictionsCarryTheirUncertainty:
    """ADR-020 and ui.md 2.2: the interval is never dropped for tidiness."""

    def test_a_predicted_finding_without_an_eta_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="eta"):
            _finding(kind=FindingKind.PREDICTED)

    def test_a_predicted_finding_without_a_confidence_interval_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="eta_confidence"):
            _finding(kind=FindingKind.PREDICTED, eta=NOW + timedelta(hours=6))

    def test_a_complete_prediction_is_accepted(self) -> None:
        finding = _finding(
            kind=FindingKind.PREDICTED,
            eta=NOW + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
        )
        assert finding.eta_confidence == timedelta(hours=2)

    def test_a_detected_finding_may_not_claim_an_eta(self) -> None:
        """The threshold is already crossed; a forecast would contradict it."""
        with pytest.raises(ValidationError, match="already crossed"):
            _finding(kind=FindingKind.DETECTED, eta=NOW + timedelta(hours=6))


class TestEveryStepSaysWhereItCameFrom:
    """Invariant 4's other half, unenforced until ADR-084.

    `page` was checked by `Field(ge=1)` and `source_doc` by nothing, so a step
    citing page 142 of no document constructed without error. #105 found it by
    running the case rather than by reading the validator. The check is on the
    field, so a draft is refused as well as an approval: provenance comes from
    the drafter, and by the time a reviewer sees the step it is not theirs to
    supply (ADR-064).
    """

    @pytest.mark.parametrize("nothing", ["", " ", "\t\n"])
    def test_a_step_citing_no_document_is_refused(self, nothing: str) -> None:
        with pytest.raises(ValidationError, match="page of no document"):
            PlaybookStep(
                text="Isolate the drive",
                source_doc=DocumentId(nothing),
                page=1,
                confidence=0.9,
            )

    def test_a_step_that_names_its_document_is_accepted(self) -> None:
        assert _step().source_doc == DocumentId("a" * 64)

    def test_an_unattributed_step_cannot_be_read_back_off_a_stored_row(self) -> None:
        """The read path for `playbook_snapshot` and for `playbook.steps` is
        `model_validate` (`work/repo.py`, `playbooks/repo.py`), so the migration
        that proves no stored row is unattributed is what keeps this from
        stopping an old work order from loading (ADR-084 section 2)."""
        with pytest.raises(ValidationError, match="page of no document"):
            PlaybookStep.model_validate(
                {"text": "Isolate the drive", "source_doc": "", "page": 1, "confidence": 0.9}
            )


class TestApprovedPlaybooksAreAccountable:
    """Invariant 4 and ADR-024, enforced where they cannot be forgotten."""

    def _approved(self, **overrides: object) -> Playbook:
        base: dict[str, object] = {
            "symptom_code": SymptomCode("SYM-014"),
            "machine_model": MachineModel("R-2000iC"),
            "steps": (_step(),),
            "estimated_minutes": 45,
            "required_skill": SkillId("robot_mechanical"),
            "source_doc": DocumentId("a" * 64),
            "page": 142,
            "status": PlaybookStatus.APPROVED,
            "approved_by": UserId("eng-01"),
            "approved_at": NOW,
            "approver_role": Role.ENGINEER,
        }
        return Playbook(**(base | overrides))  # type: ignore[arg-type]

    def test_a_complete_approval_is_accepted(self) -> None:
        assert self._approved().revision == 1

    def test_approval_without_an_approver_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="who approved it"):
            self._approved(approved_by=None)

    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.SUPERVISOR, Role.OPERATOR])
    def test_only_an_engineer_may_approve(self, role: Role) -> None:
        """ADR-024: a technician must not be able to approve their own proposal.
        Field knowledge is valuable, but it still passes the person accountable
        for the content."""
        with pytest.raises(ValidationError, match="only an engineer"):
            self._approved(approver_role=role)

    def test_an_approved_playbook_with_no_steps_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="nothing to approve"):
            self._approved(steps=())

    def test_a_playbook_citing_no_document_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="page of no document"):
            self._approved(source_doc=DocumentId(""))

    def test_a_draft_may_be_incomplete(self) -> None:
        """Drafts are what the review queue is for, and they never reach a
        technician (ADR-013)."""
        draft = Playbook(
            symptom_code=SymptomCode("SYM-014"),
            machine_model=MachineModel("R-2000iC"),
            steps=(_step(),),
            estimated_minutes=45,
            required_skill=SkillId("robot_mechanical"),
            source_doc=DocumentId("a" * 64),
            page=142,
        )
        assert draft.status is PlaybookStatus.DRAFT
        assert draft.approved_by is None


class TestWorkOrderDurations:
    """ADR-025: elapsed time is not worked time, and worked time is not repair
    time."""

    def test_a_job_across_a_shift_counts_worked_minutes_not_elapsed(self) -> None:
        """Started 15:00, finished 09:00 next day. Recording eighteen hours
        would destroy the estimate for that symptom from a single row."""
        start = datetime(2026, 3, 3, 15, 0, tzinfo=UTC)
        order = _order(
            work_segments=(
                WorkSegment(
                    user=UserId("tech-a"), started_at=start, ended_at=start + timedelta(hours=1)
                ),
                WorkSegment(
                    user=UserId("tech-b"),
                    started_at=start + timedelta(hours=18),
                    ended_at=start + timedelta(hours=18, minutes=30),
                ),
            )
        )
        assert order.actual_minutes == 90

    def test_two_people_on_one_job_both_count(self) -> None:
        """Capacity is person-minutes, so a helper's time is not free."""
        order = _order(
            assignees=(Assignee(user=UserId("tech-a")), Assignee(user=UserId("tech-b"))),
            work_segments=(
                WorkSegment(
                    user=UserId("tech-a"), started_at=NOW, ended_at=NOW + timedelta(minutes=60)
                ),
                WorkSegment(
                    user=UserId("tech-b"), started_at=NOW, ended_at=NOW + timedelta(minutes=60)
                ),
            ),
        )
        assert order.actual_minutes == 120

    def test_waiting_is_subtracted_before_it_can_reach_an_estimate(self) -> None:
        """Otherwise the estimate inflates every cycle until load_ratio reads the
        shift as permanently full (feedback_loops.md 3)."""
        order = _order(
            work_segments=(
                WorkSegment(
                    user=UserId("tech-a"), started_at=NOW, ended_at=NOW + timedelta(minutes=90)
                ),
            ),
            blocked_minutes=40,
            blocked_reason=(BlockedReason.WAITING_PARTS,),
        )
        assert order.actual_minutes == 90
        assert order.repair_minutes == 50

    def test_an_open_segment_contributes_nothing_yet(self) -> None:
        order = _order(work_segments=(WorkSegment(user=UserId("tech-a"), started_at=NOW),))
        assert order.actual_minutes == 0

    def test_repair_minutes_never_goes_negative(self) -> None:
        order = _order(
            work_segments=(
                WorkSegment(
                    user=UserId("tech-a"), started_at=NOW, ended_at=NOW + timedelta(minutes=10)
                ),
            ),
            blocked_minutes=30,
        )
        assert order.repair_minutes == 0

    def test_a_segment_cannot_end_before_it_starts(self) -> None:
        with pytest.raises(ValidationError, match="before it starts"):
            WorkSegment(user=UserId("tech-a"), started_at=NOW, ended_at=NOW - timedelta(minutes=1))


class TestWorkOrderOrigins:
    """ADR-010 and ADR-030: three sources, and the scheduler reads none of them
    through a reference."""

    def test_a_condition_order_must_name_its_finding(self) -> None:
        with pytest.raises(ValidationError, match="must reference the Finding"):
            _order(origin=WorkOrderOrigin.CONDITION)

    def test_a_scheduled_order_must_name_its_pm_task(self) -> None:
        with pytest.raises(ValidationError, match="must reference its PM task"):
            _order(origin=WorkOrderOrigin.SCHEDULED)

    def test_a_manual_order_needs_neither(self) -> None:
        """A supervisor reporting a fault has no Finding and no PM task, and must
        still be schedulable."""
        assert _order(origin=WorkOrderOrigin.MANUAL).finding_ref is None

    def test_scheduled_and_manual_orders_still_carry_severity(self) -> None:
        """The reason severity lives on the order rather than the Finding: the
        load gate admits "high severity only" and must be able to judge these
        two kinds of work at all (ADR-030)."""
        for origin, ref in (
            (WorkOrderOrigin.SCHEDULED, {"pm_task_ref": PMTaskRef("PM-1")}),
            (WorkOrderOrigin.MANUAL, {}),
        ):
            order = _order(origin=origin, severity=Severity.CRITICAL, **ref)
            assert order.severity.rank > Severity.MEDIUM.rank

    def test_the_scheduler_facing_facts_live_on_the_order(self) -> None:
        """dispatch/ may not import triggers/, so everything it scores on has to
        be here already (ADR-030)."""
        order = _order(
            origin=WorkOrderOrigin.CONDITION,
            finding_ref=FindingRef("F-1"),
            finding_kind=FindingKind.PREDICTED,
            eta=NOW + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
            playbook_ref=PlaybookRef("P-1"),
            playbook_snapshot=(_step(),),
        )
        assert order.machine_id and order.severity and order.eta
        assert order.playbook_snapshot[0].source_doc


class TestClosingAndHandover:
    def test_a_handover_without_a_note_is_rejected(self) -> None:
        """Otherwise the next shift starts again from step one (ADR-025)."""
        with pytest.raises(ValidationError, match="note saying how far"):
            _order(status=WorkOrderStatus.HANDED_OVER)

    def test_a_handover_with_a_note_is_accepted(self) -> None:
        order = _order(status=WorkOrderStatus.HANDED_OVER, handover_note="Done to step 4 of 7")
        assert order.handover_note

    def test_a_closed_order_must_say_how_it_ended(self) -> None:
        with pytest.raises(ValidationError, match="must record an outcome"):
            _order(status=WorkOrderStatus.CLOSED)

    def test_no_problem_found_is_a_valid_ending(self) -> None:
        """The only false-alarm signal the system will ever get. Loop 2 does not
        exist without it (feedback_loops.md 4)."""
        order = _order(status=WorkOrderStatus.CLOSED, outcome=WorkOutcome.NO_PROBLEM_FOUND)
        assert order.outcome is WorkOutcome.NO_PROBLEM_FOUND


def test_a_signal_looks_the_same_whatever_produced_it() -> None:
    """ADR-002: the rest of the system talks to this shape and nothing else."""
    signal = Signal(
        timestamp=NOW, machine_id=MOTOR, metric_name="temp_c", value=92.0, unit="celsius"
    )
    assert signal.model_dump() == {
        "timestamp": NOW,
        "machine_id": "MC-012",
        "metric_name": "temp_c",
        "value": 92.0,
        "unit": "celsius",
    }


class TestWhatTheSchedulerNeedsToPriceAJob:
    """ADR-041: the four facts layer 3 computes with, on the order itself.

    `load_ratio` is the sum of estimated_minutes x required_technicians over the
    shift's capacity (design.md 13.2), and `dispatch()` may not read a table to
    find them (invariant 10). Held here for the same reason machine_id and
    severity are (ADR-030).
    """

    def test_an_order_that_cannot_be_priced_cannot_be_created(self) -> None:
        with pytest.raises(ValidationError):
            WorkOrder(  # type: ignore[call-arg]
                origin=WorkOrderOrigin.MANUAL,
                machine_id=MOTOR,
                severity=Severity.HIGH,
                reason="reported by a technician",
            )

    def test_a_two_person_job_says_so(self) -> None:
        """ADR-025: counted as one, the shift reads as half as busy as it is."""
        order = _order(required_technicians=2)

        assert order.required_technicians == 2

    def test_a_job_with_no_playbook_may_have_no_skill(self) -> None:
        """None is "any technician", and it is the honest answer.

        Guessing robot_mechanical for an electrical fault sends the wrong
        person, and the guess is worse than the absence because the absence is
        visible.
        """
        order = _order(required_skill=None, estimate_is_fallback=True)

        assert order.required_skill is None

    def test_a_fallback_estimate_cannot_claim_a_playbook(self) -> None:
        """Both at once says two things, and one of them was written by
        something that was not paying attention."""
        with pytest.raises(ValidationError, match="takes its estimate from that playbook"):
            _order(estimate_is_fallback=True, playbook_ref=PlaybookRef("SYM-014/R-2000iC"))

    def test_an_order_always_says_why_it_exists(self) -> None:
        with pytest.raises(ValidationError):
            _order(reason="")

    def test_the_reason_for_existing_and_the_reason_for_the_ranking_are_separate(self) -> None:
        """One field would answer whichever question was asked last: layer 3
        overwrites priority_reason on the first tick (ADR-005, ADR-041)."""
        order = _order(
            reason="motor temperature 91 C, over the 85 C threshold for 20 minutes",
            priority_reason="first of four: this station has no buffer",
        )

        assert "20 minutes" in order.reason
        assert "no buffer" in order.priority_reason

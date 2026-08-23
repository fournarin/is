"""Loop 1 against orders of known duration (ADR-006, ADR-022, ADR-066).

The interesting tests here are the refusals. A loop that always has something to
say is a loop nobody reads: below the observation floor it proposes nothing, an
estimate the evidence agrees with is not a proposal, and a job that closed with
no repair time recorded is not evidence of how long the repair takes.

The arithmetic is checked against durations written out by hand rather than
against the module's own output, because a test that agrees with the code proves
only that the code is consistent with itself - and this is the number the
scheduler prices every shift with.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pdm.contracts import (
    FindingRef,
    MachineId,
    MachineModel,
    RuleId,
    Severity,
    SymptomCode,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderRef,
    WorkOrderStatus,
    WorkOutcome,
    WorkSegment,
)
from pdm.work.estimates import ClosedJob, EstimateProposal, propose

NOW = datetime(2026, 4, 1, 8, 0, tzinfo=UTC)
SYM = SymptomCode("SYM-014")
R2000IC = MachineModel("R-2000iC")
RULE = RuleId("R-motor-temp-high")

# The two constants of ADR-066, repeated here rather than read from policy.yaml:
# a test that takes its expectations from the file it is checking moves whenever
# the file does, and stops being able to say the file changed.
FLOOR = 5
CAP = 0.20


def _order(
    *,
    worked_minutes: int,
    blocked_minutes: int = 0,
    outcome: WorkOutcome = WorkOutcome.FIXED,
) -> WorkOrder:
    """A closed order with one segment of a known length.

    Built through the contract rather than as a bare object, so `repair_minutes`
    is the same property the technician's close-out writes and not a second
    definition of it (ADR-025).
    """
    segments: tuple[WorkSegment, ...] = ()
    if worked_minutes > 0:
        segments = (
            WorkSegment(
                user=UserId("tech-1"),
                started_at=NOW,
                ended_at=NOW + timedelta(minutes=worked_minutes),
            ),
        )
    return WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=FindingRef("F-000001"),
        machine_id=MachineId("MC-001"),
        severity=Severity.HIGH,
        estimated_minutes=50,
        reason="over threshold for 20 minutes",
        status=WorkOrderStatus.CLOSED,
        work_segments=segments,
        blocked_minutes=blocked_minutes,
        outcome=outcome,
    )


def _job(
    ref: str,
    *,
    worked_minutes: int,
    blocked_minutes: int = 0,
    outcome: WorkOutcome = WorkOutcome.FIXED,
    rule_id: RuleId | None = RULE,
) -> ClosedJob:
    return ClosedJob.from_order(
        WorkOrderRef(ref),
        _order(
            worked_minutes=worked_minutes,
            blocked_minutes=blocked_minutes,
            outcome=outcome,
        ),
        rule_id=rule_id,
    )


def _propose(
    jobs: list[ClosedJob], *, current_minutes: int, floor: int = FLOOR
) -> EstimateProposal | None:
    return propose(
        jobs,
        symptom_code=SYM,
        machine_model=R2000IC,
        current_minutes=current_minutes,
        min_observations=floor,
        max_change_ratio=CAP,
    )


class TestWhatTheEvidenceSays:
    def test_the_proposal_is_the_middle_of_the_repair_times(self) -> None:
        """The median, not the mean.

        One job left open across a shift and closed the next morning is worth
        eighteen hours to the mean and one observation to the median, and the
        first would reprice every job for that symptom from a single row.
        """
        jobs = [
            _job("WO-000001", worked_minutes=52),
            _job("WO-000002", worked_minutes=54),
            _job("WO-000003", worked_minutes=56),
            _job("WO-000004", worked_minutes=58),
            _job("WO-000005", worked_minutes=60),
        ]

        proposal = _propose(jobs, current_minutes=50)

        assert proposal is not None
        assert proposal.median_minutes == 56
        assert proposal.proposed_minutes == 56
        assert proposal.capped is False

    def test_one_absurd_job_does_not_reprice_the_symptom(self) -> None:
        jobs = [
            _job("WO-000001", worked_minutes=52),
            _job("WO-000002", worked_minutes=54),
            _job("WO-000003", worked_minutes=56),
            _job("WO-000004", worked_minutes=58),
            _job("WO-000005", worked_minutes=18 * 60),
        ]

        proposal = _propose(jobs, current_minutes=50)

        assert proposal is not None
        assert proposal.median_minutes == 56
        assert proposal.longest_minutes == 18 * 60

    def test_blocked_minutes_are_removed_before_the_estimate_is_formed(self) -> None:
        """Waiting for a part is not repair time (ADR-006, ADR-025).

        Left in, the estimate inflates every cycle: a longer estimate makes
        `load_ratio` read the shift as fuller, the gate holds back work, and the
        jobs that do run are the ones that waited longest for parts.
        """
        jobs = [
            _job("WO-000001", worked_minutes=90, blocked_minutes=40),
            _job("WO-000002", worked_minutes=90, blocked_minutes=40),
            _job("WO-000003", worked_minutes=90, blocked_minutes=40),
            _job("WO-000004", worked_minutes=90, blocked_minutes=40),
            _job("WO-000005", worked_minutes=90, blocked_minutes=40),
        ]

        proposal = _propose(jobs, current_minutes=45)

        assert proposal is not None
        # 90 worked minus 40 waiting is 50, not 90. The cap allows 54.
        assert proposal.median_minutes == 50
        assert proposal.proposed_minutes == 50

    def test_an_estimate_the_evidence_agrees_with_is_not_a_proposal(self) -> None:
        jobs = [_job(f"WO-00000{n}", worked_minutes=45) for n in range(1, 6)]

        assert _propose(jobs, current_minutes=45) is None


class TestWhatIsNotEvidence:
    def test_below_the_observation_floor_nothing_is_proposed(self) -> None:
        jobs = [_job(f"WO-00000{n}", worked_minutes=60) for n in range(1, FLOOR)]

        assert _propose(jobs, current_minutes=45) is None

    def test_no_problem_found_is_excluded_from_the_estimate_and_counted(self) -> None:
        """A false alarm says nothing about how long the repair takes.

        It is counted rather than dropped: it is the only false-alarm signal this
        system will ever receive, and the loop that tunes rule thresholds has no
        other input (ADR-022).
        """
        jobs = [_job(f"WO-00000{n}", worked_minutes=56) for n in range(1, 6)]
        jobs += [
            _job("WO-000006", worked_minutes=5, outcome=WorkOutcome.NO_PROBLEM_FOUND),
            _job("WO-000007", worked_minutes=5, outcome=WorkOutcome.NO_PROBLEM_FOUND),
        ]

        proposal = _propose(jobs, current_minutes=50)

        assert proposal is not None
        assert proposal.observations == 5
        assert proposal.no_problem_found == 2
        assert proposal.median_minutes == 56

    def test_false_alarms_do_not_make_up_the_observation_floor(self) -> None:
        jobs = [_job(f"WO-00000{n}", worked_minutes=56) for n in range(1, FLOOR)]
        jobs += [
            _job("WO-000009", worked_minutes=5, outcome=WorkOutcome.NO_PROBLEM_FOUND),
            _job("WO-000010", worked_minutes=5, outcome=WorkOutcome.NO_PROBLEM_FOUND),
        ]

        assert _propose(jobs, current_minutes=50) is None

    def test_a_job_that_recorded_no_repair_time_is_not_evidence(self) -> None:
        """Closed with nothing worked - or with the whole of it spent waiting.

        Zero minutes is not a fast repair; it is an order nobody recorded segments
        against. Counted in with the rest it drags the middle down, and the
        estimate then prices a job at less than anybody has ever taken to do it.
        """
        jobs = [_job(f"WO-00000{n}", worked_minutes=56) for n in range(1, 6)]
        jobs += [
            _job("WO-000006", worked_minutes=0),
            _job("WO-000007", worked_minutes=30, blocked_minutes=30),
        ]

        proposal = _propose(jobs, current_minutes=50)

        assert proposal is not None
        assert proposal.observations == 5
        assert proposal.without_repair_time == 2
        assert proposal.median_minutes == 56


class TestTheCap:
    def test_a_proposal_may_not_move_the_estimate_further_than_the_cap_upwards(self) -> None:
        """ADR-022's bound on movement per cycle, applied to the proposal.

        The estimate feeds `load_ratio`, `load_ratio` decides which work is
        released, and which work is released decides which durations come back -
        so a loop free to move the estimate as far as one week's evidence says can
        oscillate. The cap is what stops that.
        """
        jobs = [_job(f"WO-00000{n}", worked_minutes=120) for n in range(1, 6)]

        proposal = _propose(jobs, current_minutes=45)

        assert proposal is not None
        assert proposal.median_minutes == 120
        assert proposal.proposed_minutes == 54  # 45 + 20%
        assert proposal.capped is True
        assert "120" in proposal.reason and "54" in proposal.reason

    def test_a_proposal_may_not_move_the_estimate_further_than_the_cap_downwards(self) -> None:
        jobs = [_job(f"WO-00000{n}", worked_minutes=10) for n in range(1, 6)]

        proposal = _propose(jobs, current_minutes=45)

        assert proposal is not None
        assert proposal.proposed_minutes == 36  # 45 - 20%
        assert proposal.capped is True

    def test_the_proposal_carries_what_a_reviewer_needs_to_check_it(self) -> None:
        """ADR-022: a proposal a person cannot check is one they can only believe."""
        jobs = [
            _job("WO-000001", worked_minutes=40),
            _job("WO-000002", worked_minutes=50),
            _job("WO-000003", worked_minutes=56),
            _job("WO-000004", worked_minutes=70),
            _job("WO-000005", worked_minutes=90),
        ]

        proposal = _propose(jobs, current_minutes=50)

        assert proposal is not None
        assert proposal.symptom_code == SYM
        assert proposal.machine_model == R2000IC
        assert proposal.current_minutes == 50
        assert proposal.observations == 5
        assert proposal.shortest_minutes == 40
        assert proposal.longest_minutes == 90
        assert proposal.evidence == (
            WorkOrderRef("WO-000001"),
            WorkOrderRef("WO-000002"),
            WorkOrderRef("WO-000003"),
            WorkOrderRef("WO-000004"),
            WorkOrderRef("WO-000005"),
        )

    def test_the_floor_and_the_cap_are_not_defaults_in_the_code(self) -> None:
        """Both come from policy.yaml, and neither has a value here to fall back on.

        A default in the signature is a number with no provenance that nothing
        reports: the file could be missing the block entirely and every call would
        still return something (ADR-066).
        """
        jobs = [_job(f"WO-00000{n}", worked_minutes=56) for n in range(1, 6)]

        with pytest.raises(TypeError):
            propose(  # type: ignore[call-arg]
                jobs,
                symptom_code=SYM,
                machine_model=R2000IC,
                current_minutes=50,
            )


class TestNothingHereWrites:
    def test_only_the_approval_path_writes_a_playbook(self) -> None:
        """ADR-022 and invariant 3, as a property of the tree rather than a habit.

        `estimated_minutes` on an approved playbook is what the scheduler prices
        every shift with, and this loop exists to change it. The one thing that
        must stay true is that it changes nothing by itself: the write lives in
        the approval path, which refuses anything not approved by a person.
        """
        writers = set()
        for path in Path("src/pdm").rglob("*.py"):
            source = path.read_text()
            if "INSERT INTO playbook (" in source or "UPDATE playbook\n" in source:
                writers.add(path.relative_to(Path("src")))

        assert writers == {Path("pdm/playbooks/repo.py")}

    def test_the_estimate_loop_holds_no_sql_at_all(self) -> None:
        source = Path("src/pdm/work/estimates.py").read_text()

        assert "INSERT" not in source
        assert "UPDATE" not in source

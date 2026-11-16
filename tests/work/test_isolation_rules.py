"""The isolation rules, without a database (ADR-135, REQ-H-03 to REQ-H-06).

What a marked step needs before the job moves past it, in OSHA 1910.147's order,
and what an answer about locks may say given the register. These are the rules a
plausible screen could get wrong in a way that hurts somebody, so each is pinned
here rather than only through the API.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from pdm.contracts import (
    DocumentId,
    IsolationPoint,
    LockState,
    MachineId,
    PlaybookStep,
    StepKind,
    UserId,
)
from pdm.work.locks import (
    Confirmation,
    Lock,
    first_unfinished,
    lock_line,
    lock_state_refused,
    missing_verify,
    still_needed,
)

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
DOC = DocumentId("a" * 64)
ME, OTHER = UserId("tech-1"), UserId("tech-2")
CP3 = IsolationPoint(point_id="CP-3", label="breaker CP-3", energy="electrical")
V7 = IsolationPoint(point_id="V-7", label="air valve V-7", energy="pneumatic")


def step(kind: StepKind = StepKind.NORMAL, **marks: object) -> PlaybookStep:
    return PlaybookStep(text="do it", source_doc=DOC, page=2, confidence=0.9, kind=kind, **marks)  # type: ignore[arg-type]


def done(number: int, point: str, item: str, at: datetime = NOW) -> Confirmation:
    return Confirmation(step=number, point_id=point, item=item, confirmed_by=ME, confirmed_at=at)


def lock(owner: UserId = ME, point: str = "CP-3", number: str = "ก-03") -> Lock:
    return Lock(
        lock_id=1,
        work_order_ref="WO-1",
        machine_id=MachineId("MC-012"),
        point_id=point,
        lock_no=number,
        owner=owner,
        step=2,
        applied_at=NOW,
    )


class TestTheMarksAreTheEngineers:
    def test_an_isolation_step_must_name_its_points(self) -> None:
        with pytest.raises(ValidationError, match="must name the points"):
            step(StepKind.ISOLATION)

    def test_a_normal_step_names_none(self) -> None:
        with pytest.raises(ValidationError, match="only isolation"):
            step(isolation_points=(CP3,))

    def test_a_hazard_code_is_an_iso_7010_code(self) -> None:
        with pytest.raises(ValidationError):
            step(StepKind.HAZARD, hazards=("hot",))
        assert step(StepKind.HAZARD, hazards=("W017",)).hazards == ("W017",)


class TestWhatAStepStillNeeds:
    def test_isolation_is_off_then_locked_point_by_point(self) -> None:
        two = step(StepKind.ISOLATION, isolation_points=(CP3, V7))
        assert still_needed(two, 2, [], now=NOW) == [
            ("CP-3", "off"),
            ("CP-3", "locked"),
            ("V-7", "off"),
            ("V-7", "locked"),
        ]
        assert still_needed(two, 2, [done(2, "CP-3", "off")], now=NOW)[0] == ("CP-3", "locked")

    def test_a_confirmation_on_another_step_does_not_count(self) -> None:
        one = step(StepKind.VERIFY, isolation_points=(CP3,))
        assert still_needed(one, 3, [done(2, "CP-3", "verified")], now=NOW) == [
            ("CP-3", "verified")
        ]

    def test_a_wait_counts_from_when_the_step_was_reached(self) -> None:
        hot = step(StepKind.HAZARD, hazards=("W017",), wait_minutes=30)
        started = [done(3, "", "wait_started")]
        assert still_needed(hot, 3, started, now=NOW + timedelta(minutes=29))
        assert still_needed(hot, 3, started, now=NOW + timedelta(minutes=30)) == []
        assert still_needed(hot, 3, [], now=NOW + timedelta(hours=5)), "a clock never started"

    def test_the_job_cannot_skip_past_an_unfinished_isolation(self) -> None:
        steps = [step(), step(StepKind.ISOLATION, isolation_points=(CP3,)), step(), step()]
        assert first_unfinished(steps, [], before=2, now=NOW) is None
        assert first_unfinished(steps, [], before=4, now=NOW) == (
            2,
            [("CP-3", "off"), ("CP-3", "locked")],
        )
        locked = [done(2, "CP-3", "off"), done(2, "CP-3", "locked")]
        assert first_unfinished(steps, locked, before=4, now=NOW) is None


class TestIsolationIsVerified:
    def test_isolation_without_a_verify_after_it_is_flagged(self) -> None:
        isolate = step(StepKind.ISOLATION, isolation_points=(CP3,))
        verify = step(StepKind.VERIFY, isolation_points=(CP3,))
        assert missing_verify([isolate, step()])
        assert missing_verify([verify, isolate])
        assert not missing_verify([isolate, verify, step()])
        assert not missing_verify([step(), step()])


class TestTheAnswerAboutLocksAgreesWithTheRegister:
    def test_my_locks_still_on_refuse_released_and_no_answer(self) -> None:
        mine = [lock()]
        assert "ก-03" in str(lock_state_refused(LockState.RELEASED, mine=mine, on_this_job=mine))
        assert lock_state_refused(None, mine=mine, on_this_job=mine) is not None
        assert lock_state_refused(LockState.STILL_LOCKED, mine=mine, on_this_job=mine) is None

    def test_not_isolated_is_refused_while_anybodys_lock_is_on(self) -> None:
        theirs = [lock(owner=OTHER)]
        assert lock_state_refused(LockState.NOT_ISOLATED, mine=[], on_this_job=theirs) is not None
        assert lock_state_refused(LockState.RELEASED, mine=[], on_this_job=theirs) is None

    def test_still_locked_needs_a_lock_to_be_on(self) -> None:
        assert lock_state_refused(LockState.STILL_LOCKED, mine=[], on_this_job=[]) is not None
        assert lock_state_refused(None, mine=[], on_this_job=[]) is None

    def test_the_answer_goes_on_top_of_the_note_with_the_reason(self) -> None:
        line = lock_line(LockState.STILL_LOCKED, "รออะไหล่", [lock()])
        assert line == "สถานะกุญแจ: ยังล็อกอยู่ ก-03 ที่ CP-3 · เหตุ: รออะไหล่"
        assert lock_line(None, None, []) is None

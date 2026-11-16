"""The isolation rules, without a database (ADR-135, ADR-136, REQ-H-03 to REQ-H-06).

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
from pdm.playbooks.domain import energy_problems, uncovered
from pdm.work.locks import (
    Confirmation,
    Lock,
    first_unfinished,
    lock_line,
    lock_state_refused,
    still_needed,
)

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
DOC = DocumentId("a" * 64)
ME, OTHER = UserId("tech-1"), UserId("tech-2")
CP3 = IsolationPoint(point_id="CP-3", label="breaker CP-3", energy="electrical")
V7 = IsolationPoint(point_id="V-7", label="air valve V-7", energy="pneumatic")


def step(kind: StepKind = StepKind.NORMAL, **marks: object) -> PlaybookStep:
    return PlaybookStep(text="do it", source_doc=DOC, page=2, confidence=0.9, kind=kind, **marks)  # type: ignore[arg-type]


def done(number: int, point: str, item: str, at: datetime = NOW, by: UserId = ME) -> Confirmation:
    return Confirmation(step=number, point_id=point, item=item, confirmed_by=by, confirmed_at=at)


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


ISOLATE = step(StepKind.ISOLATION, isolation_points=(CP3,))
RESTORE = step(StepKind.RESTORE, isolation_points=(CP3,))
CHECKS = ("tools_removed", "people_clear")


def needs(
    one: PlaybookStep, number: int, done_: list[Confirmation], **kw: object
) -> list[tuple[str, str]]:
    kw.setdefault("now", NOW)
    kw.setdefault("user", ME)
    kw.setdefault("locks_on", [])
    return still_needed(one, number, done_, **kw)  # type: ignore[arg-type]


class TestWhatAStepStillNeeds:
    def test_isolation_is_off_then_your_own_lock_point_by_point(self) -> None:
        two = step(StepKind.ISOLATION, isolation_points=(CP3, V7))
        assert needs(two, 2, []) == [
            ("CP-3", "off"),
            ("CP-3", "locked"),
            ("V-7", "off"),
            ("V-7", "locked"),
        ]
        assert needs(two, 2, [done(2, "CP-3", "off")])[0] == ("CP-3", "locked")

    def test_the_lock_has_to_be_on_now_not_once(self) -> None:
        """B1: a 'locked' statement followed by the lock coming off is not a lock."""
        said = [done(2, "CP-3", "off"), done(2, "CP-3", "locked")]
        assert needs(ISOLATE, 2, said, locks_on=[]) == [("CP-3", "locked")]
        assert needs(ISOLATE, 2, said, locks_on=[lock()]) == []

    def test_everybody_who_works_past_it_hangs_their_own_lock(self) -> None:
        """B4, group lockout: my lock does not cover you; switching off is done once."""
        mine_on = [lock(owner=ME)]
        said = [done(2, "CP-3", "off")]
        assert needs(ISOLATE, 2, said, user=OTHER, locks_on=mine_on) == [("CP-3", "locked")]
        assert (
            needs(ISOLATE, 2, said, user=OTHER, locks_on=[*mine_on, lock(OTHER, number="ก-09")])
            == []
        )

    def test_verify_is_your_own(self) -> None:
        verify = step(StepKind.VERIFY, isolation_points=(CP3,))
        assert needs(verify, 4, [done(4, "CP-3", "verified", by=OTHER)]) == [("CP-3", "verified")]
        assert needs(verify, 4, [done(4, "CP-3", "verified")]) == []

    def test_restore_checks_come_before_the_locks_come_off(self) -> None:
        """B5: tools out, people clear - then the locks."""
        assert needs(RESTORE, 7, [], locks_on=[lock()], checks=CHECKS) == [
            ("tools_removed", "checked"),
            ("people_clear", "checked"),
            ("CP-3", "released"),
        ]

    def test_restore_waits_for_every_lock_on_its_points_whoever_owns_it(self) -> None:
        checked = [done(7, key, "checked") for key in CHECKS]
        assert needs(RESTORE, 7, checked, locks_on=[lock(OTHER)], checks=CHECKS) == [
            ("CP-3", "released")
        ]
        assert needs(RESTORE, 7, checked, locks_on=[], checks=CHECKS) == []

    def test_a_wait_counts_from_when_the_step_was_reached(self) -> None:
        hot = step(StepKind.HAZARD, hazards=("W017",), wait_minutes=30)
        started = [done(3, "", "wait_started")]
        assert needs(hot, 3, started, now=NOW + timedelta(minutes=29))
        assert needs(hot, 3, started, now=NOW + timedelta(minutes=30)) == []
        assert needs(hot, 3, [], now=NOW + timedelta(hours=5)), "a clock never started"

    def test_the_job_cannot_skip_past_an_isolation_without_your_lock_on(self) -> None:
        steps = [step(), ISOLATE, step(), step()]
        said = [done(2, "CP-3", "off"), done(2, "CP-3", "locked")]
        assert first_unfinished(steps, [], before=2, now=NOW, user=ME, locks_on=[]) is None
        assert first_unfinished(steps, said, before=4, now=NOW, user=ME, locks_on=[]) == (
            2,
            [("CP-3", "locked")],
        )
        assert first_unfinished(steps, said, before=4, now=NOW, user=ME, locks_on=[lock()]) is None

    def test_past_the_restore_step_the_lock_is_no_longer_asked_for(self) -> None:
        steps = [ISOLATE, RESTORE, step()]
        said = [done(1, "CP-3", "off"), done(1, "CP-3", "locked"), done(2, "CP-3", "released")]
        assert first_unfinished(steps, said, before=3, now=NOW, user=ME, locks_on=[]) is None


class TestIsolationIsVerifiedAndRestoredAtApproval:
    def test_every_isolated_point_is_verified_after_it(self) -> None:
        tp = IsolationPoint(point_id="TP-1", label="test point", energy="electrical")
        verify_cp3 = step(StepKind.VERIFY, isolation_points=(CP3,))
        assert uncovered([ISOLATE, step()]) == ["CP-3"]
        assert uncovered([ISOLATE, step(StepKind.VERIFY, isolation_points=(tp,))]) == ["CP-3"]
        assert uncovered([ISOLATE, verify_cp3]) == []

    def test_a_restore_step_that_also_runs_the_machine_is_refused(self) -> None:
        combined = PlaybookStep(
            text="Refit the guard, remove locks, and run the axis for 20 minutes.",
            source_doc=DOC,
            page=4,
            confidence=0.9,
            kind=StepKind.RESTORE,
            isolation_points=(CP3,),
        )
        verify = step(StepKind.VERIFY, isolation_points=(CP3,))
        problems = energy_problems([ISOLATE, verify, combined])
        assert any("เดินเครื่องในขั้นเดียว" in one for one in problems)
        assert energy_problems([ISOLATE, verify, RESTORE]) == []
        assert any("ไม่มีขั้นคืนพลังงาน" in one for one in energy_problems([ISOLATE, verify]))


class TestTheAnswerAboutLocksAgreesWithTheRegister:
    def refused(self, answer: LockState | None, **kw: object) -> str | None:
        kw.setdefault("on_job", [])
        kw.setdefault("on_machine", kw["on_job"])
        kw.setdefault("you_locked_here", False)
        kw.setdefault("anybody_locked_here", bool(kw["on_job"]))
        return lock_state_refused(answer, **kw)  # type: ignore[arg-type]

    def test_no_answer_is_refused_while_anybodys_lock_is_on(self) -> None:
        """Red line 3: whoever took over does not close past the first person's lock."""
        assert self.refused(None, on_job=[lock(OTHER)]) is not None
        assert self.refused(None) is None

    def test_released_is_refused_while_any_lock_is_on_the_machine(self) -> None:
        """B2: another person's lock, or another job's lock on the same machine."""
        assert self.refused(LockState.RELEASED, on_job=[lock(OTHER)], you_locked_here=True)
        other_job = [lock(OTHER)]
        assert self.refused(
            LockState.RELEASED, on_job=[], on_machine=other_job, you_locked_here=True
        )
        assert self.refused(LockState.RELEASED, you_locked_here=False), "never locked here"
        assert (
            self.refused(LockState.RELEASED, you_locked_here=True, anybody_locked_here=True) is None
        )

    def test_not_isolated_is_refused_where_anybody_locked(self) -> None:
        assert self.refused(LockState.NOT_ISOLATED, on_job=[lock()])
        assert self.refused(LockState.NOT_ISOLATED, anybody_locked_here=True), "even after release"
        assert self.refused(LockState.NOT_ISOLATED) is None

    def test_still_locked_needs_a_lock_to_be_on(self) -> None:
        assert self.refused(LockState.STILL_LOCKED) is not None
        assert self.refused(LockState.STILL_LOCKED, on_job=[lock()]) is None

    def test_the_answer_goes_on_top_of_the_note_with_the_reason(self) -> None:
        line = lock_line(LockState.STILL_LOCKED, "รออะไหล่", [lock()])
        assert line == "สถานะกุญแจ: ยังล็อกอยู่ ก-03 ที่ CP-3 · เหตุ: รออะไหล่"
        assert lock_line(None, None, []) is None


class TestRoundThree:
    """ADR-137: the holes the second EHS review found."""

    def refused(self, answer: LockState | None, **kw: object) -> str | None:
        kw.setdefault("on_job", [])
        kw.setdefault("on_machine", kw["on_job"])
        kw.setdefault("you_locked_here", True)
        kw.setdefault("anybody_locked_here", True)
        return lock_state_refused(answer, **kw)  # type: ignore[arg-type]

    def test_released_needs_the_restore_checks(self) -> None:
        """N1: a lock off without the restore step skipped tools, guards, people, operator."""
        assert self.refused(LockState.RELEASED, restore_checked=False)
        assert self.refused(LockState.RELEASED, restore_checked=True) is None

    def test_another_jobs_lock_has_its_own_answer(self) -> None:
        """N3: mine are off, the machine is still locked by another job."""
        theirs = [lock(OTHER)]
        assert self.refused(LockState.RELEASED, on_machine=theirs)
        assert self.refused(LockState.RELEASED_MACHINE_LOCKED, on_machine=theirs) is None
        assert self.refused(LockState.RELEASED_MACHINE_LOCKED, on_machine=[])
        line = lock_line(LockState.RELEASED_MACHINE_LOCKED, None, [], theirs)
        assert line is not None and "tech-2 ที่ CP-3" in line

    def test_no_answer_where_anybody_locked(self) -> None:
        assert self.refused(None)
        assert self.refused(None, anybody_locked_here=False) is None

    def test_a_restore_step_with_two_points_finishes(self) -> None:
        """N4: inside the restore step its own points no longer need the isolation lock."""
        v7 = IsolationPoint(point_id="V-7", label="valve", energy="pneumatic")
        isolate = step(StepKind.ISOLATION, isolation_points=(CP3, v7))
        restore = step(StepKind.RESTORE, isolation_points=(CP3, v7))
        said = [done(1, p, item) for p in ("CP-3", "V-7") for item in ("off", "locked")]
        only_v7_on = [lock(point="V-7", number="ก-04")]
        steps = [isolate, restore]
        blocked = first_unfinished(steps, said, before=2, now=NOW, user=ME, locks_on=only_v7_on)
        assert blocked is not None, "outside the restore step the lock is still asked for"
        assert (
            first_unfinished(
                steps,
                said,
                before=2,
                now=NOW,
                user=ME,
                locks_on=only_v7_on,
                restoring=frozenset({"CP-3", "V-7"}),
            )
            is None
        )

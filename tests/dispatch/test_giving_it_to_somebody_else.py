"""The shift lead confirms a proposal to somebody else (ADR-132).

Trial run 5: a handover note said an electrician was needed, the round proposed
somebody with no particular skill, and the lead could only confirm or set the
job aside. These are the pure halves of the fix: who the job may go to, what the
crew becomes, and how the agreement measure counts it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pdm.contracts import Assignee, AssigneeRole, Role, SkillId, Technician, UserId
from pdm.dispatch.agreement import agreement
from pdm.dispatch.proposals import Proposal, ProposalState, crew_with, why_not

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
WICHAI = UserId("tech-wichai")
PIMCHANOK = UserId("tech-pimchanok")
SOMCHAI = UserId("tech-somchai")
ELECTRICAL = SkillId("electrical")


def _primary(user: UserId) -> Assignee:
    return Assignee(user=user, role=AssigneeRole.PRIMARY)


def _helper(user: UserId) -> Assignee:
    return Assignee(user=user, role=AssigneeRole.HELPER)


class TestWhoMayTakeIt:
    def test_an_electrician_on_the_shift_may_take_an_electrical_job(self) -> None:
        pim = Technician(user=PIMCHANOK, skills=frozenset({ELECTRICAL}))

        assert (
            why_not(name="พิมพ์ชนก", technician=pim, rostered=True, required_skill=ELECTRICAL) is None
        )

    def test_somebody_without_the_skill_is_refused_by_name_and_skill(self) -> None:
        wichai = Technician(user=WICHAI, skills=frozenset())

        refusal = why_not(
            name="วิชัย",
            technician=wichai,
            rostered=True,
            required_skill=ELECTRICAL,
            skill_name="ช่างไฟฟ้า",
        )

        assert refusal is not None
        assert "วิชัย" in refusal and "ช่างไฟฟ้า" in refusal

    def test_somebody_not_on_this_shift_is_refused(self) -> None:
        pim = Technician(user=PIMCHANOK, skills=frozenset({ELECTRICAL}))

        refusal = why_not(name="พิมพ์ชนก", technician=pim, rostered=False, required_skill=None)

        assert refusal is not None and "ไม่ได้อยู่ในกะนี้" in refusal

    def test_an_inactive_or_unknown_person_is_refused(self) -> None:
        gone = Technician(user=PIMCHANOK, skills=frozenset({ELECTRICAL}), active=False)

        assert why_not(name="x", technician=gone, rostered=True, required_skill=None)
        assert why_not(name="x", technician=None, rostered=True, required_skill=None)

    def test_a_job_with_no_skill_may_go_to_anybody_on_the_shift(self) -> None:
        wichai = Technician(user=WICHAI, skills=frozenset())

        assert why_not(name="วิชัย", technician=wichai, rostered=True, required_skill=None) is None


class TestWhatTheCrewBecomes:
    def test_a_one_person_job_is_a_swap(self) -> None:
        assert crew_with((_primary(WICHAI),), PIMCHANOK) == (_primary(PIMCHANOK),)

    def test_a_crew_keeps_its_size_and_its_helper(self) -> None:
        crew = crew_with((_primary(WICHAI), _helper(SOMCHAI)), PIMCHANOK)

        assert crew == (_primary(PIMCHANOK), _helper(SOMCHAI))

    def test_promoting_the_helper_keeps_the_old_primary_on_the_crew(self) -> None:
        crew = crew_with((_primary(WICHAI), _helper(SOMCHAI)), SOMCHAI)

        assert crew == (_primary(SOMCHAI), _helper(WICHAI))


class TestTheAgreementMeasureStaysHonest:
    def _settled(self, ref: str, state: ProposalState) -> Proposal:
        return Proposal(
            work_order_ref=ref,
            proposed_at=NOW,
            assignees=(_primary(WICHAI),),
            priority_score=1.0,
            priority_reason="r",
            state=state,
            decided_at=NOW + timedelta(minutes=4),
            decided_by=UserId("sup-1"),
            decided_role=Role.SUPERVISOR,
            confirmed_assignees=(
                (_primary(PIMCHANOK),) if state is ProposalState.REASSIGNED else ()
            ),
        )

    def test_a_reassignment_is_answered_and_is_not_agreement(self) -> None:
        report = agreement(
            [
                self._settled("WO-1", ProposalState.CONFIRMED),
                self._settled("WO-2", ProposalState.REASSIGNED),
            ]
        )

        assert report.overall.reassigned == 1
        assert report.overall.answered == 2
        assert report.overall.confirmed_share == 0.5
        assert report.decision_time.answered == 2

    def test_both_crews_are_listed(self) -> None:
        report = agreement([self._settled("WO-2", ProposalState.REASSIGNED)])

        (one,) = report.reassignments
        assert one.proposed_to == (WICHAI,)
        assert one.given_to == (PIMCHANOK,)

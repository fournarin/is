"""The counterfactual, and the shift whose answer is arithmetic (ADR-055).

`plan.md`'s failure mode that matters most is a system nobody uses, and the way
an optimiser gets there is by being unable to say why. So the test that carries
this file is not that an explanation appears - it is that the number in it is the
one worked out before the code was: **335 units**, from the same two-job shift
the solver tests use.

The other three worth reading:

  * `TestAskingTwice::test_asking_the_same_question_twice_solves_once` is the
    whole of "lazily, then cached" - the property, not the intention.
  * `TestAConstraintDecided` holds the part of the issue a number cannot answer.
    "Nobody rostered on this shift holds electrical" is something a supervisor
    acts on within the hour; "it scored lower" is not.
  * `TestNothingIsGenerated::test_the_same_question_gives_the_same_sentence`
    is ADR-003 at this seam. A sentence assembled from solver output is
    identical every time; one that came from a model would not have to be.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from pdm.contracts import (
    FindingRef,
    MachineId,
    Severity,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrder,
    WorkOrderOrigin,
    WorkOrderStatus,
)
from pdm.dispatch import Explainer, Queued, Reason
from pdm.platform.config import load_config

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
CONFIG = load_config(Path("config"))

BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")

MORNING = ShiftId("morning")
MECHANICAL = SkillId("robot_mechanical")
ELECTRICAL = SkillId("electrical")

ANA = UserId("tech-ana")
BEN = UserId("tech-ben")


def _order(
    *,
    machine_id: MachineId = BUFFERED,
    severity: Severity = Severity.MEDIUM,
    minutes: int = 60,
    skill: SkillId | None = MECHANICAL,
    people: int = 1,
) -> WorkOrder:
    return WorkOrder(
        origin=WorkOrderOrigin.CONDITION,
        finding_ref=FindingRef(f"F-{machine_id}"),
        machine_id=machine_id,
        severity=severity,
        estimated_minutes=minutes,
        required_skill=skill,
        required_technicians=people,
        reason="because a test said so",
        status=WorkOrderStatus.QUEUED,
    )


def _queued(ref: str, order: WorkOrder) -> Queued:
    return Queued(ref=ref, order=order, created_at=NOW - timedelta(minutes=0))


def _explainer(
    queue: list[Queued],
    *,
    technicians: list[Technician],
    roster: list[tuple[UserId, int]],
) -> Explainer:
    return Explainer(
        queue,
        technicians=technicians,
        assignments=roster,
        config=CONFIG,
        now=NOW,
        shift_id=MORNING,
    )


# ── the shift whose counterfactual is known before the code runs ───────────
#
# The same two jobs the solver tests use. One technician, 300 minutes:
#
#   BIG   120 minutes at st-01  ->  (120 - 20) x 1 = 100 units,  0.833 per minute
#   FAST   30 minutes at st-03  ->   30 x 3        =  90 units,  3.000 per minute
#
# The plan is FAST at 0 and BIG at 30, costing 3.000 x 0 + 0.833 x 30 = 25.0.
#
# Force FAST to the end and the only remaining plan is BIG at 0, FAST at 120:
#   0.833 x 0 + 3.000 x 120 = 360.0.
#
# So moving FAST later starts it 120 minutes later and costs 360.0 - 25.0 = 335.
#
# Force BIG to the end and nothing moves - it was already last - so that one
# costs nothing, which is the other branch and just as much a fact about the
# plan as the first.


def _the_known_shift() -> tuple[list[Queued], list[Technician], list[tuple[UserId, int]]]:
    queue = [
        _queued("WO-BIG", _order(machine_id=BUFFERED, minutes=120)),
        _queued("WO-FAST", _order(machine_id=BOTTLENECK, minutes=30)),
    ]
    return queue, [Technician(user=ANA, skills=frozenset({MECHANICAL}))], [(ANA, 300)]


class TestTheCounterfactual:
    def test_the_cost_of_moving_it_later_is_the_one_computed_by_hand(self) -> None:
        """335 units and 120 minutes, from the arithmetic in the comment above."""
        queue, people, roster = _the_known_shift()
        answer = _explainer(queue, technicians=people, roster=roster).why("WO-FAST")

        assert answer.reason is Reason.MOVING_IT_LATER_COSTS
        assert answer.minutes_later == 120
        assert answer.units_lost_if_later is not None
        assert round(answer.units_lost_if_later) == 335

    def test_the_sentence_carries_the_number(self) -> None:
        """ADR-005 wants the answer where the job is, and a technician reads the
        sentence rather than the field beside it."""
        queue, people, roster = _the_known_shift()
        answer = _explainer(queue, technicians=people, roster=roster).why("WO-FAST")

        assert "ช้าลง 120 นาที" in answer.sentence
        assert "เสียราว 335 คัน" in answer.sentence

    def test_a_job_already_last_costs_nothing_to_move(self) -> None:
        """The other branch, and it has to exist: an explanation that always
        found a cost would be describing the question rather than the plan."""
        queue, people, roster = _the_known_shift()
        answer = _explainer(queue, technicians=people, roster=roster).why("WO-BIG")

        assert answer.reason is Reason.MOVING_IT_LATER_COSTS_NOTHING
        assert answer.minutes_later == 0
        assert answer.units_lost_if_later is not None
        assert answer.units_lost_if_later < 0.5
        assert not answer.a_constraint_decided

    def test_moving_it_later_does_not_mean_cancelling_what_was_before_it(self) -> None:
        """The subtlest thing in this file, and it was wrong first.

        "Start after everything else" can be satisfied by dropping everything
        else, and a solver minimising cost will happily do that: on this shift
        it answered 225 units and "0 minutes later", because it deleted the
        120-minute job rather than moving the 30-minute one behind it. Smaller
        number, confident sentence, wrong answer - which is the direction that
        makes an explanation reassuring rather than useful.

        So the counterfactual pins everything the plan scheduled. This asserts
        the consequence rather than the constraint: the job really does move to
        the end, behind the work that was in front of it.
        """
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        answer = explainer.why("WO-FAST")
        big = next(one for one in explainer.plan.placed if one.ref == "WO-BIG")

        assert big.starts_in_minutes == 30
        # 120 is where FAST lands once BIG is in front of it, which is only true
        # if BIG is still in the plan at all.
        assert answer.minutes_later == 120
        assert answer.units_lost_if_later is not None
        assert answer.units_lost_if_later > 300, "a dropped job would read far cheaper"

    def test_the_expensive_job_is_the_one_the_plan_put_first(self) -> None:
        """Ties the explanation to the plan it explains. If the counterfactual
        ever disagreed with the schedule about which job matters, one of the two
        would be measuring a different shift."""
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        first = explainer.plan.placed[0].ref
        costs = {
            ref: (explainer.why(ref).units_lost_if_later or 0.0) for ref in ("WO-BIG", "WO-FAST")
        }
        assert max(costs, key=lambda ref: costs[ref]) == first


class TestAskingTwice:
    def test_asking_the_same_question_twice_solves_once(self) -> None:
        """The issue's words. Re-solving for every ticket in every round is not
        affordable, and in practice few tickets get asked about."""
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        explainer.why("WO-FAST")
        after_one = explainer.solves
        explainer.why("WO-FAST")

        assert explainer.solves == after_one
        assert after_one == 2, "one solve for the plan, one for the counterfactual"

    def test_a_second_question_costs_a_second_solve(self) -> None:
        """Otherwise the test above would pass against a cache that never misses
        and an explainer that answers everything the same way."""
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        explainer.why("WO-FAST")
        before = explainer.solves
        explainer.why("WO-BIG")

        assert explainer.solves == before + 1

    def test_the_plan_is_solved_once_however_many_questions(self) -> None:
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        first = explainer.plan
        explainer.why("WO-FAST")
        explainer.why("WO-BIG")

        assert explainer.plan is first


class TestAConstraintDecided:
    def test_nobody_rostered_holds_the_skill(self) -> None:
        queue = [_queued("WO-ELEC", _order(skill=ELECTRICAL, minutes=30))]
        answer = _explainer(
            queue,
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            roster=[(ANA, 300)],
        ).why("WO-ELEC")

        assert answer.reason is Reason.NOBODY_HOLDS_THE_SKILL
        assert answer.a_constraint_decided
        assert "ช่างไฟฟ้า" in answer.sentence
        assert answer.units_lost_if_later is None

    def test_everybody_who_could_do_it_is_out_of_time(self) -> None:
        """A different sentence from the one above, because it is a different
        problem: one is a rostering decision and one is a capacity one."""
        queue = [_queued("WO-1", _order(minutes=60, severity=Severity.HIGH))]
        answer = _explainer(
            queue,
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            roster=[(ANA, 30)],
        ).why("WO-1")

        assert answer.reason is Reason.NOBODY_HAS_THE_TIME
        assert "60 นาที" in answer.sentence

    def test_a_two_person_job_with_one_person_free(self) -> None:
        queue = [_queued("WO-PAIR", _order(minutes=60, people=2))]
        answer = _explainer(
            queue,
            technicians=[
                Technician(user=ANA, skills=frozenset({MECHANICAL})),
                Technician(user=BEN, skills=frozenset({MECHANICAL})),
            ],
            roster=[(ANA, 300), (BEN, 10)],
        ).why("WO-PAIR")

        assert answer.reason is Reason.NOT_ENOUGH_PEOPLE
        assert "ช่างพร้อมกัน 2 คน" in answer.sentence

    def test_the_gate_answers_for_what_the_gate_held(self) -> None:
        """A job the gate held never reached the model, and the gate's own
        sentence is a better answer than anything a solver could add
        (ADR-011, ADR-054 §1)."""
        queue = [
            _queued("WO-HIGH", _order(severity=Severity.HIGH, minutes=60)),
            _queued("WO-LOW", _order(severity=Severity.LOW, minutes=60)),
            _queued("WO-MED", _order(severity=Severity.MEDIUM, minutes=60)),
        ]
        explainer = _explainer(
            queue,
            technicians=[Technician(user=ANA, skills=frozenset({MECHANICAL}))],
            roster=[(ANA, 180)],
        )
        answer = explainer.why("WO-LOW")

        assert explainer.plan.band.value == "heavy"
        assert answer.reason is Reason.HELD_BY_THE_GATE
        assert "ระบบกันงานนี้ไว้ก่อน" in answer.sentence
        assert "ความรุนแรงต่ำ" in answer.sentence


class TestTheQuestionsItRefuses:
    def test_a_reference_that_is_not_in_the_queue(self) -> None:
        queue, people, roster = _the_known_shift()
        answer = _explainer(queue, technicians=people, roster=roster).why("WO-NOWHERE")

        assert answer.reason is Reason.NOT_IN_QUEUE
        assert answer.units_lost_if_later is None

    def test_a_shift_with_nobody_on_it_says_there_is_no_plan(self) -> None:
        queue = [_queued("WO-1", _order())]
        answer = Explainer(
            queue,
            technicians=[],
            assignments=[],
            config=CONFIG,
            now=NOW,
            shift_id=MORNING,
        ).why("WO-1")

        assert answer.units_lost_if_later is None
        assert answer.sentence


class TestNothingIsGenerated:
    def test_the_same_question_gives_the_same_sentence(self) -> None:
        """ADR-003 at this seam. Assembled from solver output, so it is identical
        every time; a sentence from a model would not have to be."""
        queue, people, roster = _the_known_shift()
        once = _explainer(queue, technicians=people, roster=roster).why("WO-FAST")
        twice = _explainer(queue, technicians=people, roster=roster).why("WO-FAST")

        assert once == twice

    def test_every_answer_is_a_sentence_somebody_can_read(self) -> None:
        """Not a style check. An empty or half-built string is what a missing
        branch looks like from the outside, and it would reach a technician."""
        queue, people, roster = _the_known_shift()
        explainer = _explainer(queue, technicians=people, roster=roster)

        for ref in ("WO-BIG", "WO-FAST", "WO-NOWHERE"):
            sentence = explainer.why(ref).sentence
            assert len(sentence) > 20, sentence
            assert "{" not in sentence and "None" not in sentence, sentence

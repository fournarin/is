"""Why this job is where it is in the plan, worked out when somebody asks.

3C opens its terms for free: the score is a weighted sum and printing the five
terms costs nothing (ADR-045 §8). 3D cannot do that. The reason a job is third in
the plan lives inside a constraint model, and "the optimiser decided" is not an
answer - it is the sentence that makes a technician stop believing the system,
which `plan.md` treats as the failure that matters most, because a system nobody
uses has failed whatever its objective value.

So the answer is computed the only honest way available: **re-solve the same
shift with this job forced to the end, and report the difference.** That is
design.md 6.3, and it is a fact about the plan rather than a story about it.

Two things follow from the cost of doing that:

**It is lazy.** Re-solving for every ticket in every round is not affordable and
would mostly be wasted - in practice a handful of tickets get asked about. The
plan is solved once, each question is solved once, and both are cached.

**It is assembled, never generated.** ADR-003 keeps the LLM out of anything a
technician reads while standing at a machine, and that applies to the reason on
the ticket as much as to the steps. Every sentence here is built from solver
output and configuration by code in this file.

And one thing does not come from the objective at all. Where a *constraint*
decided - the only person with the skill is on another job, nobody has the
minutes left, the crew cannot be made - saying which constraint explains more
than any number would. A supervisor can act on "nobody rostered on this shift
holds hydraulics" within the hour; they cannot act on "it scored lower".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from pdm.contracts import ShiftId, Technician, UserId
from pdm.dispatch.domain import Queued, Round

# Same package, and deliberately the same model: a counterfactual built from a
# second construction of "the same" shift is the copy that stops being the same
# without saying so (ADR-055 section 1).
from pdm.dispatch.solver import _build, _Job, _Model, _plan_of, _run, _Shift, _shift, schedule
from pdm.platform.config.loader import Config


class Reason(StrEnum):
    """What decided this job's place, in the order the explainer checks them.

    The three that name a constraint come first on purpose: a job nobody can do
    is not a job that scored badly, and answering the second question when the
    first one applies sends somebody to argue about weights.
    """

    NOT_IN_QUEUE = "not_in_queue"
    HELD_BY_THE_GATE = "held_by_the_gate"
    NOBODY_HOLDS_THE_SKILL = "nobody_holds_the_skill"
    NOBODY_HAS_THE_TIME = "nobody_has_the_time"
    NOT_ENOUGH_PEOPLE = "not_enough_people"
    NO_ROOM_IN_THE_PLAN = "no_room_in_the_plan"
    MOVING_IT_LATER_COSTS = "moving_it_later_costs"
    MOVING_IT_LATER_COSTS_NOTHING = "moving_it_later_costs_nothing"


@dataclass(frozen=True)
class Answer:
    """One question about the plan, answered.

    `sentence` is what goes on a screen. The fields beside it are the same
    answer in numbers, for a caller that wants to lay it out differently - the
    same split ADR-045 §1 makes between `priority_reason` and `Terms`, and for
    the same reason: a sentence cannot be sorted and a number cannot be read.
    """

    ref: str
    reason: Reason
    sentence: str
    # How much more production the shift would lose with this job at the end of
    # the plan. None where a constraint decided, because there is no plan with
    # it in to compare against.
    units_lost_if_later: float | None = None
    # How much later it would start. None where forcing it late leaves it
    # undone, which `sentence` says in words instead.
    minutes_later: int | None = None

    @property
    def a_constraint_decided(self) -> bool:
        return self.reason in _CONSTRAINTS


_CONSTRAINTS = frozenset(
    {
        Reason.NOBODY_HOLDS_THE_SKILL,
        Reason.NOBODY_HAS_THE_TIME,
        Reason.NOT_ENOUGH_PEOPLE,
        Reason.NO_ROOM_IN_THE_PLAN,
    }
)


@dataclass
class Explainer:
    """One round, its plan, and the answers anybody asks for.

    Constructed from exactly the arguments `schedule()` takes, because it is the
    same round: the gate runs once, the plan is solved once, and a counterfactual
    is measured against that plan rather than against a second one built from a
    second reading of the same shift.

    Deliberately stateful, and the state is a memo. `solves` counts the times
    CP-SAT actually ran, so the caching is a property something can assert
    rather than a claim in a docstring.
    """

    queue: Sequence[Queued]
    technicians: Sequence[Technician]
    assignments: Sequence[tuple[UserId, int]]
    config: Config
    now: datetime
    shift_id: ShiftId | None = None
    on_date: date | None = None
    seconds: float | None = None

    solves: int = field(default=0, init=False)
    _plan: Round | None = field(default=None, init=False, repr=False)
    _answers: dict[str, Answer] = field(default_factory=dict, init=False, repr=False)
    _shift: _Shift = field(init=False, repr=False)
    _limit: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        self._shift = _shift(
            self.queue,
            technicians=self.technicians,
            assignments=self.assignments,
            config=self.config,
            now=self.now,
            shift_id=self.shift_id,
            on_date=self.on_date,
        )
        self._limit = (
            self.seconds if self.seconds is not None else self.config.policy.dispatch.solver_seconds
        )

    # ── the plan ───────────────────────────────────────────────────────────

    @property
    def plan(self) -> Round:
        """The round `schedule()` would return, solved at most once."""
        if self._plan is None:
            self._plan = self._solve_the_plan()
        return self._plan

    def _solve_the_plan(self) -> Round:
        self.solves += 1
        return schedule(
            self.queue,
            technicians=self.technicians,
            assignments=self.assignments,
            config=self.config,
            now=self.now,
            shift_id=self.shift_id,
            on_date=self.on_date,
            seconds=self.seconds,
        )

    # ── the questions ──────────────────────────────────────────────────────

    def why(self, ref: str) -> Answer:
        """Why this job is where it is. Asked twice, solved once."""
        if ref not in self._answers:
            self._answers[ref] = self._work_out(ref)
        return self._answers[ref]

    def _work_out(self, ref: str) -> Answer:
        if all(item.ref != ref for item in self.queue):
            return Answer(
                ref=ref,
                reason=Reason.NOT_IN_QUEUE,
                sentence="งานนี้ไม่ได้อยู่ในคิวของรอบนี้",
            )

        held = {one.ref: one.why for one in self.plan.held}
        if ref in held:
            # The gate already wrote a sentence a supervisor can act on, and it
            # is a better answer than anything the solver could add: the job
            # never reached the model (ADR-011, ADR-054 §1).
            return Answer(
                ref=ref,
                reason=Reason.HELD_BY_THE_GATE,
                sentence=f"ระบบกันงานนี้ไว้ก่อน: {held[ref]}",
            )

        shift = self._shift
        if shift.jobs is None:
            return Answer(
                ref=ref,
                reason=Reason.NO_ROOM_IN_THE_PLAN,
                sentence=(f"รอบนี้ยังไม่มีแผนให้เทียบ: {self.plan.summary or 'กะนี้ยังไม่มีอะไรให้จัด'}"),
            )

        built = _build(
            shift.jobs, available=shift.available, left=shift.left, horizon=shift.horizon
        )
        starts = {one.ref: one.starts_in_minutes for one in self.plan.placed}
        if ref not in starts:
            return self._constrained(ref, built)
        return self._counterfactual(ref, starts)

    # ── a constraint decided ───────────────────────────────────────────────

    def _constrained(self, ref: str, built: _Model) -> Answer:
        """Which constraint kept this out of the plan, in the words for it."""
        skilled = built.skilled.get(ref, ())
        with_time = built.with_time.get(ref, ())
        job = next(one for one in self._shift.jobs or [] if one.ref == ref)

        if not skilled:
            wanted = (
                self.config.wording().skill(job.required_skill)
                if job.required_skill
                else "ช่างที่ทำงานนี้ได้"
            )
            return Answer(
                ref=ref,
                reason=Reason.NOBODY_HOLDS_THE_SKILL,
                sentence=(f"กะนี้ไม่มี{wanted}ลงชื่ออยู่ จึงจัดงานนี้เข้าแผนไม่ได้"),
            )
        if not with_time:
            return Answer(
                ref=ref,
                reason=Reason.NOBODY_HAS_THE_TIME,
                sentence=(
                    f"{_people(len(skilled))}ทำงานนี้ได้ แต่ไม่มีใครเหลือเวลาถึง "
                    f"{job.minutes} นาทีที่งานนี้ต้องใช้ในกะนี้"
                ),
            )
        if len(with_time) < job.crew:
            return Answer(
                ref=ref,
                reason=Reason.NOT_ENOUGH_PEOPLE,
                sentence=(f"งานนี้ต้องใช้ช่างพร้อมกัน {job.crew} คน แต่กะนี้มีคนรับได้แค่ {len(with_time)} คน"),
            )
        return Answer(
            ref=ref,
            reason=Reason.NO_ROOM_IN_THE_PLAN,
            sentence=(
                f"{_people(len(with_time))}ทำงานนี้ได้ แต่กะนี้ใช้เวลากับงานอื่นได้คุ้มกว่า "
                "งานนี้จะได้คิวแรกในรอบถัดไป"
            ),
        )

    # ── the objective decided ──────────────────────────────────────────────

    def _counterfactual(self, ref: str, starts: dict[str, int | None]) -> Answer:
        """Re-solve with this job forced to the end, and report the difference.

        The difference is measured **between the two schedules, in units of
        production**, not between the two objective values. The objective
        carries a tie-break for orders the layout cannot price (ADR-054 §2), and
        an answer that quoted it would be reporting production plus something
        that is not production, in a sentence saying "units".
        """
        shift = self._shift
        assert shift.jobs is not None

        forced = _build(
            shift.jobs, available=shift.available, left=shift.left, horizon=shift.horizon
        )
        mine = forced.starts[ref]
        for other in shift.jobs:
            if other.ref == ref or other.ref not in starts:
                continue
            # Everything the plan scheduled stays scheduled, and this job starts
            # after all of it finishes.
            #
            # Pinning the others is not decoration. Without it, the cheapest way
            # to satisfy "start last" is to drop the jobs that would have gone
            # before: the model then answers a question nobody asked, and answers
            # it with a smaller number - the direction that makes an explanation
            # reassuring and wrong.
            forced.model.add(forced.present[other.ref] == 1)
            forced.model.add(mine >= forced.starts[other.ref] + other.minutes)

        self.solves += 1
        answer = _run(forced, seconds=self._limit, budget=self.config.policy.dispatch.solver_budget)
        if answer is None:
            return Answer(
                ref=ref,
                reason=Reason.MOVING_IT_LATER_COSTS_NOTHING,
                sentence=("คำนวณไม่ทันว่าถ้าเลื่อนงานนี้ออกไปจะเสียเท่าไร ลองกดใหม่อีกครั้ง"),
            )

        solver, status = answer
        later = _plan_of(forced, solver, status, shift.available)

        was = _production_cost(shift.jobs, starts, shift.horizon)
        would_be = _production_cost(shift.jobs, later.starts, shift.horizon)
        extra = would_be - was

        here = starts.get(ref)
        there = later.starts.get(ref)
        if there is None:
            return Answer(
                ref=ref,
                reason=Reason.MOVING_IT_LATER_COSTS,
                sentence=(
                    f"ถ้าเลื่อนงานนี้ไปท้ายแผน งานจะไม่เสร็จในกะนี้ และสายการผลิตจะเสียราว {extra:,.0f} คัน"
                ),
                units_lost_if_later=extra,
            )

        gap = there - (here or 0)
        if extra < 0.5:
            return Answer(
                ref=ref,
                reason=Reason.MOVING_IT_LATER_COSTS_NOTHING,
                sentence=(
                    "ไม่มีงานไหนในแผนรองานนี้อยู่ ถ้าเลื่อนไปท้ายแผน "
                    f"จะเริ่มช้าลง {gap} นาที โดยสายการผลิตแทบไม่เสียอะไร"
                ),
                units_lost_if_later=extra,
                minutes_later=gap,
            )
        return Answer(
            ref=ref,
            reason=Reason.MOVING_IT_LATER_COSTS,
            sentence=(
                f"ถ้าเลื่อนงานนี้ไปท้ายแผน จะเริ่มช้าลง {gap} นาที และสายการผลิตจะเสียราว {extra:,.0f} คัน"
            ),
            units_lost_if_later=extra,
            minutes_later=gap,
        )


def _production_cost(jobs: Sequence[_Job], starts: Mapping[str, int | None], horizon: int) -> float:
    """Production lost to delay under one schedule, in units.

    A job with no start in this schedule is not being done this shift, and is
    counted at the end of the horizon - the same convention the objective uses,
    for the same reason (ADR-054 §2).
    """
    total = 0.0
    for job in jobs:
        start = starts.get(job.ref)
        total += job.rate * (horizon if start is None else start)
    return total


def _people(count: int) -> str:
    return f"ช่างในกะนี้ {count} คน"

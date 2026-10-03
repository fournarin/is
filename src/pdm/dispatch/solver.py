"""3D: CP-SAT over the orders the gate admitted, and nothing wider.

`dispatch()` ranks a queue and hands out work greedily down the ranking. That is
a good answer computed one order at a time, and it is the wrong shape for the
question a shift actually asks: given these people, these skills and these
minutes, *what is the best plan for the rest of the shift*. Greedy cannot see
that starting a ninety-minute job now blocks two thirty-minute ones on the
machine that matters more.

**The gate is not part of the optimisation** (ADR-011, and the issue for this
slice says so twice). It runs first, unchanged, and decides how deep into the
queue this round reaches. Only what it admitted reaches the solver. Folding the
load term into the objective would produce weights nobody can explain to a shift
lead and would cost the one sentence ADR-011 exists to protect - "this shift is
at 92%, four non-urgent jobs are being held".

So this module calls `dispatch()` rather than reimplementing any of it. What it
replaces is one stage: ADR-045 §5's greedy assignment. Everything before that -
`load_ratio`, the band, admission in score order, the five normalised terms - is
the same code producing the same answer, which is also what makes the fallback
below honest: when the solver has nothing, the round returns what 3C decided,
not an error and not an empty plan.

Nothing here reads a clock or a connection. `now` is an argument, the solver's
seed and worker count are fixed, and every loop runs over a sorted sequence, so
the same inputs give the same schedule (invariant 10, ADR-054 §4).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ortools.sat.python import cp_model

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderOrigin,
)
from pdm.dispatch.domain import (
    Band,
    Placement,
    Queued,
    RawFacts,
    Round,
    Terms,
    Withheld,
    _Ranked,  # the ranking's row type, shared by the explainer
    capacity_left,
    dispatch,
    downtime_or_unknown,
    put_down_by,
    ranking,
)
from pdm.platform.config.loader import Config

# The objective is in integers, so the per-minute cost of delay is scaled before
# it is rounded. A thousandth of a unit of production per minute is far below
# anything a plant could act on, and the scale keeps the arithmetic exact.
_RATE_SCALE = 1000

# The tie-break's scale. A whole unit of production per minute of delay outranks
# any difference in the 3C score, which is what makes this a tie-break rather
# than a second objective competing with the first.
_SCORE_SCALE = 1


def schedule(
    queue: Sequence[Queued],
    *,
    technicians: Sequence[Technician],
    assignments: Sequence[tuple[UserId, int]],
    config: Config,
    now: datetime,
    shift_id: ShiftId | None = None,
    on_date: date | None = None,
    seconds: float | None = None,
) -> Round:
    """One scheduling round, planned rather than ranked.

    Same arguments as `dispatch()` and the same return type, deliberately: the
    comparison in `docs/results/` gains a column rather than a script, and any
    caller can swap one for the other without learning a second vocabulary.

    `seconds` overrides `policy.dispatch.solver_seconds` and exists for tests
    that need to force the timeout path. A round that hits the limit without a
    feasible schedule returns 3C's answer unchanged.
    """
    shift = _shift(
        queue,
        technicians=technicians,
        assignments=assignments,
        config=config,
        now=now,
        shift_id=shift_id,
        on_date=on_date,
    )
    if shift.jobs is None:
        return shift.ranked

    built = _build(shift.jobs, available=shift.available, left=shift.left, horizon=shift.horizon)
    _start_from(built, shift.ranked)
    answer = _run(
        built,
        seconds=seconds if seconds is not None else config.policy.dispatch.solver_seconds,
        budget=config.policy.dispatch.solver_budget,
    )
    if answer is None:
        # No feasible schedule inside the limit. The issue for this slice names
        # this case explicitly: fall back to 3C rather than returning nothing.
        # A round that answers "no plan" leaves a shift with a queue nobody is
        # working, which is strictly worse than a good-enough ranking.
        return shift.ranked

    solver, status = answer
    plan = _plan_of(built, solver, status, shift.available)
    return _round_from(plan, ranked=shift.ranked, admitted=shift.admitted, ranks=shift.ranks)


@dataclass(frozen=True)
class _Shift:
    """Everything one round needs, resolved once.

    `schedule()` and `Explainer` both start here, so a counterfactual is
    computed against the same admitted set, the same capacity and the same
    ranking the plan was built from. Two resolutions of "the same" shift is the
    copy that stops being the same without saying so (ADR-055 §1).

    `jobs` is None when there is nothing to solve - no capacity, nothing
    admitted, or nobody available - and `ranked` is then the whole answer.
    """

    ranked: Round
    admitted: list[Queued]
    available: list[Technician]
    left: dict[UserId, int]
    ranks: dict[str, _Ranked]
    horizon: int
    jobs: list[_Job] | None


def _shift(
    queue: Sequence[Queued],
    *,
    technicians: Sequence[Technician],
    assignments: Sequence[tuple[UserId, int]],
    config: Config,
    now: datetime,
    shift_id: ShiftId | None,
    on_date: date | None,
) -> _Shift:
    """Run the gate, then work out what a solver would be given."""
    ranked = dispatch(
        queue,
        technicians=technicians,
        assignments=assignments,
        config=config,
        now=now,
        shift_id=shift_id,
        on_date=on_date,
    )
    # The same ranking `dispatch()` computed, including for the orders it
    # admitted and could not crew. Those are the ones the solver may place by
    # moving something else, and their tickets need the same explanation as
    # everybody else's.
    ranks = ranking(
        queue,
        technicians=technicians,
        assignments=assignments,
        config=config,
        now=now,
    )
    admitted = _admitted(ranked, queue)

    rostered = {user for user, _ in assignments}
    available = sorted(
        (person for person in technicians if person.active and person.user in rostered),
        key=lambda person: person.user,
    )
    left = capacity_left(available, dict(assignments), queue) if available else {}
    horizon = max(left.values(), default=0)

    nothing = ranked.band is Band.NO_CAPACITY or not admitted or not available or horizon <= 0
    return _Shift(
        ranked=ranked,
        admitted=admitted,
        available=available,
        left=left,
        ranks=ranks,
        horizon=horizon,
        jobs=(
            None
            if nothing
            else [
                _job(item, ranks[item.ref][1] if item.ref in ranks else 0.0, config)
                for item in admitted
            ]
        ),
    )


@dataclass(frozen=True)
class _Job:
    """One admitted order, reduced to what the model needs.

    `rate` is the production lost for each minute this job is delayed - the
    per-minute form of ADR-021's downtime cost, and the only thing in the
    objective. `score` is 3C's ranking of the same order, used to break ties and
    for nothing else.
    """

    ref: str
    minutes: int
    crew: int
    required_skill: SkillId | None
    rate: float
    score: float
    # Who put this job down after a handover; the solver does not hand it back
    # to them (ADR-126), as greedy does not.
    excluded: frozenset[UserId] = frozenset()


def _job(item: Queued, score: float, config: Config) -> _Job:
    cost = downtime_or_unknown(item.order, config)
    minutes = item.order.estimated_minutes
    # An order whose machine the layout cannot price (ADR-048) gets a rate of
    # zero, which makes the solver indifferent about when it runs rather than
    # eager to run it last. "We cannot speak for this machine" is not "this
    # machine costs nothing", and that is why the 3C score breaks the tie below
    # instead of the objective deciding by omission.
    rate = 0.0 if cost is None or minutes <= 0 else cost / minutes
    # A scheduled job's machine runs while it waits: delaying it loses nothing,
    # whatever doing it costs (ADR-127). Its place comes from the score alone.
    if item.order.origin is WorkOrderOrigin.SCHEDULED:
        rate = 0.0
    return _Job(
        ref=item.ref,
        minutes=minutes,
        crew=item.order.required_technicians,
        required_skill=item.order.required_skill,
        rate=rate,
        score=score,
        excluded=put_down_by(item.order),
    )


def _admitted(ranked: Round, queue: Sequence[Queued]) -> list[Queued]:
    """What the gate let through, in the order it ranked them.

    Placed and unassigned together: both were admitted, and the second group is
    only there because greedy could find nobody free. Those are exactly the
    orders a solver might place by moving something else, so leaving them out
    would hand CP-SAT the problem greedy had already solved.
    """
    admitted = [one.ref for one in ranked.placed] + [one.ref for one in ranked.unassigned]
    by_ref = {item.ref: item for item in queue}
    return [by_ref[ref] for ref in admitted if ref in by_ref]


@dataclass(frozen=True)
class _Plan:
    """What the solver decided: who does what, when it starts, and what it cost."""

    starts: dict[str, int]
    crews: dict[str, tuple[UserId, ...]]
    status: str


@dataclass
class _Model:
    """The model and the handles needed to read an answer out of it.

    Kept as a value rather than built twice, because `explain.py` re-solves the
    same shift with one order forced late, and a second construction of "the
    same" model is the kind of copy that stops being the same without saying so.
    """

    model: cp_model.CpModel
    jobs: list[_Job]
    horizon: int
    starts: dict[str, cp_model.IntVar]
    present: dict[str, cp_model.IntVar]
    effective: dict[str, cp_model.IntVar]
    doing: dict[tuple[str, UserId], cp_model.IntVar]
    # Who holds the skill at all, and who holds it *and* has the minutes. The
    # two are separate because they are different sentences to a supervisor:
    # "nobody on this shift can do it" is a rostering problem and "everybody who
    # can is out of time" is a capacity one (ADR-055 §3).
    skilled: dict[str, tuple[UserId, ...]]
    with_time: dict[str, tuple[UserId, ...]]


def _build(
    jobs: list[_Job], *, available: Sequence[Technician], left: dict[UserId, int], horizon: int
) -> _Model:
    """The model of ADR-054 §2, with nothing solved yet."""
    model = cp_model.CpModel()
    starts: dict[str, cp_model.IntVar] = {}
    present: dict[str, cp_model.IntVar] = {}
    effective: dict[str, cp_model.IntVar] = {}
    doing: dict[tuple[str, UserId], cp_model.IntVar] = {}
    skilled: dict[str, tuple[UserId, ...]] = {}
    with_time: dict[str, tuple[UserId, ...]] = {}
    intervals: dict[UserId, list[cp_model.IntervalVar]] = {person.user: [] for person in available}

    for job in jobs:
        start = model.new_int_var(0, horizon, f"start[{job.ref}]")
        here = model.new_bool_var(f"present[{job.ref}]")
        starts[job.ref] = start
        present[job.ref] = here

        # An order that is not scheduled this shift is treated as delayed to the
        # end of the horizon. That needs no penalty constant: "not doing it costs
        # you the whole shift's delay" is the same currency as every other term
        # in the objective, and a made-up big-M would not be (workflow.md 4.1).
        eff = model.new_int_var(0, horizon, f"effective[{job.ref}]")
        model.add(eff == start).only_enforce_if(here)
        model.add(eff == horizon).only_enforce_if(~here)
        effective[job.ref] = eff

        # Skill is a hard constraint, not a preference (ADR-027): a technician
        # who does not hold it cannot do the job, and the w3 term of the 3C score
        # is about who is *free*, which is a different question.
        can = [
            person
            for person in available
            if (job.required_skill is None or person.can_perform(job.required_skill))
            and person.user not in job.excluded
        ]
        skilled[job.ref] = tuple(person.user for person in can)

        chosen = []
        fits = []
        for person in can:
            if left[person.user] < job.minutes:
                # This person cannot fit the job in what is left of their shift
                # at all, so the variable would only ever be zero.
                continue
            fits.append(person.user)
            picked = model.new_bool_var(f"doing[{job.ref},{person.user}]")
            doing[(job.ref, person.user)] = picked
            chosen.append(picked)
            intervals[person.user].append(
                model.new_optional_interval_var(
                    start, job.minutes, start + job.minutes, picked, f"iv[{job.ref},{person.user}]"
                )
            )
            # Finish inside the minutes this person has left. This is the
            # person-minute capacity the issue asks for, in its stronger form:
            # a budget alone would allow a job to be planned into time the shift
            # does not reach.
            model.add(start + job.minutes <= left[person.user]).only_enforce_if(picked)
        with_time[job.ref] = tuple(fits)

        # `required_technicians` people or none at all (ADR-025). Half a
        # two-person job cannot be started and would spend one person's shift
        # achieving nothing.
        if len(chosen) < job.crew:
            model.add(here == 0)
        else:
            model.add(sum(chosen) == job.crew * here)

    for person in available:
        if intervals[person.user]:
            # Nobody is under two machines at once (ADR-047).
            model.add_no_overlap(intervals[person.user])

    model.minimize(sum(_weight(job) * effective[job.ref] for job in jobs))

    return _Model(
        model=model,
        jobs=jobs,
        horizon=horizon,
        starts=starts,
        present=present,
        effective=effective,
        doing=doing,
        skilled=skilled,
        with_time=with_time,
    )


def _weight(job: _Job) -> int:
    """The objective's coefficient for one job, in scaled integers."""
    return round(job.rate * _RATE_SCALE) + round(job.score * _SCORE_SCALE)


def _run(
    built: _Model, *, seconds: float, budget: float | None = None
) -> tuple[cp_model.CpSolver, str] | None:
    """Solve, deterministically. None means no feasible answer inside the limit.

    `budget` is CP-SAT's deterministic time (ADR-110): the same budget gives the
    same plan on every machine, which a wall-clock limit did not - one of 1,440
    comparison runs came back different on a faster machine. `seconds` stays as
    a cap that should not bind.
    """
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    if budget is not None:
        solver.parameters.max_deterministic_time = budget
    # One worker and a fixed seed. CP-SAT's portfolio is parallel and the first
    # worker to prove optimality wins, so several of them make the *solution*
    # depend on how the machine was loaded that afternoon - which would make
    # every figure in `docs/results/` unreproducible, and quietly (ADR-054 §4).
    solver.parameters.num_workers = 1
    solver.parameters.random_seed = 0
    status = solver.solve(built.model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return solver, str(solver.status_name(status))


def _start_from(built: _Model, ranked: Round) -> None:
    """Hand the solver 3C's round as its first solution (ADR-110).

    `dispatch()` has already assigned the admitted orders to people, in rank
    order, and never beyond anybody's minutes. Laid end to end per person that is
    a complete schedule, so CP-SAT starts from the greedy plan and can only move
    to a better one. Without it, the solver spent its whole budget and on long
    queues returned plans several times worse than the one greedy had already
    found (ADR-107).

    An order 3C admitted and could not crew is hinted absent. A hint the model
    rejects is not an error: CP-SAT repairs or drops it and searches as before.
    """
    cursor: dict[UserId, int] = {}
    crews = {one.ref: tuple(assignee.user for assignee in one.assignees) for one in ranked.placed}
    by_ref = {job.ref: job for job in built.jobs}
    for placement in ranked.placed:
        job = by_ref.get(placement.ref)
        crew = crews[placement.ref]
        if job is None or any((job.ref, user) not in built.doing for user in crew):
            continue
        start = max((cursor.get(user, 0) for user in crew), default=0)
        for user in crew:
            cursor[user] = start + job.minutes
        built.model.add_hint(built.starts[job.ref], start)
        built.model.add_hint(built.present[job.ref], 1)
        built.model.add_hint(built.effective[job.ref], start)
        for (ref, user), variable in built.doing.items():
            if ref == job.ref:
                built.model.add_hint(variable, 1 if user in crew else 0)
    for job in built.jobs:
        if job.ref not in crews:
            built.model.add_hint(built.present[job.ref], 0)
            built.model.add_hint(built.effective[job.ref], built.horizon)
            for (ref, _), variable in built.doing.items():
                if ref == job.ref:
                    built.model.add_hint(variable, 0)


def _plan_of(
    built: _Model,
    solver: cp_model.CpSolver,
    status: str,
    available: Sequence[Technician],
) -> _Plan:
    scheduled = [job for job in built.jobs if solver.boolean_value(built.present[job.ref])]
    return _Plan(
        starts={job.ref: int(solver.value(built.starts[job.ref])) for job in scheduled},
        crews={
            job.ref: tuple(
                sorted(
                    person.user
                    for person in available
                    if (job.ref, person.user) in built.doing
                    and solver.boolean_value(built.doing[(job.ref, person.user)])
                )
            )
            for job in scheduled
        },
        status=status,
    )


def _solve(
    admitted: Sequence[Queued],
    *,
    available: Sequence[Technician],
    left: dict[UserId, int],
    scores: dict[str, float],
    config: Config,
    seconds: float,
) -> _Plan | None:
    """Build the model and solve it. None means no feasible schedule was found."""
    horizon = max(left.values(), default=0)
    if horizon <= 0:
        return None
    built = _build(
        [_job(item, scores.get(item.ref, 0.0), config) for item in admitted],
        available=available,
        left=left,
        horizon=horizon,
    )
    answer = _run(built, seconds=seconds)
    if answer is None:
        return None
    solver, status = answer
    return _plan_of(built, solver, status, available)


def _round_from(
    plan: _Plan,
    *,
    ranked: Round,
    admitted: Sequence[Queued],
    ranks: dict[str, tuple[Queued, float, Terms, RawFacts]],
) -> Round:
    """Dress the solver's answer in the same `Round` the rest of the system reads.

    The five terms and the raw facts come from 3C's ranking of the same order,
    because they are the answer to "why this job" and the solver did not compute
    a better one - it answered "when". `priority_reason` carries both.
    """
    reasons = {one.ref: one.priority_reason for one in ranked.placed}
    placed: list[Placement] = []
    unassigned: list[Withheld] = []

    for item in admitted:
        ref = item.ref
        if ref not in plan.starts:
            unassigned.append(
                Withheld(
                    ref=ref,
                    why=("แผนของกะนี้ไม่มีช่องว่างพอก่อนหมดกะ งานนี้จะได้คิวแรกในรอบถัดไป"),
                )
            )
            continue

        start = plan.starts[ref]
        crew = plan.crews[ref]
        _, score, terms, facts = ranks[ref]
        # Why this job at all is the score's answer and it is unchanged; why it
        # is at this minute is the plan's, and it goes in front (ADR-005).
        because = reasons.get(ref, "ผ่านประตูภาระงานแล้ว แต่ยังไม่มีช่างว่างรับ")
        placed.append(
            Placement(
                ref=ref,
                assignees=tuple(
                    Assignee(
                        user=user,
                        role=AssigneeRole.PRIMARY if index == 0 else AssigneeRole.HELPER,
                    )
                    for index, user in enumerate(crew)
                ),
                priority_score=score,
                # In Thai, as everything a shift lead reads (ADR-093), and with
                # no minute in it: the sentence is frozen when proposed and read
                # for half an hour after (ADR-126). The minute is on the
                # placement as `starts_in_minutes`.
                priority_reason=(
                    f"แผนของกะให้ทำงานนี้ต่อจากงานที่ช่างถืออยู่ · {because}"
                    if start
                    else f"แผนของกะให้เริ่มงานนี้ทันที · {because}"
                ),
                terms=terms,
                facts=facts,
                starts_in_minutes=start,
            )
        )

    # Start time first, then the score, then the reference. Every one of the
    # three is needed: two jobs can start in the same minute on two people, and
    # two can tie on both.
    placed.sort(key=lambda one: (one.starts_in_minutes or 0, -one.priority_score, one.ref))

    return ranked.model_copy(
        update={
            "placed": tuple(placed),
            "unassigned": tuple(unassigned),
            # The solver's status (OPTIMAL, FEASIBLE) is for the log, not the
            # board; what the shift lead needs is whether anything is waiting.
            "summary": (
                f"{ranked.summary} · อีก {len(unassigned)} ใบรอรอบถัดไป เพราะกะนี้เวลาไม่พอ"
                if unassigned
                else ranked.summary
            ),
        }
    )

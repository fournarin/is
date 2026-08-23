"""Closed work orders for machines whose degradation the generator chose.

One machine's history is a stream of failures at a baseline rate, plus - for the
machines the plan degrades - a second stream at a higher rate inside a window.
Both are drawn as exponential gaps, which is the memoryless process a wear-out
failure is usually modelled as and is what makes "twice the rate" mean twice as
many in a window rather than a fixed extra count.

The answer key is the degradation windows themselves. It is written into the plan
rather than recovered from the output, so a test can hold the generator to it and
a measurement can score a ranking against it (ADR-072 section 5, ADR-076
section 6).

Reproducibility works exactly as `SyntheticSource` does: every draw comes from a
generator seeded on the string `f"{seed}:{machine_id}:{stream}"`, hashed with
sha512 rather than the process-salted hash used for dict keys, so the same seed
gives the same history on any machine and adding a stream to one plan does not
shift another's.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts import (
    FindingRef,
    MachineId,
    PMTask,
    PMTaskRef,
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
from pdm.contracts.resources import PM_SYMPTOM_PREFIX
from pdm.health import ClosedRepair

_FROZEN = ConfigDict(frozen=True, extra="forbid")

_DAYS = 86_400.0

# Outcomes a real repair can close with, in the proportions the plan draws them.
# Invented, like everything else here, and they change nothing in the ranking:
# `ClosedRepair.is_failure` treats all three alike and separates only
# `no_problem_found`. They exist so the generated rows look like the rows this
# system writes rather than like one repeated record.
_REPAIR_OUTCOMES = (
    WorkOutcome.FIXED,
    WorkOutcome.FIXED,
    WorkOutcome.FIXED,
    WorkOutcome.TEMPORARY_FIX,
    WorkOutcome.NOT_FIXED,
)
_SEVERITIES = (Severity.MEDIUM, Severity.HIGH, Severity.HIGH, Severity.CRITICAL)

_TECHNICIAN = UserId("tech-history")


class DegradationEpisode(BaseModel):
    """One stretch during which the generator made a machine fail more often.

    `ends_at` of None means the machine was still degrading when the history
    stopped - the case a health reading is supposed to catch, because it is the
    only one where the failures are still coming.
    """

    model_config = _FROZEN

    machine_id: MachineId
    began_at: datetime
    ends_at: datetime | None = None
    # How much more often the machine failed inside the window, against its own
    # baseline. A multiplier rather than a rate, so the answer key says what was
    # done to the machine and not what the machine then was.
    multiplier: float = Field(gt=1.0)

    def covers(self, moment: datetime) -> bool:
        return self.began_at <= moment and (self.ends_at is None or moment < self.ends_at)

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> DegradationEpisode:
        if self.ends_at is not None and self.ends_at <= self.began_at:
            raise ValueError("a degradation episode cannot end before it began")
        return self


class MachinePlan(BaseModel):
    """One machine's invented behaviour over the span of the history."""

    model_config = _FROZEN

    machine_id: MachineId
    # Failures per hundred days when nothing is wrong beyond ordinary wear.
    baseline_per_100_days: float = Field(gt=0.0)
    # Of the orders raised against this machine, roughly this fraction close
    # `no_problem_found`. It is the noise ADR-076 section 3 refuses to rank on,
    # present so that refusal is exercised rather than assumed.
    false_alarm_rate: float = Field(default=0.0, ge=0.0, lt=1.0)
    # How often a PM task falls due, and how many of the most recent ones were
    # left undone at the end of the span.
    pm_interval_days: float = Field(default=30.0, gt=0.0)
    pm_skipped: int = Field(default=0, ge=0)
    degradation: DegradationEpisode | None = None

    @model_validator(mode="after")
    def _the_episode_is_this_machine(self) -> MachinePlan:
        if self.degradation is not None and self.degradation.machine_id != self.machine_id:
            raise ValueError(
                f"{self.machine_id}'s plan carries an episode for "
                f"{self.degradation.machine_id}: an answer key that names the wrong machine "
                f"would score every ranking against the wrong column"
            )
        return self


class HistoryPlan(BaseModel):
    """A whole plant's invented maintenance history, and what was done to it."""

    model_config = _FROZEN

    name: str
    starts_at: datetime
    ends_at: datetime
    machines: tuple[MachinePlan, ...]

    @property
    def span(self) -> timedelta:
        return self.ends_at - self.starts_at

    @property
    def answer_key(self) -> tuple[DegradationEpisode, ...]:
        """Which machines were degraded, and between which moments."""
        return tuple(
            machine.degradation for machine in self.machines if machine.degradation is not None
        )

    @property
    def degraded(self) -> frozenset[MachineId]:
        return frozenset(episode.machine_id for episode in self.answer_key)

    @property
    def machine_ids(self) -> tuple[MachineId, ...]:
        return tuple(machine.machine_id for machine in self.machines)

    @model_validator(mode="after")
    def _the_span_is_a_span(self) -> HistoryPlan:
        if self.ends_at <= self.starts_at:
            raise ValueError("a history has to end after it starts")
        for machine in self.machines:
            episode = machine.degradation
            if episode is None:
                continue
            if not (self.starts_at <= episode.began_at < self.ends_at):
                raise ValueError(
                    f"{machine.machine_id}'s degradation begins outside the history it is the "
                    f"answer key for"
                )
        return self


class SyntheticHistory:
    """One draw of a plan. Same plan and same seed, same history."""

    def __init__(self, plan: HistoryPlan, *, seed: int) -> None:
        self._plan = plan
        self._seed = seed

    @property
    def plan(self) -> HistoryPlan:
        return self._plan

    @property
    def answer_key(self) -> tuple[DegradationEpisode, ...]:
        return self._plan.answer_key

    def orders(self) -> tuple[tuple[WorkOrderRef, WorkOrder, datetime], ...]:
        """Every closed order, with the reference and close time the store holds.

        The close time is beside the order rather than on it because a
        `WorkOrder` does not carry one: it carries work segments, and the last
        segment's end is when somebody stopped working (ADR-025). Keeping the two
        apart here is what stops the generator inventing a field the contract
        does not have.
        """
        rows: list[tuple[WorkOrderRef, WorkOrder, datetime]] = []
        for machine in self._plan.machines:
            rows.extend(self._orders_for(machine))
        return tuple(sorted(rows, key=lambda row: (row[2], row[0])))

    def repairs(self) -> tuple[ClosedRepair, ...]:
        """The same orders, reduced to what a health reading may learn from."""
        return tuple(
            ClosedRepair.from_order(ref, order, closed_at=closed_at)
            for ref, order, closed_at in self.orders()
        )

    def pm_tasks(self) -> tuple[PMTask, ...]:
        """One PM task per machine, standing where the plan left it.

        A single task per machine rather than a backlog of them: `PMTask` is one
        recurring job with one due date (ADR-027), so "three were skipped" is one
        task overdue by three intervals, which is what the plan's `pm_skipped`
        means and what `pm_overdue_days` then reports.

        The cycle is anchored half an interval off the end of the history. A
        machine with nothing skipped is then due in half an interval rather than
        at the exact moment the history stops, which would make every machine in
        the plan read as one task overdue by zero days - true, useless, and the
        kind of thing a reader stops looking at.
        """
        tasks: list[PMTask] = []
        for machine in self._plan.machines:
            interval = timedelta(days=machine.pm_interval_days)
            due_at = self._plan.ends_at + interval * (0.5 - machine.pm_skipped)
            tasks.append(
                PMTask(
                    pm_task_ref=PMTaskRef(f"pm-{machine.machine_id}"),
                    machine_id=machine.machine_id,
                    symptom_code=SymptomCode(f"{PM_SYMPTOM_PREFIX}ROUTINE"),
                    interval=interval,
                    due_at=due_at,
                    last_done_at=due_at - interval,
                )
            )
        return tuple(tasks)

    # ── one machine ────────────────────────────────────────────────────────
    def _orders_for(self, machine: MachinePlan) -> list[tuple[WorkOrderRef, WorkOrder, datetime]]:
        faults = self._fault_times(machine)
        rng = self._stream(machine.machine_id, "orders")

        rows: list[tuple[WorkOrderRef, WorkOrder, datetime]] = []
        for index, moment in enumerate(faults):
            false_alarm = rng.random() < machine.false_alarm_rate
            outcome = WorkOutcome.NO_PROBLEM_FOUND if false_alarm else rng.choice(_REPAIR_OUTCOMES)
            severity = rng.choice(_SEVERITIES)
            minutes = rng.randrange(20, 120, 5)
            ref = WorkOrderRef(f"wo-{machine.machine_id}-{index:04d}")
            rows.append(
                (
                    ref,
                    self._condition_order(
                        machine.machine_id,
                        index=index,
                        raised_at=moment,
                        severity=severity,
                        outcome=outcome,
                        minutes=minutes,
                    ),
                    moment + timedelta(minutes=minutes),
                )
            )

        rows.extend(self._pm_orders(machine))
        return rows

    def _fault_times(self, machine: MachinePlan) -> list[datetime]:
        """Failure moments from a rate that changes partway through the span.

        Drawn by thinning: candidates come at the highest rate the machine ever
        runs at, and each is kept with probability rate(t) / peak. Drawing a gap
        at whatever the rate happened to be at the *previous* failure would be
        the obvious way and is wrong for exactly the case this fixture exists
        for - a machine failing once every hundred days draws a hundred-day gap
        and steps straight over a four-month episode, so the answer key would
        name machines whose history never shows it.
        """
        rng = self._stream(machine.machine_id, "faults")
        baseline = machine.baseline_per_100_days / 100.0
        episode = machine.degradation
        peak = baseline * (episode.multiplier if episode is not None else 1.0)

        moments: list[datetime] = []
        at = self._plan.starts_at
        while True:
            at = at + timedelta(days=rng.expovariate(peak))
            if at >= self._plan.ends_at:
                return moments
            rate = baseline * (
                episode.multiplier if episode is not None and episode.covers(at) else 1.0
            )
            if rng.random() <= rate / peak:
                moments.append(at)

    def _pm_orders(self, machine: MachinePlan) -> list[tuple[WorkOrderRef, WorkOrder, datetime]]:
        """The PM work that was done, which is not evidence of failure.

        Present so that the ranking has to ignore it. A machine with a diligent
        PM record has more closed orders than a neglected one, and a history
        contribution that counted closed orders would rank it as the sicker of
        the two.
        """
        interval = timedelta(days=machine.pm_interval_days)
        # The last one actually carried out, which is one interval before the
        # task became due - the same anchor `pm_tasks` uses, so the orders and
        # the standing task tell the same story.
        done_until = self._plan.ends_at + interval * (0.5 - machine.pm_skipped) - interval
        rows: list[tuple[WorkOrderRef, WorkOrder, datetime]] = []
        at = self._plan.starts_at + interval
        index = 0
        while at <= done_until:
            ref = WorkOrderRef(f"pm-{machine.machine_id}-{index:04d}")
            rows.append(
                (
                    ref,
                    WorkOrder(
                        origin=WorkOrderOrigin.SCHEDULED,
                        machine_id=machine.machine_id,
                        severity=Severity.LOW,
                        pm_task_ref=PMTaskRef(f"pm-{machine.machine_id}"),
                        estimated_minutes=45,
                        estimate_is_fallback=True,
                        reason="Routine maintenance fell due (synthetic history).",
                        status=WorkOrderStatus.CLOSED,
                        assignees=(),
                        work_segments=(
                            WorkSegment(
                                user=_TECHNICIAN,
                                started_at=at,
                                ended_at=at + timedelta(minutes=45),
                            ),
                        ),
                        outcome=WorkOutcome.FIXED,
                    ),
                    at + timedelta(minutes=45),
                )
            )
            at += interval
            index += 1
        return rows

    def _condition_order(
        self,
        machine_id: MachineId,
        *,
        index: int,
        raised_at: datetime,
        severity: Severity,
        outcome: WorkOutcome,
        minutes: int,
    ) -> WorkOrder:
        return WorkOrder(
            origin=WorkOrderOrigin.CONDITION,
            machine_id=machine_id,
            severity=severity,
            finding_ref=FindingRef(f"fnd-{machine_id}-{index:04d}"),
            estimated_minutes=minutes,
            estimate_is_fallback=True,
            reason=(
                f"A rule fired on {machine_id} and somebody was sent "
                f"(synthetic history, {raised_at.date().isoformat()})."
            ),
            status=WorkOrderStatus.CLOSED,
            work_segments=(
                WorkSegment(
                    user=_TECHNICIAN,
                    started_at=raised_at,
                    ended_at=raised_at + timedelta(minutes=minutes),
                ),
            ),
            outcome=outcome,
        )

    def _stream(self, machine_id: MachineId, name: str) -> random.Random:
        return random.Random(f"{self._seed}:{machine_id}:{name}")


# ── the committed plan ─────────────────────────────────────────────────────
# The four machines of `config/plant.yaml`, over a year ending at a fixed moment
# so that nothing here moves with the wall clock.
#
# Two of the four are degraded and two are not, which is the smallest set that
# makes "the top two" a claim rather than a coin toss. MC-012 is still degrading
# when the history stops - the case that matters, because those failures are
# still coming - and MC-018's episode ended four months before the end, which is
# the case that separates a rate from a recency: it should rank high on failures
# and low on "the last one was yesterday", and a reader should be able to see
# which of the two put it there.
#
# MC-004 carries the false alarms and MC-001 the skipped PM, so both of ADR-076
# section 3's refusals - neither may lift a machine up the order - are exercised
# by the committed plan rather than only by a hand-written test.
#
# Every number below is invented. There is no plant behind any of them.
_ENDS_AT = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
_STARTS_AT = _ENDS_AT - timedelta(days=365)

LINE_A_ONE_YEAR = HistoryPlan(
    name="line-a-one-year",
    starts_at=_STARTS_AT,
    ends_at=_ENDS_AT,
    machines=(
        MachinePlan(
            machine_id=MachineId("MC-001"),
            baseline_per_100_days=1.0,
            pm_interval_days=30.0,
            # Three intervals of PM left undone: the machine that looks neglected
            # and is not failing.
            pm_skipped=3,
        ),
        MachinePlan(
            machine_id=MachineId("MC-004"),
            baseline_per_100_days=1.0,
            # A rule that keeps sending somebody for nothing. ADR-073's problem,
            # and not a reason to rank this machine up.
            false_alarm_rate=0.6,
            pm_interval_days=30.0,
        ),
        MachinePlan(
            machine_id=MachineId("MC-012"),
            baseline_per_100_days=1.0,
            pm_interval_days=30.0,
            degradation=DegradationEpisode(
                machine_id=MachineId("MC-012"),
                began_at=_ENDS_AT - timedelta(days=120),
                ends_at=None,
                multiplier=6.0,
            ),
        ),
        MachinePlan(
            machine_id=MachineId("MC-018"),
            baseline_per_100_days=1.0,
            pm_interval_days=45.0,
            degradation=DegradationEpisode(
                machine_id=MachineId("MC-018"),
                began_at=_ENDS_AT - timedelta(days=300),
                ends_at=_ENDS_AT - timedelta(days=120),
                multiplier=6.0,
            ),
        ),
    ),
)

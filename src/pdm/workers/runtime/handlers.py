"""The trigger loop: signals in, tickets out, one tick at a time (ADR-044).

This is where layer 1 meets layer 2, and the only module in the system allowed to
know both. `triggers/` raises Findings and has never heard of a work order;
`work/` issues orders and has never heard of a signal. Joining them in a
composition root rather than in either one is what keeps the connectors of
design.md 3.3 real - layers 2 and 3 stay testable with no layer 1 present.

Everything happens on the job's connection, so a tick's Findings, the tickets
they produced, the tickets it withdrew and the appointment for the next round all
commit together or not at all (ADR-017). The handler neither finishes nor fails
its own job; the loop owns that.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.contracts import FindingRef, MachineId, RuleId, Signal, WorkOrderRef
from pdm.dispatch.service import DispatchRounds, describe
from pdm.platform.clock import Clock
from pdm.platform.config.loader import Config
from pdm.platform.jobs import Job, JobKind, JobQueue
from pdm.signals import Feed
from pdm.sinks import Deliveries
from pdm.sinks import describe as describe_deliveries
from pdm.triggers import Observation, Raised, Triggers
from pdm.work import NoEstimateAvailable, WorkOrders

log = logging.getLogger(__name__)


class Tick(BaseModel):
    """What one round did. Returned rather than logged, so a test can read it.

    The counts that are not tickets are the interesting half: a tick that
    suppressed forty firings and issued nothing is the alarm flood being held
    back, and a return value carrying only the tickets would make it look like a
    tick where nothing happened (ADR-023).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    signals: int = 0
    observation: Observation = Observation()
    issued: tuple[str, ...] = ()
    cancelled: tuple[str, ...] = ()
    expired: tuple[FindingRef, ...] = ()
    # Findings that were raised and could not be priced. They exist in the table
    # with no ticket behind them, which is a gap somebody has to close in
    # `policy.yaml` - not a reason to stop the loop.
    unpriced: tuple[FindingRef, ...] = ()
    # Machines the plant topology has never heard of. A live source will carry
    # tags for machines nobody has added to plant.yaml yet, and layer 1 must not
    # die on the first one.
    unknown_machines: tuple[MachineId, ...] = ()

    @property
    def worth_reporting(self) -> bool:
        return bool(
            self.observation.anything_happened
            or self.issued
            or self.cancelled
            or self.expired
            or self.unpriced
            or self.unknown_machines
        )


class TriggerLoop:
    """One feed, one rule engine, one way of issuing work.

    Holds no connection and no transaction. It holds the same in-process memory
    `Triggers` does - the debounce and the trend windows - which is why the
    process that runs the tick has to be the process that keeps running it
    (ADR-042 §1, ADR-044's first consequence).
    """

    def __init__(
        self,
        *,
        triggers: Triggers,
        orders: WorkOrders,
        config: Config,
        clock: Clock,
        feed: Feed | None = None,
    ) -> None:
        self.triggers = triggers
        self.orders = orders
        self.config = config
        self.clock = clock
        # None means no signal source was configured. The loop still runs: expiry
        # is housekeeping the queue needs whether or not new data arrives
        # (ADR-044 §5).
        self.feed = feed
        self.machines = frozenset(
            machine_id for station in config.stations.values() for machine_id in station.machine_ids
        )

    def tick(self, conn: Connection[Any]) -> Tick:
        """One round: read what is due, decide, write, withdraw what is stale.

        **Observation runs before expiry, and the order is a decision.** A
        prediction the data still supports has its ETA moved forward by the
        re-fit in `observe`, so expiry afterwards retires only the predictions
        nothing is refreshing. Expiring first would retire a prediction on the
        strength of an ETA that this very batch was about to correct.

        **Forecasts are ticketed before detections**, which is a second ordering
        with a second reason. One batch can hold both the trend and the crossing
        it predicted - certain after any stall, since the feed hands over its
        whole backlog - and `observe` will already have marked the prediction
        superseded. Ticketing the detection first would withdraw a ticket that
        did not exist yet, and the forecast's ticket, issued a moment later
        against a Finding that is already superseded, could never be withdrawn by
        anything: expiry only touches open and acknowledged records. Two open
        tickets for one fault, for ever, which is what ADR-023 §7 exists to stop.
        """
        signals, unknown = self._due()
        issued: list[str] = []
        cancelled: list[str] = []
        unpriced: list[FindingRef] = []
        observation = Observation()

        if signals:
            observation = self.triggers.observe(conn, signals, under_repair=self.under_repair(conn))
            for raised in (*observation.forecast, *observation.raised):
                self._issue(conn, raised, issued, cancelled, unpriced)

        expired = self.triggers.expire_stale_predictions(conn)
        for finding_ref in expired:
            cancelled.extend(self.orders.withdraw_for_finding(conn, finding_ref))

        return Tick(
            signals=len(signals),
            observation=observation,
            issued=tuple(issued),
            cancelled=tuple(cancelled),
            expired=tuple(expired),
            unpriced=tuple(unpriced),
            unknown_machines=unknown,
        )

    def _due(self) -> tuple[list[Signal], tuple[MachineId, ...]]:
        """What the feed hands over now, minus anything off the topology.

        A machine that is not in `plant.yaml` has no model, so no rule can be
        matched to it and no ticket can be priced for it. Invariant 13 guarantees
        every machine a *rule* names is on the map; it promises nothing about
        what a live connection will send.
        """
        if self.feed is None:
            return ([], ())
        arrived = self.feed.due(self.clock.now())
        known = [signal for signal in arrived if signal.machine_id in self.machines]
        if len(known) == len(arrived):
            return (known, ())
        unknown = tuple(
            sorted(
                {signal.machine_id for signal in arrived if signal.machine_id not in self.machines}
            )
        )
        return (known, unknown)

    def under_repair(self, conn: Connection[Any]) -> dict[MachineId, frozenset[RuleId]]:
        """Which (machine, rule) pairs somebody already has work open against.

        Read from the **tickets**, and the Findings behind them whatever state
        those are in. This was written the other way round first - the live
        Findings that had an open ticket - and it was dead code: a live Finding
        suppresses its own rule as a repeat (ADR-023 §2) before the repair check
        is ever reached, so the map could only ever contain pairs that were
        already handled.

        The case ADR-023 §4 is actually about is the one that derivation could
        not see. A technician resolves the Finding and then spends an hour
        repairing the machine; the cooldown covers thirty minutes of that, and
        for the rest of it the rule is free to raise a second Finding and a
        second ticket for the job somebody is standing inside the machine doing.

        Two queries and a join in Python, rather than one SQL join across two
        modules' tables: `work_order` belongs to layer 2 and `finding` to
        layer 1, and a statement naming both would be the coupling ADR-030 keeps
        out of the import graph, hidden in a string.
        """
        open_refs = self.orders.open_finding_refs(conn)
        if not open_refs:
            return {}
        pairs: dict[MachineId, set[RuleId]] = defaultdict(set)
        for machine_id, rule_id in self.triggers.rules_behind(conn, open_refs):
            pairs[machine_id].add(rule_id)
        return {machine_id: frozenset(rules) for machine_id, rules in pairs.items()}

    def _issue(
        self,
        conn: Connection[Any],
        raised: Raised,
        issued: list[str],
        cancelled: list[str],
        unpriced: list[FindingRef],
    ) -> None:
        """One Finding becomes one ticket, and withdraws what it supersedes.

        A Finding that cannot be priced is logged and skipped rather than raised.
        The whole tick is one transaction: letting `NoEstimateAvailable` out
        would roll back the Findings this batch raised, and the next tick would
        raise them again and fail again - one machine model missing from
        `fallback_minutes` would stop the pipeline for the whole plant, for ever.
        """
        finding = raised.decision.finding
        assert finding is not None  # RAISE and FORECAST always carry one
        try:
            order = self.orders.from_finding(
                conn,
                finding,
                finding_ref=raised.finding_ref,
                machine_model=self.config.model_of(finding.machine_id),
            )
        except NoEstimateAvailable:
            log.error(
                "finding %s on %s (%s) has no playbook and no fallback estimate: "
                "it is in the table with no ticket behind it",
                raised.finding_ref,
                finding.machine_id,
                finding.severity.value,
            )
            unpriced.append(raised.finding_ref)
            return

        issued.append(order.ref)
        if raised.superseded is not None:
            # The prediction came true. Its ticket describes a crossing that has
            # already happened, and this batch has just issued the one that says
            # so - which is the two-orders-for-one-fault case ADR-023 §7 exists
            # to prevent. A ticket somebody has accepted stays where it is.
            cancelled.extend(self.orders.withdraw_for_finding(conn, raised.superseded))


def observe_handler(loop: TriggerLoop, queue: JobQueue, clock: Clock, *, period: timedelta) -> Any:
    """Run one tick and book the next one, in the job's transaction (ADR-044 §1).

    The successor is enqueued here rather than inside `TriggerLoop`, because the
    schedule belongs to the queue and the loop belongs to layer 1: a tick that
    failed leaves no appointment, which is correct - the whole transaction rolls
    back - and is the case `ensure_tick_queued` exists to recover from.
    """

    def handle(conn: Connection[Any], job: Job) -> None:
        tick = loop.tick(conn)
        queue.enqueue(conn, kind=JobKind.OBSERVE, available_at=clock.now() + period)

        if tick.unknown_machines:
            log.warning(
                "signals arrived for machines that are not in plant.yaml: %s",
                ", ".join(tick.unknown_machines),
            )
        # Quiet ticks are the normal case - one every `period`, for ever - and a
        # line each would bury the ticks that did something.
        report = log.info if tick.worth_reporting else log.debug
        report(
            "tick: %s signals, %s raised, %s predicted, %s repeated, %s suppressed, "
            "%s in cooldown -> %s issued, %s cancelled, %s expired",
            tick.signals,
            len(tick.observation.raised),
            len(tick.observation.forecast),
            tick.observation.repeated,
            tick.observation.suppressed,
            tick.observation.in_cooldown,
            len(tick.issued),
            len(tick.cancelled),
            len(tick.expired),
        )

    return handle


def ensure_tick_queued(conn: Connection[Any], queue: JobQueue) -> Job | None:
    """Put the trigger tick back if the chain is gone (ADR-044 §3).

    Called at boot and on every empty poll. Idempotent through the same
    `pending` primitive ADR-040 built for the second press of a button: a tick
    that is queued, running, or waiting out a retry backoff counts as coming, so
    ordinary retries stay with the queue and only a chain that has actually
    stopped is restarted.
    """
    if queue.pending(conn, kind=JobKind.OBSERVE, payload={}) is not None:
        return None
    log.info("no trigger tick was pending; starting the chain")
    return queue.enqueue(conn, kind=JobKind.OBSERVE)


def dispatch_handler(
    rounds: DispatchRounds,
    queue: JobQueue,
    clock: Clock,
    *,
    period: timedelta,
    deliveries: Deliveries | None = None,
) -> Any:
    """Run one scheduling round, send what it placed, and book the next one.

    All three in the job's transaction. This is the composition root's half of
    ADR-068: layer 3 places the work, layer 4 takes it somewhere, and neither
    imports the other. A delivery that fails does not roll the round back - the
    placement stands and the record says the destination refused it - but a
    round that fails takes the queued deliveries with it, which is the direction
    that has to hold.

    **Layer 4 is handed `placed` and never `proposed`.** In `supervisor` mode a
    round decides and writes nothing anybody has agreed to, and `placed` is empty
    (ADR-071 §5); what leaves the system is queued by the confirmation instead,
    in the request a supervisor made. A ticket reaching a CMMS before anybody
    approved it is the one failure the confirmation step exists to prevent, and
    at this seam it would be one argument in one call.

    `deliveries` is optional so that a test asserting on scheduling alone need
    not stand up a destination. `None` means the tickets stay where the round
    put them, which is exactly the behaviour before layer 4 existed.

    The same shape as `observe_handler` and for the same reason (ADR-044 §1): a
    round that failed leaves no appointment, the whole transaction rolls back,
    and `ensure_round_queued` is what starts the chain again. Layer 3 does not
    know it is on a schedule, which is what keeps `dispatch()` replayable.

    Unlike layer 1's tick, this one runs whether or not anything arrived. The
    queue changes for reasons no event reaches - a shift starts, a technician's
    remaining minutes fall, a predicted crossing gets closer - so a round that
    only ran on an event would rank a shift by facts that had stopped being true.
    """

    def handle(conn: Connection[Any], job: Job) -> None:
        report = rounds.run(conn)
        queue.enqueue(conn, kind=JobKind.DISPATCH, available_at=clock.now() + period)

        report_at = log.info if report.worth_reporting else log.debug
        report_at("round: %s", describe(report))

        if deliveries is not None:
            sent = deliveries.run(conn, placed=[WorkOrderRef(ref) for ref in report.placed])
            sent_at = log.info if sent.worth_reporting else log.debug
            sent_at("delivery: %s", describe_deliveries(sent))

    return handle


def ensure_round_queued(conn: Connection[Any], queue: JobQueue) -> Job | None:
    """Put the dispatch round back if the chain is gone (ADR-044 §3).

    Layer 3's copy of `ensure_tick_queued`, deliberately not shared with it: the
    two chains fail independently, and a single helper covering both would have
    to be told which, at which point it is two functions with an argument.
    """
    if queue.pending(conn, kind=JobKind.DISPATCH, payload={}) is not None:
        return None
    log.info("no dispatch round was pending; starting the chain")
    return queue.enqueue(conn, kind=JobKind.DISPATCH)

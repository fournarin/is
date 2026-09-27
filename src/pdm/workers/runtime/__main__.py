"""Entrypoint for the `worker-runtime` container (ADR-026, ADR-039, ADR-044).

**This is where layer 1 starts running for real.** Until this slice the process
existed and claimed nothing: the rule engine and the trend extrapolator were
constructed only by tests and by `scripts/measure_prediction.py`, so a system
that could detect and predict did neither in any process a technician could open.

It now runs one handler, `observe`, which is layer 1's pulse. The tick that runs
enqueues the next one in the same transaction, so the schedule is a row rather
than a timer, and the period is the runtime class's own heartbeat interval - no
new constant (ADR-044 §1, §2).

Its signal source must be asked for. With `SIGNAL_SOURCE` unset the process
behaves exactly as it did before this slice - no handlers, no chain, reaping only
- because a deployment that has not been wired to the plant yet must not quietly
invent its own data (ADR-044 §5).

`SIGNAL_SPEED` scales the **clock**, not the feed. A compressed run moves source
time and decision time together, so a ticket's ETA, the cooldown and the expiry
sweep all mean in a demo what they mean in the plant (ADR-044 §4).

It still claims `job_class = runtime` and nothing else (invariant 12).
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import timedelta
from pathlib import Path

from pdm.contracts import MachineModel, Severity
from pdm.dispatch.service import DispatchRounds
from pdm.platform.clock import Clock, ScaledClock, SystemClock
from pdm.platform.config import load_config
from pdm.platform.config.loader import Config
from pdm.platform.db import make_pool
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.signals import LINE_A_TWELVE_HOURS, Feed, ReplaySource, SyntheticSource
from pdm.sinks import Deliveries
from pdm.sinks.registry import build as build_sink
from pdm.triggers import Triggers
from pdm.work import WorkOrders
from pdm.workers.loop import Worker
from pdm.workers.runtime.handlers import (
    TriggerLoop,
    dispatch_handler,
    ensure_pm_scan_queued,
    ensure_round_queued,
    ensure_tick_queued,
    observe_handler,
    pm_scan_handler,
)

log = logging.getLogger(__name__)

WORKER = f"{socket.gethostname()}:{os.getpid()}"

# How much faster than the plant a compressed run moves. Provenance: recorded
# decision (ADR-044 §4). Sixty turns the twelve-hour demo scenario into twelve
# minutes, which is one sitting - the requirement ADR-007 puts on a demo the
# advisor can negotiate with, and the reason `Clock` is a port at all (ADR-028).
DEFAULT_SPEED = 60.0

# Hours into the scenario the synthetic feed begins (ADR-094). Zero keeps the
# scenario whole; a demo or a trial run at real speed sets it so the degradation
# is already under way when a person sits down.
DEFAULT_HEAD_START_HOURS = 0.0


def build_clock() -> Clock:
    """Real time, or real time running fast when a demo is being compressed.

    The speed belongs here rather than on the feed. Every window in the system is
    measured on decision time - the cooldown, the ETA a ticket shows, the expiry
    sweep - so a feed that ran fast against a clock that did not would put a
    ticket's "in about six hours" six minutes away (ADR-044 §4).
    """
    speed = float(os.environ.get("SIGNAL_SPEED", DEFAULT_SPEED))
    return SystemClock() if speed == 1.0 else ScaledClock(speed)


def build_feed(clock: Clock) -> Feed | None:
    """The signal source this process reads, or None if it was not asked for.

    Three sources are in ADR-002 and two exist. `live` is named here so that an
    operator who sets it gets a sentence saying it is not built yet, rather than
    a process that silently reads nothing.
    """
    source = os.environ.get("SIGNAL_SOURCE", "").strip().lower()
    if not source or source == "none":
        return None
    if source == "live":
        raise ValueError(
            "SIGNAL_SOURCE=live is one of ADR-002's three sources and is not built yet; "
            "use 'replay' with SIGNAL_REPLAY_FILE, or 'synthetic'"
        )
    if source == "replay":
        return _replay_feed(clock)
    if source != "synthetic":
        raise ValueError(f"SIGNAL_SOURCE must be 'synthetic', 'replay' or unset, not {source!r}")

    seed = int(os.environ.get("SIGNAL_SEED", "0"))
    speed = getattr(clock, "speed", 1.0)
    scenario = LINE_A_TWELVE_HOURS

    # Loud, and at the top of the log rather than buried in it. Every ticket this
    # process issues describes a machine that is not there, and the one thing
    # that must never happen is somebody reading them as the plant (ADR-044 §5,
    # the same argument ADR-033 made about synthetic manuals).
    log.warning(
        "SYNTHETIC SIGNALS: scenario %s, seed %s, clock at %sx. %s covers %s of plant time "
        "and will be read in about %.0f minutes. Every work order this process issues is "
        "about data that does not exist.",
        scenario.name,
        seed,
        speed,
        scenario.name,
        scenario.duration,
        scenario.duration.total_seconds() / speed / 60,
    )
    head_start = timedelta(
        hours=float(os.environ.get("SIGNAL_HEAD_START_HOURS", DEFAULT_HEAD_START_HOURS))
    )
    if head_start:
        log.warning("SYNTHETIC SIGNALS: starting %s into the scenario", head_start)
    return Feed(
        SyntheticSource(scenario, seed=seed),
        decision_origin=clock.now(),
        head_start=head_start,
    )


def _replay_feed(clock: Clock) -> Feed:
    """A plant export, read back against decision time (ADR-091).

    The whole file is read and checked at boot, so a bad export stops the
    process with the line numbers in the log rather than failing an hour in.
    The feed starts at the first reading, and `SIGNAL_SPEED` compresses it
    exactly as it compresses the synthetic scenario.
    """
    raw = os.environ.get("SIGNAL_REPLAY_FILE", "").strip()
    if not raw:
        raise ValueError("SIGNAL_SOURCE=replay needs SIGNAL_REPLAY_FILE, the path of the CSV")
    path = Path(raw)
    if not path.is_file():
        raise ValueError(f"SIGNAL_REPLAY_FILE={raw} is not a file this process can read")
    signals = list(ReplaySource(path).stream())
    machines = sorted({str(signal.machine_id) for signal in signals})
    speed = getattr(clock, "speed", 1.0)
    span = signals[-1].timestamp - signals[0].timestamp
    log.warning(
        "REPLAYED SIGNALS: %s, %d readings from %s to %s (%s of plant time, about %.0f "
        "minutes at %sx) for %s. Findings are about the past the file describes.",
        path.name,
        len(signals),
        signals[0].timestamp.isoformat(),
        signals[-1].timestamp.isoformat(),
        span,
        span.total_seconds() / speed / 60,
        speed,
        ", ".join(machines),
    )
    return Feed(ReplaySource(path), decision_origin=clock.now())


def build_triggers(config: Config, clock: Clock) -> Triggers:
    """The rule engine with prediction turned on.

    The tests construct it without a trend window, because a mechanism that could
    not be switched off would have to be reasoned about in every test of the
    other half. In a real process both halves run: "monitor **and** predict" is
    the advisor's first requirement, and half of it has been switched off in
    every process until now.
    """
    policy = config.policy.triggers
    return Triggers(
        clock,
        config.rules.rules,
        cooldown=timedelta(minutes=policy.cooldown_minutes),
        eta_grace=timedelta(minutes=policy.eta_grace_minutes),
        model_of=config.model_of,
        trend_window=timedelta(minutes=policy.trend.window_minutes),
        trend_min_samples=policy.trend.min_samples,
        trend_horizon=timedelta(hours=policy.trend.max_horizon_hours),
    )


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config(Path(os.environ.get("CONFIG_DIR", "config")))
    clock = build_clock()
    pool = make_pool(min_size=2, max_size=4)

    timing = ClassTiming(
        heartbeat_seconds=config.policy.jobs.runtime.heartbeat_seconds,
        dead_after_seconds=config.policy.jobs.runtime.dead_after_seconds,
    )
    queue = JobQueue(job_class=JobClass.RUNTIME, worker=WORKER, timing=timing, clock=clock)

    fallback: dict[MachineModel, dict[Severity, int]] = config.policy.fallback_minutes
    loop = TriggerLoop(
        triggers=build_triggers(config, clock),
        orders=WorkOrders(
            clock,
            fallback_minutes={str(k): v for k, v in fallback.items()},
            wording=config.wording(),
        ),
        config=config,
        clock=clock,
        feed=build_feed(clock),
    )

    rounds = DispatchRounds(clock, config)
    # The destination `policy.yaml` asked for, resolved here and nowhere else
    # (ADR-012, ADR-069). An unknown name raises before the first round rather
    # than falling back, and none of the three environment variables below has a
    # default, for the reason ADR-019 gives `STORAGE_DIR` none: a worker pointed
    # at a guessed directory or a guessed host starts healthy and delivers
    # nowhere (ADR-074 §5).
    ticket_dir = os.environ.get("TICKET_DIR", "").strip()
    deliveries = Deliveries(
        build_sink(
            config.policy.sinks.destination,
            clock=clock,
            ticket_dir=Path(ticket_dir) if ticket_dir else None,
            cmms_base_url=os.environ.get("CMMS_BASE_URL", "").strip() or None,
            cmms_token=os.environ.get("CMMS_TOKEN", "").strip() or None,
        ),
        clock,
    )
    round_period = timedelta(seconds=config.policy.dispatch.round_seconds)

    # **No source, no trigger chain.** With nothing to read, a tick would do
    # nothing but book the next one - a job row every ten seconds for ever, and a
    # process claiming to run a trigger loop that has no signals in it. Layer 3
    # is not conditional on it: work arrives from a PM schedule and from
    # technicians reporting faults (ADR-010), so a plant with no sensors still
    # has a queue that has to be ranked.
    running = loop.feed is not None

    def seed_the_chain() -> None:
        """All three chains, seeded together and independent afterwards."""
        with pool.connection() as conn:
            if running:
                ensure_tick_queued(conn, queue)
            ensure_round_queued(conn, queue)
            ensure_pm_scan_queued(conn, queue)
            conn.commit()

    worker = Worker(
        queue=queue,
        pool=pool,
        clock=clock,
        handlers={
            JobKind.DISPATCH.value: dispatch_handler(
                rounds, queue, clock, period=round_period, deliveries=deliveries
            ),
            # The PM schedule, on the round's cadence and its own chain
            # (ADR-083). Unconditional: a plant with no sensors still has
            # preventive maintenance, which is half the point of ADR-010.
            JobKind.PM_SCAN.value: pm_scan_handler(
                loop.orders, config, queue, clock, period=round_period
            ),
            **(
                {
                    JobKind.OBSERVE.value: observe_handler(
                        loop, queue, clock, period=timedelta(seconds=timing.heartbeat_seconds)
                    )
                }
                if running
                else {}
            ),
        },
        # A job that exhausts its attempts schedules no successor, and its layer
        # would stop for ever with everything else still running (ADR-044 §3).
        on_idle=seed_the_chain,
    )
    worker.install_signal_handlers()

    seed_the_chain()
    log.info(
        "worker-runtime %s: dispatch round every %ss of clock time",
        WORKER,
        config.policy.dispatch.round_seconds,
    )
    log.info(
        "worker-runtime %s: %s PM task(s) in plant.yaml, scanned every %ss of clock time",
        WORKER,
        len(config.pm_tasks),
        config.policy.dispatch.round_seconds,
    )
    if running:
        log.info(
            "worker-runtime %s: trigger loop every %ss of clock time, signals from %s",
            WORKER,
            timing.heartbeat_seconds,
            os.environ["SIGNAL_SOURCE"],
        )
    else:
        log.info(
            "worker-runtime %s: SIGNAL_SOURCE is not set, so there is no trigger loop. "
            "Scheduling rounds still run - scheduled and reported work needs no sensor "
            "(ADR-010) - and %s jobs are reaped every %ss.",
            WORKER,
            JobClass.RUNTIME.value,
            timing.heartbeat_seconds,
        )
    try:
        worker.run_forever()
    finally:
        pool.close()
        log.info("worker-runtime %s stopped", WORKER)


if __name__ == "__main__":
    main()

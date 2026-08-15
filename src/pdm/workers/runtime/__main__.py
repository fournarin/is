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
behaves exactly as it did before this slice - reaping only - because a deployment
that has not been wired to the plant yet must not quietly invent its own data
(ADR-044 §5).

It still claims `job_class = runtime` and nothing else (invariant 12).
"""

from __future__ import annotations

import logging
import os
import socket
from datetime import timedelta
from pathlib import Path

from pdm.contracts import MachineModel, Severity
from pdm.platform.clock import Clock, SystemClock
from pdm.platform.config import load_config
from pdm.platform.config.loader import Config
from pdm.platform.db import make_pool
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.signals import LINE_A_TWELVE_HOURS, Feed, SyntheticSource
from pdm.triggers import Triggers
from pdm.work import WorkOrders
from pdm.workers.loop import Worker
from pdm.workers.runtime.handlers import TriggerLoop, ensure_tick_queued, observe_handler

log = logging.getLogger(__name__)

WORKER = f"{socket.gethostname()}:{os.getpid()}"

# How much faster than the plant a synthetic run moves. Provenance: recorded
# decision (ADR-044 §4). Sixty turns the twelve-hour demo scenario into twelve
# minutes, which is one sitting - the requirement ADR-007 puts on a demo the
# advisor can negotiate with, and the reason `Clock` is a port at all (ADR-028).
DEFAULT_SPEED = 60.0


def build_feed(clock: Clock) -> Feed | None:
    """The signal source this process reads, or None if it was not asked for.

    Three sources are in ADR-002 and one exists. `replay` and `live` are named
    here so that an operator who sets one gets a sentence saying it is not built
    yet, rather than a process that silently reads nothing.
    """
    source = os.environ.get("SIGNAL_SOURCE", "").strip().lower()
    if not source or source == "none":
        return None
    if source in ("replay", "live"):
        raise ValueError(
            f"SIGNAL_SOURCE={source} is one of ADR-002's three sources and is not built yet; "
            "only 'synthetic' exists"
        )
    if source != "synthetic":
        raise ValueError(f"SIGNAL_SOURCE must be 'synthetic' or unset, not {source!r}")

    seed = int(os.environ.get("SIGNAL_SEED", "0"))
    speed = float(os.environ.get("SIGNAL_SPEED", DEFAULT_SPEED))
    scenario = LINE_A_TWELVE_HOURS

    # Loud, and at the top of the log rather than buried in it. Every ticket this
    # process issues describes a machine that is not there, and the one thing
    # that must never happen is somebody reading them as the plant (ADR-044 §5,
    # the same argument ADR-033 made about synthetic manuals).
    log.warning(
        "SYNTHETIC SIGNALS: scenario %s, seed %s, %sx speed. %s covers %s of plant time "
        "and will be read in about %.0f minutes. Every work order this process issues is "
        "about data that does not exist.",
        scenario.name,
        seed,
        speed,
        scenario.name,
        scenario.duration,
        scenario.duration.total_seconds() / speed / 60,
    )
    return Feed(
        SyntheticSource(scenario, seed=seed),
        decision_origin=clock.now(),
        speed=speed,
    )


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
    clock = SystemClock()
    pool = make_pool(min_size=2, max_size=4)

    timing = ClassTiming(
        heartbeat_seconds=config.policy.jobs.runtime.heartbeat_seconds,
        dead_after_seconds=config.policy.jobs.runtime.dead_after_seconds,
    )
    queue = JobQueue(job_class=JobClass.RUNTIME, worker=WORKER, timing=timing, clock=clock)

    fallback: dict[MachineModel, dict[Severity, int]] = config.policy.fallback_minutes
    loop = TriggerLoop(
        triggers=build_triggers(config, clock),
        orders=WorkOrders(clock, fallback_minutes={str(k): v for k, v in fallback.items()}),
        config=config,
        clock=clock,
        feed=build_feed(clock),
    )

    def seed_the_chain() -> None:
        with pool.connection() as conn:
            ensure_tick_queued(conn, queue)
            conn.commit()

    worker = Worker(
        queue=queue,
        pool=pool,
        clock=clock,
        handlers={
            JobKind.OBSERVE.value: observe_handler(
                loop, queue, clock, period=timedelta(seconds=timing.heartbeat_seconds)
            )
        },
        # A tick that exhausts its attempts schedules no successor, and layer 1
        # would stop for ever with everything else still running (ADR-044 §3).
        on_idle=seed_the_chain,
    )
    worker.install_signal_handlers()

    seed_the_chain()
    log.info(
        "worker-runtime %s: trigger loop every %ss, signals from %s",
        WORKER,
        timing.heartbeat_seconds,
        "no source (reaping only)" if loop.feed is None else os.environ["SIGNAL_SOURCE"],
    )
    try:
        worker.run_forever()
    finally:
        pool.close()
        log.info("worker-runtime %s stopped", WORKER)


if __name__ == "__main__":
    main()

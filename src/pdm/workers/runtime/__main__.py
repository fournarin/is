"""Entrypoint for the `worker-runtime` container (ADR-026, ADR-039).

**It has no work to do yet, and it exists anyway.** The trigger loop and the
dispatch tick are layers 1 and 3; until they arrive this process claims nothing
and only sweeps for jobs whose worker died.

That is worth a container because the alternative was worse: `docker-compose.yml`
has run `python -m pdm.workers.runtime` since slice 0.3 against a module that did
not exist, so every `docker compose up` produced a container crash-looping under
`restart: unless-stopped` - noise beside the services that are working, of
exactly the kind that trains somebody to ignore a red container.

It claims `job_class = runtime` and nothing else, and with no handlers it does
not claim at all (invariant 12 twice over: the filter is in the claim's SQL, and
there is nothing here that could run an authoring job even if one were handed to
it).
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.platform.db import make_pool
from pdm.platform.jobs import ClassTiming, JobClass, JobQueue
from pdm.workers.loop import Worker

log = logging.getLogger(__name__)

WORKER = f"{socket.gethostname()}:{os.getpid()}"


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config(Path(os.environ.get("CONFIG_DIR", "config")))
    clock = SystemClock()
    pool = make_pool(min_size=2, max_size=4)

    queue = JobQueue(
        job_class=JobClass.RUNTIME,
        worker=WORKER,
        timing=ClassTiming(
            heartbeat_seconds=config.policy.jobs.runtime.heartbeat_seconds,
            dead_after_seconds=config.policy.jobs.runtime.dead_after_seconds,
        ),
        clock=clock,
    )

    # No handlers. `Worker` reads that as "reap and wait" rather than claiming
    # work it cannot do - a worker that claimed a job and failed it as an unknown
    # kind would burn the attempts of a job whose handler ships next month.
    worker = Worker(queue=queue, pool=pool, clock=clock, handlers={})
    worker.install_signal_handlers()

    log.info(
        "worker-runtime %s: no handlers yet, reaping %s jobs every %ss",
        WORKER,
        JobClass.RUNTIME.value,
        queue.timing.heartbeat_seconds,
    )
    try:
        worker.run_forever()
    finally:
        pool.close()
        log.info("worker-runtime %s stopped", WORKER)


if __name__ == "__main__":
    main()

"""Entrypoint for the `worker-authoring` container (ADR-026, ADR-039).

One image, three roles, chosen by the command in docker-compose.yml. This is the
role that ingests manuals and drafts playbooks - the slow work nobody is standing
in front of - and **the only process with a network route to `llm-server`**
(ADR-029).

It claims `job_class = authoring` and nothing else. The filter is in the claim's
SQL rather than here (invariant 12), so a mistake in this file cannot make this
process pick up a dispatch tick.

Everything it needs comes from the environment or from `config/`, and both fail
loudly at boot: a worker that started against a guessed storage directory would
look healthy while indexing manuals from somewhere nobody backs up (ADR-019).
"""

from __future__ import annotations

import logging
import os
import socket
from pathlib import Path

from pdm.authoring.service import Drafting, Ingest
from pdm.llm.extractive import ExtractiveDrafter
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.platform.db import make_pool
from pdm.platform.documents import DocumentLibrary
from pdm.platform.jobs import ClassTiming, JobClass, JobKind, JobQueue
from pdm.platform.objects import FilesystemObjectStore, storage_root
from pdm.retrieval.embedding import OnnxEmbedder
from pdm.retrieval.service import HybridSearch, profiles_from
from pdm.retrieval.vectors import qdrant_from_env
from pdm.workers.authoring.handlers import draft_handler, ingest_handler
from pdm.workers.loop import Worker

log = logging.getLogger(__name__)

# The name that goes in `claimed_by`, so a stuck job says which container to look
# at. The hostname is the container id under compose, and the pid distinguishes a
# restarted process from the one the reaper gave up on.
WORKER = f"{socket.gethostname()}:{os.getpid()}"


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    config = load_config(Path(os.environ.get("CONFIG_DIR", "config")))
    clock = SystemClock()

    # Two, minimum: the handler holds one for the whole of the job's transaction
    # and the heartbeat needs its own. At one they deadlock, and only under load
    # (ADR-039).
    pool = make_pool(min_size=2, max_size=4)

    library = DocumentLibrary(FilesystemObjectStore(storage_root()), clock)
    hybrid = HybridSearch(OnnxEmbedder(), qdrant_from_env())
    authoring_profile, _ = profiles_from(config.policy.retrieval)

    ingest = Ingest(library, hybrid)
    drafting = Drafting(
        hybrid,
        # The backend with no model in it. The LLM one is a deliberate change of
        # configuration and not a default (ADR-037 section 9): a worker that fell
        # back to whichever was reachable would file drafts of two different
        # qualities under one name.
        ExtractiveDrafter(),
        profile=authoring_profile,
        skills=config.skills,
    )

    queue = JobQueue(
        job_class=JobClass.AUTHORING,
        worker=WORKER,
        timing=ClassTiming(
            heartbeat_seconds=config.policy.jobs.authoring.heartbeat_seconds,
            dead_after_seconds=config.policy.jobs.authoring.dead_after_seconds,
        ),
        clock=clock,
    )

    worker = Worker(
        queue=queue,
        pool=pool,
        clock=clock,
        handlers={
            JobKind.INGEST.value: ingest_handler(ingest),
            JobKind.DRAFT.value: draft_handler(drafting, clock),
        },
    )
    worker.install_signal_handlers()

    log.info("worker-authoring %s: claiming %s jobs", WORKER, JobClass.AUTHORING.value)
    try:
        worker.run_forever()
    finally:
        pool.close()
        log.info("worker-authoring %s stopped", WORKER)


if __name__ == "__main__":
    main()

"""The FastAPI application (ADR-008, ADR-029).

Assembled here rather than at import time so that a test can build one against
its own database, store and clock without a module-level connection appearing
the moment anything imports this package.

`api` is on the `app` network only. It has no route to `llm-server`, which is
what makes ADR-003 physically true rather than merely enforced by an import rule
(ADR-029), and `scripts/check_llm_isolation.py` fails the build if that changes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from pdm.api import documents, sessions
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import Clock, SystemClock
from pdm.platform.db import make_pool
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore, storage_root


def create_app(
    *,
    pool: Any | None = None,
    library: DocumentLibrary | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """Build the application, with everything it depends on passed in.

    Nothing here reads the environment unless it has to. A test supplies its own
    pool, store and clock; the deployed process supplies none and gets the real
    ones - and gets a loud failure at boot rather than a default if DATABASE_URL
    or STORAGE_DIR is missing (ADR-019, ADR-031).
    """
    the_clock = clock or SystemClock()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.pool = pool or make_pool()
        app.state.library = library or DocumentLibrary(
            FilesystemObjectStore(storage_root()), the_clock
        )
        app.state.authentication = Authentication(LocalAccounts(), the_clock)
        yield

    app = FastAPI(title="Predictive maintenance", lifespan=lifespan)
    app.include_router(sessions.router)
    app.include_router(documents.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """The one route with no session, besides logging in.

        A health check that required credentials would mean the thing watching
        the service needs an account, and an account for a monitor is an account
        nobody rotates.
        """
        return {"status": "ok"}

    return app

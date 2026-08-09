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

from fastapi import FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from pdm.api import deps, documents, sessions
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import Clock, SystemClock
from pdm.platform.db import make_pool
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore, storage_root

# A scanned two-hundred-page manual is tens of megabytes; this leaves room for
# several times the largest thing anybody should be uploading and stops the
# request that is not a manual at all.
MAX_BODY_BYTES = 256 * 1024 * 1024

# Everything else needs a session. Listed here rather than inferred, so adding a
# route that should be public is a visible edit and forgetting to add one gives a
# 401 rather than an open door.
_PUBLIC_PATHS = frozenset({"/health", "/sessions", "/docs", "/redoc", "/openapi.json"})


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

    @app.middleware("http")
    async def refuse_before_reading_the_body(request: Request, call_next: Any) -> Response:
        """Two checks that have to happen before FastAPI parses a request body.

        FastAPI parses a multipart body **before** it resolves dependencies, so
        the authorisation on the upload route runs after the file has already
        been written to the container's disk. `curl -F file=@/dev/zero` with no
        session at all would fill the volume and only then be told 401.

        So the size limit and a session *presence* check live here, in front of
        the parser. The presence check is not the authorisation - `requires()` on
        the route is, and it is what invariant 6 is about. This one only refuses
        to read a body from somebody who has not even attempted to sign in.
        """
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse(
                {"detail": f"a request body over {MAX_BODY_BYTES} bytes is refused"},
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            )

        anonymous = deps.SESSION_COOKIE not in request.cookies
        if anonymous and request.url.path not in _PUBLIC_PATHS:
            return JSONResponse({"detail": "no session"}, status_code=status.HTTP_401_UNAUTHORIZED)

        response: Response = await call_next(request)
        return response

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

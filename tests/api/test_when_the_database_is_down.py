"""PostgreSQL stops while people are signed in (acceptance walk, 2026-09-30).

On the rehearsal stack every screen waited thirty seconds and then showed a
500: the pool's default wait, then an unhandled `PoolTimeout`. A technician
holding a phone reads thirty seconds of nothing as a broken system. The API now
says 503 - "not answering", which the web layer already treats as the network
failure it is and keeps a close on the phone for - and says it within seconds.

No database is needed to test a database that is not there.
"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from pdm.api.app import API_POOL_TIMEOUT_SECONDS, create_app
from pdm.platform.clock import SystemClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore

# Port 1 on loopback: refused at once, as a stopped container's port is.
NOBODY_HOME = "postgresql://nobody@127.0.0.1:1/nothing?connect_timeout=1"


def test_a_database_that_does_not_answer_is_a_503_and_soon(tmp_path: Path) -> None:
    clock = SystemClock()
    pool = ConnectionPool(NOBODY_HOME, min_size=1, max_size=2, open=True, timeout=1.0)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    try:
        app = create_app(pool=pool, library=library, clock=clock)
        with TestClient(app) as client:
            client.cookies.set("pdm_session", "anything")
            started = time.monotonic()
            response = client.get("/sessions/current")
            waited = time.monotonic() - started
    finally:
        pool.close()

    assert response.status_code == 503
    assert "database" in response.json()["detail"]
    assert waited < 5


def test_the_api_waits_seconds_for_a_connection_and_not_half_a_minute() -> None:
    assert API_POOL_TIMEOUT_SECONDS <= 5

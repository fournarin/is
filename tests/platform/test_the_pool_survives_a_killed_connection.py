"""A connection the server closed is the pool's problem, not the next caller's.

Measured rather than assumed. Terminating the backends and then making six
requests through a pool built without `check` failed four of them - one per
pooled connection - each with `AdminShutdown`. With `check` none of them failed.

The scenario is ordinary: a backup script terminating idle backends,
`idle_session_timeout`, a firewall dropping an idle TCP connection on a plant
network, or anybody restarting the database. What makes it worth a test rather
than a comment is where it lands. In `api` it is an error on a technician's
screen; in `worker-runtime` it is a failed trigger tick or a failed dispatch
round, and the job queue retrying is recovery rather than the absence of a
fault.

This test kills every other backend on the database it runs against, so it is
marked `db` and belongs to the tier that owns a PostgreSQL of its own.
"""

from __future__ import annotations

import os

import pytest
from psycopg import connect
from psycopg_pool import ConnectionPool

from pdm.platform.db import make_pool

pytestmark = pytest.mark.db


def _terminate_every_other_backend() -> None:
    with connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid()"
        )


class TestAfterTheServerClosesEverything:
    def test_the_pool_still_answers(self) -> None:
        pool = make_pool(min_size=3, max_size=4)
        try:
            for _ in range(3):
                with pool.connection() as conn:
                    conn.execute("SELECT 1")

            _terminate_every_other_backend()

            for _ in range(6):
                with pool.connection() as conn:
                    assert conn.execute("SELECT 1").fetchone() == (1,)
        finally:
            pool.close()

    def test_and_the_pool_is_built_to(self) -> None:
        """The behaviour above comes from one argument. Asserting the argument
        as well as the behaviour is what makes a future edit that drops it fail
        here rather than on a plant machine six months later."""
        pool = make_pool()
        try:
            assert pool._check is ConnectionPool.check_connection
        finally:
            pool.close()

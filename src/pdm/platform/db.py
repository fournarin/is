"""Database connections. The only module that knows a DSN exists.

Everything else receives a connection (ADR-031): repo functions take one as
their first argument so that a job and the data it belongs to commit together
(ADR-017), and services pass it down rather than reaching for one.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

DSN_ENV = "DATABASE_URL"


def dsn() -> str:
    value = os.environ.get(DSN_ENV)
    if not value:
        raise RuntimeError(
            f"{DSN_ENV} is not set. There is no default and no fallback to a local "
            f"file database: the queue relies on SKIP LOCKED, partial indexes and "
            f"CHECK constraints, so a substitute would pass tests that the real "
            f"thing would fail (ADR-031)."
        )
    return value


def make_pool(
    min_size: int = 1, max_size: int = 4, timeout: float = 30.0
) -> ConnectionPool[Connection[Any]]:
    """A pool that hands out a connection it has just verified.

    `check` is what makes a connection the server has closed somebody else's
    problem rather than the next caller's. Without it the pool hands out what it
    holds, and a connection killed while idle fails on use: measured here by
    terminating the backends and then making six requests, four of them failed
    with `AdminShutdown` - one per pooled connection - and with `check` none of
    them did.

    That is not an exotic input. An idle backend is terminated by a backup
    script, by `idle_session_timeout`, by a firewall dropping an idle TCP
    connection on a plant network, or by anybody restarting the database. The
    cost of noticing is one round trip per checkout, against a request that is
    about to do several.

    `worker-runtime` is where it matters most: a failed checkout there is a
    failed trigger tick or a failed dispatch round, and the queue retrying is
    recovery rather than the absence of a fault.

    `timeout` is how long a caller waits for a connection. A worker can wait; a
    person looking at a screen cannot, so the API passes a shorter one.
    """
    return ConnectionPool(
        dsn(),
        min_size=min_size,
        max_size=max_size,
        open=True,
        timeout=timeout,
        check=ConnectionPool.check_connection,
    )


@contextmanager
def transaction(conn: Connection[Any]) -> Iterator[Connection[Any]]:
    """One transaction around a unit of work.

    The shape ADR-017 depends on: the caller opens this once and passes the same
    connection to every repo call inside, so enqueueing a job and writing its
    result cannot end up in separate transactions.
    """
    with conn.transaction():
        yield conn


@contextmanager
def connection() -> Iterator[Connection[Any]]:
    """A single short-lived connection, for scripts and tests."""
    conn = connect(dsn())
    try:
        yield conn
    finally:
        conn.close()

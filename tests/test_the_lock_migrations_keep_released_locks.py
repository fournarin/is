"""Migration 0022 over a database that already holds released locks (ADR-137, N5).

0022 adds "a lock off says why". A database migrated to 0021 and used - trial
data - holds locks that came off with no reason recorded, and adding the rule
without first saying where they came off fails the upgrade on exactly the
databases that matter. This migrates a fresh database to 0021, takes a lock on
and off, and upgrades to head.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from psycopg import connect
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy.engine import URL

from pdm.contracts import MachineId, MachineModel, Severity, UserId
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import WorkOrders

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)


@pytest.fixture
def scratch() -> Iterator[str]:
    """A database of its own, created and dropped here: the shared one is at head."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    name = f"pdm_migration_{uuid.uuid4().hex[:8]}"
    with connect(url, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield make_conninfo(url, dbname=name)
    finally:
        with connect(url, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE "{name}" WITH (FORCE)')


def _alembic(dsn: str) -> Config:
    config = Config(str(Path("alembic.ini")))
    params = {k: str(v) for k, v in conninfo_to_dict(dsn).items() if v is not None}
    # Keep the password: CI's PostgreSQL asks for one, a laptop's often does not.
    url = URL.create(
        "postgresql+psycopg",
        username=params.get("user") or None,
        password=params.get("password") or None,
        host=params.get("host") or "localhost",
        port=int(params.get("port") or 5432),
        database=params["dbname"],
    ).render_as_string(hide_password=False)
    # alembic's config is a ConfigParser, where a bare % starts an interpolation.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def test_0022_upgrades_a_database_with_released_locks(scratch: str) -> None:
    config = _alembic(scratch)
    command.upgrade(config, "0021")
    fallback = {
        str(model): dict(rows)
        for model, rows in load_config(Path("config")).policy.fallback_minutes.items()
    }
    with connect(scratch) as conn:
        ref = (
            WorkOrders(SimulatedClock(NOW), fallback_minutes=fallback)
            .from_report(
                conn,
                machine_id=MachineId("MC-012"),
                machine_model=MachineModel("R-2000iC"),
                severity=Severity.MEDIUM,
                reported_by=UserId("op-1"),
                description="a lock on and off under 0021",
            )
            .ref
        )
        conn.execute(
            "INSERT INTO lock_record (work_order_ref, machine_id, point_id, lock_no, owner, step,"
            " applied_at, released_at) VALUES (%s, 'MC-012', 'CP-3', 'ก-03', 'tech-1', 2, %s, %s)",
            (ref, NOW, NOW + timedelta(hours=1)),
        )
        conn.commit()

    command.upgrade(config, "head")

    with connect(scratch) as conn:
        row = conn.execute("SELECT release_reason, release_witness FROM lock_record").fetchone()
    assert row == ("restore step (before ADR-136)", None)

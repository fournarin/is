"""Alembic environment.

No SQLAlchemy models and no autogenerate (ADR-031). Alembic is used for one
thing: keeping migrations ordered and recording which have been applied. The
migrations themselves are raw SQL.

This file and the versions beside it are the only place in the repository
allowed to import alembic or sqlalchemy; .importlinter enforces that for
src/pdm, so the transitive dependency cannot quietly spread into repo.py.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config


def _psycopg3(url: str) -> str:
    """Point SQLAlchemy at psycopg 3.

    A bare postgresql:// URL makes SQLAlchemy reach for psycopg2, which this
    project does not install. Translating here means DATABASE_URL stays the
    ordinary DSN that psycopg, docker compose and psql all accept, and nobody
    has to remember a driver-specific spelling in an environment variable.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


if not config.get_main_option("sqlalchemy.url", None):
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    config.set_main_option("sqlalchemy.url", _psycopg3(url))


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

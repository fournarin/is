"""The proof obligation migration 0014 carries, run against rows written to fail it.

`PlaybookStep` now refuses a step that cites no document (invariant 4, ADR-084).
Steps already in the database were written under the older contract and are read
back through `model_validate`, so before the contract may tighten, something has
to say that no stored row fails it. Migration 0014 is that something, and it
stops the upgrade rather than rewriting anything: a `playbook_snapshot` is
evidence of what a technician was instructed to do and invariant 2 makes it
unchangeable.

A check that has never been seen to fail is a check nobody knows the shape of.
So the two queries are run here against rows written to fail them on purpose
(#108), in real PostgreSQL, because what could be wrong about them is `jsonb`
semantics: `->>` on a missing key returns NULL rather than the empty string, and
a query that forgets that passes every row.
"""

from __future__ import annotations

import importlib.util
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg.types.json import Jsonb

pytestmark = pytest.mark.db

MIGRATION = Path("migrations/versions/0014_every_stored_step_names_its_document.py")


def _migration() -> Any:
    """Imported by path: the versions directory is not a package, and alembic
    loads these files the same way."""
    spec = importlib.util.spec_from_file_location("pdm_migration_0014", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ATTRIBUTED = {"text": "Isolate the drive", "source_doc": "a" * 64, "page": 12, "confidence": 0.9}
NO_SOURCE = {"text": "Isolate the drive", "source_doc": "", "page": 12, "confidence": 0.9}
BLANK_SOURCE = {"text": "Isolate the drive", "source_doc": "  ", "page": 12, "confidence": 0.9}
NO_KEY_AT_ALL = {"text": "Isolate the drive", "page": 12, "confidence": 0.9}


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    """A connection that never commits. The temp tables below shadow the real
    `work_order` and `playbook` for this session only, which is what lets the
    queries run against rows the real tables would refuse: `work_order` has a
    trigger that freezes a snapshot, so there is no way to write a bad one
    through the front door, and that is the point of the freeze."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _snapshots(conn: Connection[Any], rows: dict[str, list[dict[str, Any]]]) -> None:
    conn.execute("CREATE TEMP TABLE work_order (work_order_ref text, playbook_snapshot jsonb)")
    for ref, steps in rows.items():
        conn.execute(
            "INSERT INTO work_order (work_order_ref, playbook_snapshot) VALUES (%s, %s)",
            (ref, Jsonb(steps)),
        )


def _found(conn: Connection[Any], query: str) -> list[str]:
    return [str(row[0]) for row in conn.execute(query).fetchall()]


class TestASnapshotThatLostItsProvenanceIsNamed:
    def test_a_step_citing_the_empty_string_is_found(self, conn: Connection[Any]) -> None:
        _snapshots(
            conn,
            {
                "WO-000001": [ATTRIBUTED, ATTRIBUTED],
                "WO-000002": [ATTRIBUTED, NO_SOURCE],
            },
        )

        assert _found(conn, _migration().UNATTRIBUTED_SNAPSHOT_STEPS) == ["WO-000002"]

    def test_a_step_citing_whitespace_is_found_too(self, conn: Connection[Any]) -> None:
        """`" "` is not a document. The contract strips before it judges, and a
        query that only compared against `''` would let the row through and then
        fail on the read a year later."""
        _snapshots(conn, {"WO-000003": [BLANK_SOURCE]})

        assert _found(conn, _migration().UNATTRIBUTED_SNAPSHOT_STEPS) == ["WO-000003"]

    def test_a_step_with_no_source_doc_key_is_found(self, conn: Connection[Any]) -> None:
        """`->>` on a missing key is NULL, and `NULL = ''` is NULL rather than
        true, so the `coalesce` is what makes this row visible. Without it the
        query passes every row it should catch."""
        _snapshots(conn, {"WO-000004": [NO_KEY_AT_ALL]})

        assert _found(conn, _migration().UNATTRIBUTED_SNAPSHOT_STEPS) == ["WO-000004"]

    def test_a_fully_attributed_table_comes_back_empty(self, conn: Connection[Any]) -> None:
        """The expected result on any database this repository has seeded, and
        not the same as not looking."""
        _snapshots(conn, {"WO-000005": [ATTRIBUTED], "WO-000006": [ATTRIBUTED, ATTRIBUTED]})

        assert _found(conn, _migration().UNATTRIBUTED_SNAPSHOT_STEPS) == []


class TestTheServedPlaybooksAreCheckedToo:
    """`playbooks/repo.py` reads `steps` through the same contract, so a served
    playbook with an unattributed step stops being readable at the same moment."""

    def test_a_playbook_step_citing_no_document_is_named(self, conn: Connection[Any]) -> None:
        conn.execute(
            "CREATE TEMP TABLE playbook (symptom_code text, machine_model text, steps jsonb)"
        )
        conn.execute(
            "INSERT INTO playbook VALUES (%s, %s, %s), (%s, %s, %s)",
            ("SYM-014", "R-2000iC", Jsonb([ATTRIBUTED]), "SYM-022", "R-2000iC", Jsonb([NO_SOURCE])),
        )

        assert _found(conn, _migration().UNATTRIBUTED_PLAYBOOK_STEPS) == ["SYM-022 / R-2000iC"]

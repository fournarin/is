"""ADR-101: an install can reset, re-role and withdraw accounts from the host."""

from __future__ import annotations

import os
from typing import Any

import pytest
from psycopg import connect

from pdm.platform.auth import cli

pytestmark = pytest.mark.db


@pytest.fixture
def url() -> str:
    found = os.environ.get("DATABASE_URL")
    if not found:
        pytest.skip("DATABASE_URL not set")
    with connect(found) as conn:
        conn.execute("TRUNCATE account CASCADE")
        conn.commit()
    return found


def _row(url: str, user: str) -> tuple[Any, ...] | None:
    with connect(url) as conn:
        return conn.execute(
            "SELECT role, active FROM account WHERE user_id = %s", (user,)
        ).fetchone()


def test_add_reset_re_role_and_withdraw(url: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["add", "somsak", "สมศักดิ์", "technician"]) == 0
    assert "shown once" in capsys.readouterr().out
    assert _row(url, "somsak") == ("technician", True)

    assert cli.main(["reset-password", "somsak"]) == 0
    assert cli.main(["set-role", "somsak", "supervisor"]) == 0
    assert _row(url, "somsak") == ("supervisor", True)

    assert cli.main(["withdraw", "somsak"]) == 0
    assert _row(url, "somsak") == ("supervisor", False)


def test_an_unknown_command_prints_the_usage(url: str) -> None:
    assert cli.main(["delete-everything"]) == 1

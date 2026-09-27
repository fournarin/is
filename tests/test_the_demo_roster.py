"""The demo roster: what it writes, and what it refuses to write (ADR-078).

Two of these are about the refusal rather than the roster, and they are the
reason this file exists. A script that invents three people has to be unable to
do it anywhere except the world it was written for, and "unable" has to be a
test rather than a sentence in a docstring.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import Role, UserId, shift_at
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from scripts import seed_demo_roster

pytestmark = pytest.mark.db

CONFIG = load_config(Path("config"))
DEMO_ACCOUNTS = [
    (UserId("tech-1"), Role.TECHNICIAN),
    (UserId("eng-1"), Role.ENGINEER),
    (UserId("sup-1"), Role.SUPERVISOR),
    (UserId("op-1"), Role.OPERATOR),
]


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def conn(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection[Any]]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = connect(database_url, autocommit=True)
    try:
        connection.execute(
            "TRUNCATE work_order, shift_assignment, technician, access_log, session, "
            "account CASCADE"
        )
        yield connection
    finally:
        connection.close()


def _seed_demo_accounts(conn: Connection[Any]) -> None:
    """What `scripts/seed_demo.py` leaves behind, reduced to the part §6 reads."""
    auth = Authentication(LocalAccounts(), SystemClock())
    for user, role in DEMO_ACCOUNTS:
        auth.create_account(
            conn, user=user, display_name=str(user), role=role, password="demo-password"
        )


class TestItRefusesWhereItDoesNotBelong:
    def test_a_database_with_no_demo_accounts_is_not_a_demo_database(
        self, conn: Connection[Any]
    ) -> None:
        """ADR-078 §6. The one guard available that rests on a fact: nothing in
        the schema says "this is production", but the world this script extends
        is either present or it is not."""
        assert seed_demo_roster.main() == 1

    def test_the_refusal_writes_nothing_at_all(self, conn: Connection[Any]) -> None:
        seed_demo_roster.main()

        assert conn.execute("SELECT count(*) FROM technician").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM shift_assignment").fetchone() == (0,)
        assert conn.execute("SELECT count(*) FROM account").fetchone() == (0,)

    def test_one_missing_account_is_enough_to_refuse(self, conn: Connection[Any]) -> None:
        """Not "some of them": a half-seeded world produces a half-working demo,
        which is the failure mode hardest to read from a screen."""
        auth = Authentication(LocalAccounts(), SystemClock())
        for user, role in DEMO_ACCOUNTS[:-1]:
            auth.create_account(
                conn, user=user, display_name=str(user), role=role, password="demo-password"
            )

        assert seed_demo_roster.main() == 1
        assert conn.execute("SELECT count(*) FROM technician").fetchone() == (0,)


class TestWhatItWrites:
    def test_three_technicians_with_accounts_to_open_their_work(
        self, conn: Connection[Any]
    ) -> None:
        _seed_demo_accounts(conn)

        assert seed_demo_roster.main() == 0

        technicians = dispatch_repo.technicians(conn)
        assert len(technicians) == 3
        accounts = conn.execute("SELECT count(*) FROM account WHERE role = 'technician'").fetchone()
        assert accounts == (3,)

    def test_between_them_they_hold_every_skill_the_plant_has(self, conn: Connection[Any]) -> None:
        """A playbook's `required_skill` is chosen at drafting time and is not
        knowable here. A round that finds nobody with it leaves the job
        unassigned, correctly, and that reads on a demo screen as a bug."""
        _seed_demo_accounts(conn)
        seed_demo_roster.main()

        held = {
            skill for technician in dispatch_repo.technicians(conn) for skill in technician.skills
        }
        assert held == set(CONFIG.skills)

    def test_the_roster_covers_the_shift_running_now_and_the_day_after(
        self, conn: Connection[Any]
    ) -> None:
        """ADR-078 §5: resolved when it runs, not hardcoded. A demo at 23:00 files
        under the night shift, against the date that shift began - and, since
        ADR-094, every shift of the next day too, so a demo that crosses a shift
        boundary still has somebody on it."""
        _seed_demo_accounts(conn)
        seed_demo_roster.main()

        now = SystemClock().now()
        wanted = {
            (str(found.shift_id), found.on_date)
            for hour in range(25)
            if (
                found := shift_at(
                    CONFIG.shifts.values(), now + timedelta(hours=hour), CONFIG.timezone
                )
            )
            is not None
        }
        rows = conn.execute("SELECT DISTINCT shift_id, on_date FROM shift_assignment").fetchall()
        assert set(rows) == wanted
        running = shift_at(CONFIG.shifts.values(), now, CONFIG.timezone)
        assert running is not None and (str(running.shift_id), running.on_date) in wanted

    def test_every_technician_gets_the_same_declared_capacity(self, conn: Connection[Any]) -> None:
        _seed_demo_accounts(conn)
        seed_demo_roster.main()

        minutes = conn.execute("SELECT DISTINCT available_minutes FROM shift_assignment").fetchall()
        assert minutes == [(seed_demo_roster.AVAILABLE_MINUTES,)]

    def test_running_it_twice_leaves_one_roster(self, conn: Connection[Any]) -> None:
        """The rehearsal runs it after a re-seed, and a person will run it again
        after that. Three people twice is a shift with six technicians in it and
        a load gate that lets through twice what the plant can do."""
        _seed_demo_accounts(conn)
        seed_demo_roster.main()
        assert seed_demo_roster.main() == 0

        assert len(dispatch_repo.technicians(conn)) == 3
        shifts = conn.execute(
            "SELECT count(DISTINCT (shift_id, on_date)) FROM shift_assignment"
        ).fetchone()
        assert shifts is not None
        assert conn.execute("SELECT count(*) FROM shift_assignment").fetchone() == (3 * shifts[0],)

    def test_it_creates_no_work(self, conn: Connection[Any]) -> None:
        """A roster is capacity, not a source of work. ADR-010's three origins
        stand, and a demo seed that issued orders would be a fourth."""
        _seed_demo_accounts(conn)
        seed_demo_roster.main()

        assert conn.execute("SELECT count(*) FROM work_order").fetchone() == (0,)

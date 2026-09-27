"""The plant's own people, roster and PM history, read from CSV (ADR-091).

Two halves. The readers are pure, so what they accept and refuse is tested
without a database. `main()` is tested against PostgreSQL for the two promises
that matter on an installation: nothing is written when any row is wrong, and
what is written is what the files said.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from psycopg import Connection, connect

from pdm.contracts import SkillId
from scripts import import_plant_data
from scripts.import_plant_data import read_pm_history, read_roster, read_technicians

SKILLS = frozenset({SkillId("robot_mechanical"), SkillId("electrical")})
BANGKOK = ZoneInfo("Asia/Bangkok")
NOW = datetime(2026, 9, 27, 3, 0, tzinfo=UTC)


def _csv(*lines: str) -> list[str]:
    return [f"{line}\n" for line in lines]


class TestTechnicians:
    def test_a_row_becomes_a_technician_with_its_skills(self) -> None:
        data = read_technicians(
            _csv(
                "user_id,display_name,skills,active",
                "tech-07,Somsak,robot_mechanical;electrical,yes",
            ),
            skills=SKILLS,
        )

        assert data.problems == []
        assert data.people[0].technician.skills == SKILLS
        assert data.people[0].technician.active

    def test_a_skill_plant_yaml_does_not_know_is_refused_not_created(self) -> None:
        data = read_technicians(
            _csv("user_id,display_name,skills", "tech-07,Somsak,welding"), skills=SKILLS
        )

        assert data.people == []
        assert "technicians.csv:2: skill welding is not in plant.yaml" in data.problems[0]

    def test_a_person_listed_twice_is_refused(self) -> None:
        data = read_technicians(
            _csv("user_id,display_name,skills", "tech-07,A,electrical", "tech-07,B,electrical"),
            skills=SKILLS,
        )

        assert data.problems == ["technicians.csv:3: tech-07 appears twice"]


class TestRoster:
    def test_a_line_is_a_person_on_a_shift_on_a_day(self) -> None:
        data = read_roster(
            _csv("date,shift_id,user_id,available_minutes", "2026-10-01,morning,tech-07,420"),
            shifts=frozenset({"morning"}),
            technicians=frozenset({"tech-07"}),
        )

        assert data.problems == []
        assert data.roster[0].available_minutes == 420

    def test_every_bad_line_is_reported_together(self) -> None:
        data = read_roster(
            _csv(
                "date,shift_id,user_id,available_minutes",
                "01/10/2026,morning,tech-07,420",
                "2026-10-01,lunch,tech-07,420",
                "2026-10-01,morning,nobody,420",
                "2026-10-01,morning,tech-07,0",
            ),
            shifts=frozenset({"morning"}),
            technicians=frozenset({"tech-07"}),
        )

        assert [problem.split(":")[1] for problem in data.problems] == ["2", "3", "4", "5"]


class TestPmHistory:
    def test_a_date_is_midnight_in_the_plants_own_zone(self) -> None:
        data = read_pm_history(
            _csv("pm_task_ref,last_done", "pm-a,2026-06-14"),
            tasks=frozenset({"pm-a"}),
            zone=BANGKOK,
            now=NOW,
        )

        assert data.pm_done[0][1] == datetime(2026, 6, 13, 17, 0, tzinfo=UTC)

    def test_a_time_without_an_offset_is_refused(self) -> None:
        data = read_pm_history(
            _csv("pm_task_ref,last_done", "pm-a,2026-06-14T08:00:00"),
            tasks=frozenset({"pm-a"}),
            zone=BANGKOK,
            now=NOW,
        )

        assert "no UTC offset" in data.problems[0]

    def test_a_task_plant_yaml_does_not_have_and_a_future_date_are_refused(self) -> None:
        data = read_pm_history(
            _csv("pm_task_ref,last_done", "pm-z,2026-06-14", "pm-a,2027-01-01"),
            tasks=frozenset({"pm-a"}),
            zone=BANGKOK,
            now=NOW,
        )

        assert len(data.problems) == 2
        assert "in the future" in data.problems[1]


@pytest.fixture
def conn(monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url, autocommit=True)
    try:
        connection.execute(
            "TRUNCATE work_order, shift_assignment, technician, pm_task, access_log, "
            "session, account CASCADE"
        )
        yield connection
    finally:
        connection.close()


def _files(tmp_path: Path, roster_minutes: str = "420") -> list[str]:
    (tmp_path / "technicians.csv").write_text(
        "user_id,display_name,skills,active\ntech-07,Somsak,robot_mechanical,yes\n",
        encoding="utf-8",
    )
    (tmp_path / "roster.csv").write_text(
        f"date,shift_id,user_id,available_minutes\n2026-10-01,morning,tech-07,{roster_minutes}\n",
        encoding="utf-8",
    )
    (tmp_path / "pm_history.csv").write_text(
        "pm_task_ref,last_done\npm-mc-001-toothed-belt,2026-06-14\n", encoding="utf-8"
    )
    return [
        "--technicians", str(tmp_path / "technicians.csv"),
        "--roster", str(tmp_path / "roster.csv"),
        "--pm-history", str(tmp_path / "pm_history.csv"),
    ]  # fmt: skip


@pytest.mark.db
class TestWritingIt:
    def test_what_the_files_say_is_what_the_database_holds(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        environ = {"DATABASE_URL": os.environ["DATABASE_URL"]}

        assert import_plant_data.main(_files(tmp_path), environ) == 0

        assert conn.execute("SELECT user_id, active FROM technician").fetchall() == [
            ("tech-07", True)
        ]
        assert conn.execute(
            "SELECT technician, available_minutes FROM shift_assignment"
        ).fetchall() == [("tech-07", 420)]
        assert conn.execute(
            "SELECT last_done_at FROM pm_task WHERE pm_task_ref = 'pm-mc-001-toothed-belt'"
        ).fetchone() == (datetime(2026, 6, 13, 17, 0, tzinfo=UTC),)
        assert conn.execute("SELECT role FROM account WHERE user_id = 'tech-07'").fetchone() == (
            "technician",
        )

    def test_one_bad_row_anywhere_writes_nothing_at_all(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        environ = {"DATABASE_URL": os.environ["DATABASE_URL"]}

        assert import_plant_data.main(_files(tmp_path, roster_minutes="none"), environ) == 2

        for table in ("technician", "shift_assignment", "account"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)

    def test_running_it_twice_changes_nothing_the_second_time(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        environ = {"DATABASE_URL": os.environ["DATABASE_URL"]}
        arguments = _files(tmp_path)

        assert import_plant_data.main(arguments, environ) == 0
        assert import_plant_data.main(arguments, environ) == 0

        assert conn.execute("SELECT count(*) FROM technician").fetchone() == (1,)
        assert conn.execute("SELECT count(*) FROM shift_assignment").fetchone() == (1,)


class TestTheShippedExamplesAreValid:
    """`plant-data/examples/` is what somebody copies first. If it stops matching
    `config/plant.yaml` it teaches the wrong format, so it is read here."""

    def test_every_example_reads_with_no_problem(self) -> None:
        from pdm.platform.config import load_config
        from pdm.signals.replay import parse

        config = load_config(Path("config"))
        examples = Path("plant-data/examples")
        skills = frozenset(SkillId(str(skill)) for skill in config.skills)

        people = read_technicians(
            (examples / "technicians.csv").read_text(encoding="utf-8").splitlines(True),
            skills=skills,
        )
        roster = read_roster(
            (examples / "roster.csv").read_text(encoding="utf-8").splitlines(True),
            shifts=frozenset(str(shift) for shift in config.shifts),
            technicians=frozenset(str(person.technician.user) for person in people.people),
        )
        history = read_pm_history(
            (examples / "pm_history.csv").read_text(encoding="utf-8").splitlines(True),
            tasks=frozenset(str(task.pm_task_ref) for task in config.pm_tasks),
            zone=config.timezone,
            now=NOW,
        )
        signals = parse((examples / "signals.csv").read_text(encoding="utf-8").splitlines(True))

        assert people.problems == roster.problems == history.problems == []
        machines = {str(m) for station in config.stations.values() for m in station.machine_ids}
        assert {str(signal.machine_id) for signal in signals} <= machines

    def test_the_example_signals_cross_a_rule_for_long_enough_to_fire(self) -> None:
        """A replay example that fires nothing teaches somebody that replay does
        not work. MC-001's motor passes 85 degrees and stays there."""
        from pdm.platform.config import load_config
        from pdm.signals.replay import parse
        from pdm.triggers.domain import breaches

        config = load_config(Path("config"))
        rule = next(rule for rule in config.rules.rules if rule.rule_id == "R-motor-temp-high")
        signals = parse(
            Path("plant-data/examples/signals.csv").read_text(encoding="utf-8").splitlines(True)
        )
        over = [
            signal.timestamp
            for signal in signals
            if signal.machine_id == "MC-001"
            and signal.metric_name == rule.metric_name
            and breaches(signal, rule)
        ]

        assert over
        assert (over[-1] - over[0]).total_seconds() >= rule.for_seconds

"""Load the plant's own people, roster and PM history from CSV (ADR-091).

    DATABASE_URL=... uv run python scripts/import_plant_data.py \\
        --technicians technicians.csv --roster roster.csv --pm-history pm_history.csv

Any of the three files may be given alone. This is what replaces
`seed_demo_roster.py` on a real installation: the demo invents three people,
and this reads the ones the plant has. The advisor expects the technician data
to be obtainable before any sensor data is (docs-md `professor_notes.md`, round
5), and a spreadsheet export is the form it will arrive in.

    technicians.csv   user_id,display_name,skills,active
                      tech-07,Somsak K.,robot_mechanical;electrical,yes
    roster.csv        date,shift_id,user_id,available_minutes
                      2026-10-01,morning,tech-07,420
    pm_history.csv    pm_task_ref,last_done
                      pm-mc-001-toothed-belt,2026-06-14

Every row of every file is checked before anything is written. The vocabulary is
`config/plant.yaml`: a skill, a shift or a PM task the plant file does not know
is refused rather than created, because two vocabularies fail to match in
silence (ADR-027). A date with no time is midnight in the plant's time zone,
which is known, so it is not a guess (ADR-028). One transaction writes all of
it, so a file with one bad line leaves the database as it was.

A technician with no account gets one with a random password, printed once.
The plant's own identity system replaces that through ADR-036's adapter.
"""

from __future__ import annotations

import argparse
import csv
import os
import secrets
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import Path
from typing import Any

from psycopg import Connection, connect

from pdm.contracts import (
    PMTaskRef,
    Role,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth import repo as auth_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.work import repo as work_repo
from pdm.work.repo import PmTaskDefinition

TECHNICIAN_COLUMNS = ("user_id", "display_name", "skills")
ROSTER_COLUMNS = ("date", "shift_id", "user_id", "available_minutes")
PM_HISTORY_COLUMNS = ("pm_task_ref", "last_done")

_YES = {"yes", "y", "true", "1", ""}
_NO = {"no", "n", "false", "0"}


@dataclass(frozen=True)
class Person:
    technician: Technician
    display_name: str


@dataclass
class PlantData:
    people: list[Person] = field(default_factory=list)
    roster: list[ShiftAssignment] = field(default_factory=list)
    pm_done: list[tuple[PMTaskRef, datetime]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _rows(
    lines: Iterable[str], columns: tuple[str, ...], name: str, problems: list[str]
) -> list[tuple[int, dict[str, str]]]:
    reader = csv.DictReader(lines)
    header = {column.strip() for column in (reader.fieldnames or ())}
    missing = [column for column in columns if column not in header]
    if missing:
        problems.append(
            f"{name}: the header must name {', '.join(columns)}; missing {', '.join(missing)}"
        )
        return []
    return [
        (reader.line_num, {key.strip(): (value or "").strip() for key, value in row.items() if key})
        for row in reader
    ]


def read_technicians(
    lines: Iterable[str], *, skills: frozenset[SkillId], name: str = "technicians.csv"
) -> PlantData:
    data = PlantData()
    seen: set[str] = set()
    for line, row in _rows(lines, TECHNICIAN_COLUMNS, name, data.problems):
        where = f"{name}:{line}"
        user = row.get("user_id", "")
        if not user:
            data.problems.append(f"{where}: empty user_id")
            continue
        if user in seen:
            data.problems.append(f"{where}: {user} appears twice")
            continue
        seen.add(user)
        held = {
            SkillId(skill.strip()) for skill in row.get("skills", "").split(";") if skill.strip()
        }
        unknown = sorted(held - skills)
        if unknown:
            data.problems.append(
                f"{where}: skill {', '.join(unknown)} is not in plant.yaml "
                f"({', '.join(sorted(skills))})"
            )
            continue
        active = row.get("active", "").lower()
        if active not in _YES | _NO:
            data.problems.append(f"{where}: active must be yes or no, not {row['active']!r}")
            continue
        data.people.append(
            Person(
                technician=Technician(
                    user=UserId(user), skills=frozenset(held), active=active in _YES
                ),
                display_name=row.get("display_name") or user,
            )
        )
    return data


def shift_minutes(shifts: Mapping[Any, Any]) -> dict[str, int]:
    """plant.yaml's shifts, each with its length in minutes."""
    return {str(key): int(shift.length.total_seconds() // 60) for key, shift in shifts.items()}


def read_roster(
    lines: Iterable[str],
    *,
    shifts: Mapping[str, int],
    technicians: frozenset[str],
    name: str = "roster.csv",
) -> PlantData:
    """`shifts` is each shift in plant.yaml and how many minutes long it is."""
    data = PlantData()
    for line, row in _rows(lines, ROSTER_COLUMNS, name, data.problems):
        where = f"{name}:{line}"
        try:
            on_date = date.fromisoformat(row["date"])
        except ValueError:
            data.problems.append(f"{where}: date {row['date']!r} is not YYYY-MM-DD")
            continue
        if row["shift_id"] not in shifts:
            data.problems.append(
                f"{where}: shift {row['shift_id']!r} is not in plant.yaml "
                f"({', '.join(sorted(shifts))})"
            )
            continue
        if row["user_id"] not in technicians:
            data.problems.append(
                f"{where}: {row['user_id']!r} is not a technician, in technicians.csv or "
                "already in the database"
            )
            continue
        try:
            minutes = int(row["available_minutes"])
        except ValueError:
            minutes = 0
        if minutes <= 0:
            data.problems.append(
                f"{where}: available_minutes must be a whole number above zero, "
                f"not {row['available_minutes']!r}"
            )
            continue
        if minutes > shifts[row["shift_id"]]:
            data.problems.append(
                f"{where}: available_minutes {minutes} is more than the whole "
                f"{row['shift_id']} shift, which is {shifts[row['shift_id']]} minutes"
            )
            continue
        data.roster.append(
            ShiftAssignment(
                shift_id=ShiftId(row["shift_id"]),
                on_date=on_date,
                technician=UserId(row["user_id"]),
                available_minutes=minutes,
            )
        )
    return data


def read_pm_history(
    lines: Iterable[str],
    *,
    tasks: frozenset[str],
    zone: tzinfo,
    now: datetime,
    name: str = "pm_history.csv",
) -> PlantData:
    data = PlantData()
    for line, row in _rows(lines, PM_HISTORY_COLUMNS, name, data.problems):
        where = f"{name}:{line}"
        if row["pm_task_ref"] not in tasks:
            data.problems.append(
                f"{where}: PM task {row['pm_task_ref']!r} is not in plant.yaml "
                f"({', '.join(sorted(tasks)) or 'none'})"
            )
            continue
        raw = row["last_done"]
        try:
            done = (
                datetime.combine(date.fromisoformat(raw), time(), tzinfo=zone)
                if len(raw) == 10
                else datetime.fromisoformat(raw)
            )
        except ValueError:
            data.problems.append(f"{where}: last_done {raw!r} is not a date or ISO 8601 time")
            continue
        if done.tzinfo is None:
            data.problems.append(f"{where}: last_done {raw!r} has a time but no UTC offset")
            continue
        if done > now:
            data.problems.append(f"{where}: last_done {raw!r} is in the future")
            continue
        data.pm_done.append((PMTaskRef(row["pm_task_ref"]), done))
    return data


def _existing_technicians(conn: Connection[Any]) -> frozenset[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM technician")
        return frozenset(str(row[0]) for row in cur.fetchall())


def _read(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    return path.read_text(encoding="utf-8-sig").splitlines(keepends=True)


def main(argv: list[str] | None = None, environ: Mapping[str, str] = os.environ) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--technicians", type=Path)
    parser.add_argument("--roster", type=Path)
    parser.add_argument("--pm-history", type=Path)
    parser.add_argument("--config", type=Path, default=Path(environ.get("CONFIG_DIR", "config")))
    args = parser.parse_args(argv)
    if not (args.technicians or args.roster or args.pm_history):
        parser.error("give at least one of --technicians, --roster, --pm-history")

    url = environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1

    config = load_config(args.config)
    clock = SystemClock()
    now = clock.now()
    skills = frozenset(SkillId(str(skill)) for skill in config.skills)

    with connect(url) as conn:
        people = PlantData()
        technicians_lines = _read(args.technicians)
        if technicians_lines is not None:
            people = read_technicians(technicians_lines, skills=skills, name=args.technicians.name)

        roster = PlantData()
        roster_lines = _read(args.roster)
        if roster_lines is not None:
            known = _existing_technicians(conn) | {str(p.technician.user) for p in people.people}
            roster = read_roster(
                roster_lines,
                shifts=shift_minutes(config.shifts),
                technicians=known,
                name=args.roster.name,
            )

        history = PlantData()
        history_lines = _read(args.pm_history)
        if history_lines is not None:
            history = read_pm_history(
                history_lines,
                tasks=frozenset(str(task.pm_task_ref) for task in config.pm_tasks),
                zone=config.timezone,
                now=now,
                name=args.pm_history.name,
            )

        problems = people.problems + roster.problems + history.problems
        if problems:
            print("nothing was written; fix these and run it again:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return 2

        auth = Authentication(LocalAccounts(), clock)
        created: list[tuple[str, str]] = []
        for person in people.people:
            user = person.technician.user
            if auth_repo.account(conn, user) is None:
                password = secrets.token_urlsafe(9)
                auth.create_account(
                    conn,
                    user=user,
                    display_name=person.display_name,
                    role=Role.TECHNICIAN,
                    password=password,
                )
                created.append((str(user), password))
            dispatch_repo.add_technician(conn, person.technician, known_skills=skills, now=now)
        for assignment in roster.roster:
            dispatch_repo.assign_to_shift(conn, assignment)
        if history.pm_done:
            work_repo.register_pm_tasks(
                conn,
                [
                    PmTaskDefinition(
                        pm_task_ref=task.pm_task_ref,
                        machine_id=task.machine_id,
                        symptom_code=task.symptom_code,
                        interval=timedelta(hours=task.interval_hours),
                    )
                    for task in config.pm_tasks
                ],
                now=now,
            )
        moved = sum(work_repo.record_pm_done(conn, ref, at=at) for ref, at in history.pm_done)
        conn.commit()

    print(f"technicians: {len(people.people)} written")
    print(f"roster lines: {len(roster.roster)} written")
    if history.pm_done:
        print(
            f"PM history: {moved} of {len(history.pm_done)} moved a task's clock "
            "(a date earlier than one already recorded changes nothing)"
        )
    if created:
        print("\naccounts created - give each person their password, it is not shown again:")
        for account, password in created:
            print(f"  {account:16} {password}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

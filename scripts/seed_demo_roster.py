"""Technicians and a shift's roster, for a demo and for nothing else (ADR-078).

    DATABASE_URL=... uv run python scripts/seed_demo_roster.py

**The three people this creates do not exist.** That sentence is the reason this
is a separate script rather than a flag on `seed_demo.py`. Accounts and manuals
are things an operator can defensibly seed on the plant's own machine; a
technician row is a person, work is placed on it, and the roster is the one table
here the plant will certainly replace with its own (ADR-078 §1).

What it buys is the middle of the system. Without a roster `dispatch()` ranks the
queue and assigns none of it, so the shift lead has nothing to confirm and the
technician's screen says there is no work - on a plant that has just raised five
Findings. The load gate, the five-term score and the confirmation record are all
invisible until somebody can be sent.

Run it **after** `seed_demo.py`, and after the screen checks if you are running
those: they truncate `account` and `technician` on their way through.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from psycopg import connect

from pdm.contracts import Role, ShiftAssignment, SkillId, Technician, UserId, shift_at
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth import repo as auth_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config

# Three, not one: one technician makes the load gate a straight line, and three
# is the smallest roster where ADR-011's three bands are reachable in a single
# shift - which is the behaviour the advisor described most concretely. It is
# also the roster `docs/results/comparison.md` measured against (ADR-078 §2).
#
# Between them they hold **all four** skills in `plant.yaml`. A playbook's
# `required_skill` is chosen at drafting time and is not knowable here, and a
# round that finds nobody with the skill correctly leaves the job unassigned -
# which on a demo screen is indistinguishable from a bug (ADR-078 §3).
TECHNICIANS = [
    (
        UserId("tech-1"),
        "Somchai (technician)",
        "demo-technician",
        ("robot_mechanical", "electrical"),
    ),
    (
        UserId("tech-2"),
        "Wichai (technician)",
        "demo-technician-2",
        ("robot_controls", "electrical"),
    ),
    (
        UserId("tech-3"),
        "Pimchanok (technician)",
        "demo-technician-3",
        ("hydraulics", "robot_mechanical"),
    ),
]

# Half of an eight-hour shift. Provenance: ADR-078 §4 - a recorded decision and
# not a measurement. A technician also walks the line, runs PM rounds, hands over
# and eats; counting the whole shift as repair capacity makes `load_ratio` read
# low and the gate release more work than there are hours for.
AVAILABLE_MINUTES = 240

# The world this script extends. Their absence is the one fact available that
# says "this is not the demo database", and it is what §6 refuses on.
SEEDED_BY_SEED_DEMO = (UserId("tech-1"), UserId("eng-1"), UserId("sup-1"), UserId("op-1"))


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1

    config = load_config(Path(os.environ.get("CONFIG_DIR", "config")))
    clock = SystemClock()
    now = clock.now()
    auth = Authentication(LocalAccounts(), clock)

    # Every skill named here has to exist in plant.yaml, or the round quietly
    # matches nobody. Checked before anything is written, because a roster that
    # is half correct is worse than none: the missing half looks like a
    # scheduling bug.
    unknown = sorted(
        {skill for _, _, _, skills in TECHNICIANS for skill in skills}
        - {str(skill) for skill in config.skills}
    )
    if unknown:
        print(f"skills not in plant.yaml: {', '.join(unknown)}")
        return 1

    window = shift_at(config.shifts.values(), now, config.timezone)
    if window is None:
        local = now.astimezone(config.timezone)
        print(
            f"no shift in plant.yaml covers {local:%H:%M} local time, so there is no roster "
            f"to write. A plant that runs sixteen hours a day has eight with no shift; this "
            f"is that answer rather than an error."
        )
        return 1

    with connect(url) as conn:
        missing = [user for user in SEEDED_BY_SEED_DEMO if auth_repo.account(conn, user) is None]
        if missing:
            print(f"this is not a seeded demo database: no account for {', '.join(missing)}")
            print("run `uv run python scripts/seed_demo.py` first (ADR-078 section 6)")
            return 1

        written: list[str] = []
        for user, name, password, skills in TECHNICIANS:
            if auth_repo.account(conn, user) is None:
                auth.create_account(
                    conn, user=user, display_name=name, role=Role.TECHNICIAN, password=password
                )
                note = f"account created, password {password}"
            else:
                note = "account already there"

            dispatch_repo.add_technician(
                conn,
                Technician(user=user, skills=frozenset(SkillId(skill) for skill in skills)),
                now=now,
            )
            dispatch_repo.assign_to_shift(
                conn,
                ShiftAssignment(
                    shift_id=window.shift_id,
                    on_date=window.on_date,
                    technician=user,
                    available_minutes=AVAILABLE_MINUTES,
                ),
            )
            written.append(f"  {user:8} {', '.join(skills):32} {note}")

        conn.commit()

    # After the commit, never before: a failure halfway through rolls the whole
    # transaction back, and somebody who has already been told a password exists
    # has no way to find out that it does not (the pattern `seed_demo.py` set).
    print(f"roster for shift {window.shift_id} on {window.on_date}")
    print(f"  {window.starts_at:%Y-%m-%d %H:%M} to {window.ends_at:%H:%M} UTC")
    for line in written:
        print(line)
    shift_minutes = int(config.shifts[window.shift_id].length.total_seconds() // 60)
    print(f"\n{AVAILABLE_MINUTES} minutes each, of a {shift_minutes}-minute shift.")
    print("That split is an assumption recorded in ADR-078, not a measurement.")
    print("\nThese three people do not exist. This script is for a demo; the plant's")
    print("own roster replaces every row it writes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

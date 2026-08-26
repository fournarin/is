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

# The same three people `pdm.sim.scenarios.LINE_A_ONE_SHIFT` puts on a shift -
# same names, same count, same capacity - so that the demo and the measurement in
# `docs/results/comparison.md` describe one plant rather than two (ADR-078 §2).
#
# tech-1 is `seed_demo.py`'s account; the other two are created here.
TECHNICIANS = [
    (UserId("tech-1"), "Somchai (technician)", "demo-technician"),
    (UserId("tech-2"), "Wichai (technician)", "demo-technician-2"),
    (UserId("tech-3"), "Pimchanok (technician)", "demo-technician-3"),
]

# Every skill in plant.yaml, to each of them, which is what the simulator's
# roster does and for the reason it gives: a ticket priced from
# `fallback_minutes` carries no required skill at all, and a round that finds
# nobody holding a skill correctly leaves the job unassigned - an answer that
# reads on a demo screen as a bug. The cost is stated rather than discovered:
# nothing in this demo exercises skill matching (ADR-078 §3).

# The whole shift. Provenance: `src/pdm/sim/scenarios.py`, which assigns
# `available_minutes` the full length of the shift, and whose runs are every
# figure in `docs/results/comparison.md`. A technician is not really available
# for eight hours of repair work - but a demo that assumed otherwise would put a
# different capacity under the same load gate the measurement used, and the two
# would stop describing the same plant (ADR-078 §4).
AVAILABLE_MINUTES = 480

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

    # A plant with no skills configured would produce three technicians who can
    # do nothing, and a round that leaves every job unassigned for a reason that
    # sounds like a scheduling defect. Refused before anything is written.
    if not config.skills:
        print("plant.yaml lists no skills, so a roster from it can perform nothing")
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

        skills = frozenset(SkillId(str(skill)) for skill in config.skills)
        written: list[str] = []
        for user, name, password in TECHNICIANS:
            if auth_repo.account(conn, user) is None:
                auth.create_account(
                    conn, user=user, display_name=name, role=Role.TECHNICIAN, password=password
                )
                note = f"account created, password {password}"
            else:
                note = "account already there"

            dispatch_repo.add_technician(conn, Technician(user=user, skills=skills), now=now)
            dispatch_repo.assign_to_shift(
                conn,
                ShiftAssignment(
                    shift_id=window.shift_id,
                    on_date=window.on_date,
                    technician=user,
                    available_minutes=AVAILABLE_MINUTES,
                ),
            )
            written.append(f"  {user:8} {note}")

        conn.commit()

    # After the commit, never before: a failure halfway through rolls the whole
    # transaction back, and somebody who has already been told a password exists
    # has no way to find out that it does not (the pattern `seed_demo.py` set).
    print(f"roster for shift {window.shift_id} on {window.on_date}")
    print(f"  {window.starts_at:%Y-%m-%d %H:%M} to {window.ends_at:%H:%M} UTC")
    for line in written:
        print(line)
    shift_minutes = int(config.shifts[window.shift_id].length.total_seconds() // 60)
    whole = " (the whole of it)" if AVAILABLE_MINUTES == shift_minutes else ""
    print(f"\n{AVAILABLE_MINUTES} available minutes each of a {shift_minutes}-minute shift{whole},")
    print("holding", end=" ")
    print(f"every skill in plant.yaml: {', '.join(sorted(str(s) for s in config.skills))}")
    print("Those are the simulator's assumptions, so this demo and the comparison in")
    print("docs/results/ describe the same shift (ADR-078).")
    print("\nThese three people do not exist. This script is for a demo; the plant's")
    print("own roster replaces every row it writes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

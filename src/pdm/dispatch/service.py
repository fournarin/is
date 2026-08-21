"""One scheduling round: read the world, decide, write what was decided.

`dispatch()` is a pure function of its arguments (ADR-045 §6) and this is what
gives it arguments. The split is not tidiness: slice 7 compares three policies
over hundreds of scenarios and Loop 6 replays past rounds against different
weights, and both need the deciding half to be replayable exactly. A round that
read a clock or a table from inside the algorithm would make every measurement
in the report irreproducible, and would do it quietly.

**The whole round is one transaction** (ADR-017). The reads, the writes and the
appointment for the next round commit together or not at all, so a round cannot
half-happen: there is no state in which two of five placements were written and
the other three were forgotten, and no state in which a round ran without
booking its successor.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection

from pdm.contracts import ShiftDefinition, shift_at
from pdm.dispatch import repo
from pdm.dispatch.domain import Queued, Round, dispatch
from pdm.platform.clock import Clock
from pdm.platform.config.loader import Config
from pdm.work import repo as work_repo

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoundReport:
    """What one round did, for the log and for a test to assert on.

    `moved_on` is the count of orders the round meant to place and could not,
    because somebody accepted them between the read and the write. Not an error:
    the next round ranks what is true then. It is reported because a round that
    silently placed fewer orders than it decided would be indistinguishable from
    a round that decided fewer.
    """

    at: datetime
    round: Round
    placed: tuple[str, ...] = ()
    moved_on: tuple[str, ...] = field(default=())

    @property
    def worth_reporting(self) -> bool:
        """A quiet round is the normal case - one every five minutes, for ever -
        and a line each would bury the rounds that did something."""
        return bool(self.placed or self.moved_on or self.round.held or self.round.unassigned)


class DispatchRounds:
    """Layer 3 in a process.

    Takes its collaborators rather than reaching for them, so a test can run a
    round against a real database without a worker, and so the composition root
    stays the only place that decides what talks to what.
    """

    def __init__(self, clock: Clock, config: Config) -> None:
        self.clock = clock
        self.config = config
        self._zone = ZoneInfo(config.plant.timezone)
        self._shifts = tuple(
            ShiftDefinition(
                shift_id=shift.shift_id, starts_at=shift.starts_at, ends_at=shift.ends_at
            )
            for shift in config.plant.shifts
        )

    def run(self, conn: Connection[Any]) -> RoundReport:
        """Decide and write, in the caller's transaction."""
        now = self.clock.now()
        window = shift_at(self._shifts, now, self._zone)

        queue = [
            Queued(ref=ref, order=order, created_at=created_at)
            for ref, order, created_at in work_repo.open_orders(conn)
        ]
        # No shift covers this moment: the plant is not running, and `dispatch()`
        # is told so through `shift_id=None` rather than being handed an empty
        # roster it would have to guess about (ADR-045 §3).
        assignments = (
            repo.roster(conn, shift_id=window.shift_id, on_date=window.on_date)
            if window is not None
            else []
        )

        decided = dispatch(
            queue,
            technicians=repo.technicians(conn),
            assignments=[(one.technician, one.available_minutes) for one in assignments],
            config=self.config,
            now=now,
            shift_id=window.shift_id if window is not None else None,
            on_date=window.on_date if window is not None else None,
        )

        placed: list[str] = []
        moved_on: list[str] = []
        for placement in decided.placed:
            # Only an order still queued is written. Work somebody accepted
            # between this round's read and its write keeps its assignee
            # (ADR-045 §4), and the round says how many it let go rather than
            # reporting a placement that did not happen.
            (placed if repo.place(conn, placement) else moved_on).append(placement.ref)

        return RoundReport(at=now, round=decided, placed=tuple(placed), moved_on=tuple(moved_on))


def describe(report: RoundReport) -> str:
    """The sentence ADR-011 kept the gate separate in order to be able to write,
    plus what became of the decision once it met the database."""
    parts = [report.round.summary]
    if report.moved_on:
        parts.append(f"{len(report.moved_on)} were accepted while the round was deciding")
    return "; ".join(parts)

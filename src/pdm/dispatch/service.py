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
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg import Connection

from pdm.contracts import Role, ShiftDefinition, UserId, WorkOrderStatus, shift_at
from pdm.dispatch import repo
from pdm.dispatch.domain import Queued, Round, dispatch
from pdm.dispatch.proposals import Proposal, ProposalState
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
    # Decided and waiting for a supervisor (ADR-071). Kept apart from `placed`
    # because layer 4 is handed the second one and must not be handed this one:
    # a ticket nobody has approved must not reach a CMMS, and the difference
    # between the two lists is the whole of that guarantee at this seam.
    proposed: tuple[str, ...] = field(default=())
    # Proposals this round swept because nobody answered them, and whose orders
    # are back in the queue it then ranked.
    expired: tuple[str, ...] = field(default=())

    @property
    def worth_reporting(self) -> bool:
        """A quiet round is the normal case - one every five minutes, for ever -
        and a line each would bury the rounds that did something."""
        return bool(
            self.placed
            or self.proposed
            or self.expired
            or self.moved_on
            or self.round.held
            or self.round.unassigned
        )


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
        """Sweep, decide and write, in the caller's transaction."""
        expired = self._sweep(conn)
        decided = self.decide(conn)

        # The one line where the two confirmation modes differ (ADR-071 §2).
        # Everything above it - the sweep, the queue, the gate, the score, the
        # crewing - has already happened identically.
        holds_for_a_person = self.config.policy.dispatch.confirmation == "supervisor"
        status = WorkOrderStatus.PROPOSED if holds_for_a_person else WorkOrderStatus.ASSIGNED

        placed: list[str] = []
        proposed: list[str] = []
        moved_on: list[str] = []
        for placement in decided.placed:
            # Only an order still queued is written. Work somebody accepted
            # between this round's read and its write keeps its assignee
            # (ADR-045 §4), and the round says how many it let go rather than
            # reporting a placement that did not happen.
            if not repo.place(conn, placement, status=status):
                moved_on.append(placement.ref)
                continue
            if not holds_for_a_person:
                placed.append(placement.ref)
                continue
            repo.propose(
                conn,
                Proposal(
                    work_order_ref=placement.ref,
                    proposed_at=decided.at,
                    assignees=placement.assignees,
                    priority_score=placement.priority_score,
                    priority_reason=placement.priority_reason,
                    # The round it was decided against, copied on because a round
                    # is never stored (ADR-050) and six weeks later there is
                    # nothing else to read the decision back against.
                    band=decided.band,
                    load_ratio=decided.load_ratio,
                    shift_id=decided.shift_id,
                    on_date=decided.on_date,
                ),
            )
            proposed.append(placement.ref)

        return RoundReport(
            at=decided.at,
            round=decided,
            placed=tuple(placed),
            moved_on=tuple(moved_on),
            proposed=tuple(proposed),
            expired=expired,
        )

    def _sweep(self, conn: Connection[Any]) -> tuple[str, ...]:
        """Return the orders nobody answered for to the queue (ADR-071 §6).

        Before `decide`, and in the round's transaction, so the queue the round
        is handed already contains what the sweep let go rather than seeing it
        one cadence later.

        **It runs in `automatic` too**, where no round writes a proposal. A plant
        that switches the mode mid-shift would otherwise strand every open
        proposal in a status only a confirmation can leave, holding its
        technicians' minutes against a screen that has stopped asking about them -
        a shift that reads full for work nobody will ever be sent to do. Sweeping
        unconditionally costs one indexed query against an empty partial index.
        """
        now = self.clock.now()
        cutoff = now - timedelta(minutes=self.config.policy.dispatch.proposal_expires_minutes)
        refs = repo.expire_proposals(conn, proposed_before=cutoff, at=now)
        # Only what was actually returned. `return_to_queue` writes nothing to an
        # order that is no longer `proposed`, which is the narrow case of a
        # supervisor confirming one in the instant this sweep ran: the work stays
        # theirs, and the round does not report having released it. One process
        # runs rounds (ADR-026), so this is the only writer the sweep races with.
        return tuple(ref for ref in refs if repo.return_to_queue(conn, ref))

    def decide(self, conn: Connection[Any]) -> Round:
        """What a round would do, without doing any of it (ADR-050).

        The read path for the gate's report calls this, so the sentence a
        supervisor is shown comes from the same function that schedules rather
        than from a second implementation that could drift from it. Writes
        nothing, so it is safe on a read-only request.
        """
        now = self.clock.now()
        window = shift_at(self._shifts, now, self._zone)

        # Read here rather than inside `dispatch()`, which may not read a table
        # (invariant 10, ADR-045 §6). The released refs are part of the world the
        # round is handed, in the same sense the roster is: this is the half of
        # the split that talks to the database (ADR-059).
        let_through = repo.released(conn)
        queue = [
            Queued(ref=ref, order=order, created_at=created_at, released=ref in let_through)
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

        return dispatch(
            queue,
            technicians=repo.technicians(conn),
            assignments=[(one.technician, one.available_minutes) for one in assignments],
            config=self.config,
            now=now,
            shift_id=window.shift_id if window is not None else None,
            on_date=window.on_date if window is not None else None,
        )


def describe(report: RoundReport) -> str:
    """The sentence ADR-011 kept the gate separate in order to be able to write,
    plus what became of the decision once it met the database."""
    parts = [report.round.summary]
    if report.proposed:
        parts.append(f"{len(report.proposed)} waiting for a supervisor to confirm")
    if report.expired:
        parts.append(f"{len(report.expired)} proposal(s) expired unanswered and are queued again")
    if report.moved_on:
        parts.append(f"{len(report.moved_on)} were accepted while the round was deciding")
    return "; ".join(parts)


class NoProposal(LookupError):
    """Nothing is waiting for an answer about this order."""


class AlreadyAnswered(Exception):
    """Somebody got there first.

    Two supervisors on the same screen is the ordinary case rather than a race
    worth locking against, and the honest answer names what happened instead of
    overwriting the first decision with the second.
    """


class Confirmations:
    """The half of layer 3 that is a person (ADR-071).

    Separate from `DispatchRounds` because the two run in different processes on
    different clocks: a round is a job in worker-runtime every five minutes, and
    this is somebody pressing a button in a request. What they share is the
    repository and the rule that both write in the caller's transaction.

    Neither method sends anything anywhere. Queueing the delivery of a confirmed
    ticket belongs to the composition root, which is what lets `.importlinter`
    keep `pdm.dispatch` from importing `pdm.sinks` at all (ADR-068, ADR-071 §5).

    **Both methods write the order before they write the record, and that order
    is load-bearing.** An `HTTPException` commits the request's transaction
    rather than rolling it back (`api/deps.py::connection`, ADR-019), so a
    refusal raised after a write would commit the write. The conditional UPDATE
    on the order is therefore attempted first: when it matches nothing, nothing
    has been written and the refusal costs nothing; when it matches, the answer
    is ours and the record follows in the same transaction.
    """

    def __init__(self, clock: Clock) -> None:
        self.clock = clock

    def confirm(self, conn: Connection[Any], ref: str, *, by: UserId, role: Role) -> Proposal:
        """A supervisor agrees, and the job becomes the technician's."""
        proposal = self._pending(conn, ref)
        if not repo.confirm_placement(conn, ref):
            # The proposal was open and the order is not `proposed` any more.
            # Reachable through a sweep committed between the two reads, and
            # refused rather than forced: confirming an order that has gone back
            # to the queue would assign somebody to a decision that no longer
            # has a crew on it.
            raise AlreadyAnswered(f"{ref} ไม่ได้รอการยืนยันแล้ว รอบถัดไปจะจัดลำดับใหม่")
        repo.settle_proposal(
            conn, ref, state=ProposalState.CONFIRMED, at=self.clock.now(), by=by, role=role
        )
        return proposal

    def reject(
        self, conn: Connection[Any], ref: str, *, by: UserId, role: Role, reason: str
    ) -> Proposal:
        """A supervisor does not, and the order goes back into the queue now.

        Not held, not cooled off, not marked so that it is proposed differently
        next time (ADR-071 §4). If the round proposes the same pairing again that
        is information rather than a defect: nothing about the shift has changed,
        and a second rejection with a second reason is evidence about the score
        rather than noise.
        """
        proposal = self._pending(conn, ref)
        if not repo.return_to_queue(conn, ref):
            raise AlreadyAnswered(f"{ref} ไม่ได้รอการยืนยันแล้ว รอบถัดไปจะจัดลำดับใหม่")
        repo.settle_proposal(
            conn,
            ref,
            state=ProposalState.REJECTED,
            at=self.clock.now(),
            by=by,
            role=role,
            reason=reason,
        )
        return proposal

    def _pending(self, conn: Connection[Any], ref: str) -> Proposal:
        proposal = repo.pending_proposal(conn, ref)
        if proposal is None:
            raise NoProposal(f"{ref} ไม่ได้รอการยืนยันแล้ว อาจมีคนตอบไปก่อน ลองโหลดหน้าใหม่")
        return proposal

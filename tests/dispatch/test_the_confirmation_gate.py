"""A round proposes and a person decides (ADR-071, #81).

The advisor was asked on 2026-08-23 who presses the button and answered that a
person should at first, and that automatic approval is something to consider
later once there is a record to judge it by. This file is that flow, against a
real PostgreSQL, and four of its tests are the ones that would fail if any part
of the argument were dropped:

  * `TestNothingIsAnybodysJobYet` - the whole point. A round in `supervisor` mode
    writes a decision nobody has agreed to, and neither the technician's screen
    nor layer 4's queue may contain it.
  * `TestAProposalHoldsItsCapacity` - a proposal that did not consume its
    technician's minutes would make the shift read emptier than it is, and
    ADR-011's gate answers an empty-looking shift by releasing more work. The
    supervisor's screen would fill with duplicates of the same decision.
  * `TestAProposalNobodyAnswersGoesBack` - a supervisor who goes home must not
    leave a shift committed to work nobody will be sent to do (ADR-023's
    argument, one layer up).
  * `TestTheJobStaysOnTheScreenAfterARound` - the regression test for the defect
    ADR-071 §7 records. The technician's screen used to filter a recomputed
    round, and `dispatch()` only places what is still `queued`, so a job vanished
    at the moment the system decided to give it to somebody. The rehearsal could
    not see it because it stops `worker-runtime` while the screen checks run.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect
from psycopg.rows import dict_row

from pdm.contracts import (
    FindingRef,
    MachineId,
    MachineModel,
    Role,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderStatus,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.proposals import ProposalState
from pdm.dispatch.service import (
    AlreadyAnswered,
    Confirmations,
    DispatchRounds,
    NoProposal,
    NotSetAside,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.work import TransitionRefused, WorkOrders
from pdm.work import repo as work_repo
from tests.modes import automatic

pytestmark = pytest.mark.db

# 08:00 UTC is 15:00 in Bangkok: the afternoon shift, filed under the 3rd
# (ADR-045 §7). Chosen so the round has a roster to find at all.
NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
AFTERNOON = ShiftId("afternoon")
TODAY = date(2026, 3, 3)

BUFFERED = MachineId("MC-001")
BOTTLENECK = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")

ANA = UserId("tech-ana")
BEN = UserId("tech-ben")
SUP = UserId("sup-1")
ALL_SKILLS = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
WINDOW = timedelta(minutes=CONFIG.policy.dispatch.proposal_expires_minutes)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE work_order, dispatch_proposal, ticket_delivery, finding, job, "
            "shift_assignment, technician CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def rounds(clock: SimulatedClock) -> DispatchRounds:
    """The shipped configuration, which is `confirmation: supervisor`."""
    return DispatchRounds(clock, CONFIG)


@pytest.fixture
def confirming(clock: SimulatedClock) -> Confirmations:
    return Confirmations(clock)


@pytest.fixture
def orders(clock: SimulatedClock) -> WorkOrders:
    return WorkOrders(clock, fallback_minutes=FALLBACK)


def _crew(conn: Connection[Any], *users: UserId, minutes: int = 480) -> None:
    for user in users:
        dispatch_repo.add_technician(
            conn, Technician(user=user, skills=ALL_SKILLS), known_skills=ALL_SKILLS, now=NOW
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=AFTERNOON, on_date=TODAY, technician=user, available_minutes=minutes
            ),
        )


def _ticket(
    orders: WorkOrders,
    conn: Connection[Any],
    *,
    machine_id: MachineId = BUFFERED,
    severity: Severity = Severity.MEDIUM,
) -> str:
    """A reported fault, so a ticket exists without layer 1 being involved
    (ADR-010: most work has no Finding behind it)."""
    return orders.from_report(
        conn,
        machine_id=machine_id,
        machine_model=R2000,
        severity=severity,
        reported_by=SUP,
        description="reported in a test",
    ).ref


def _status(conn: Connection[Any], ref: str) -> WorkOrderStatus:
    order = work_repo.get(conn, ref)
    assert order is not None
    return order.status


def _proposal_rows(conn: Connection[Any]) -> list[dict[str, Any]]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM dispatch_proposal ORDER BY proposal_id")
        return [dict(row) for row in cur.fetchall()]


def _outstanding(conn: Connection[Any]) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT work_order_ref FROM ticket_delivery ORDER BY work_order_ref")
        return [str(row[0]) for row in cur.fetchall()]


class TestNothingIsAnybodysJobYet:
    """What a round in `supervisor` mode may and may not have done."""

    def test_a_round_proposes_instead_of_placing(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)

        report = rounds.run(conn)

        assert report.proposed == (ref,)
        assert report.placed == ()
        assert _status(conn, ref) is WorkOrderStatus.PROPOSED

    def test_the_proposal_keeps_what_the_round_decided_and_the_round_it_decided_in(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """A round is never stored (ADR-050), so the four columns naming the
        shift it was decided against are the only way to read the decision back
        in the context that produced it."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)

        decided = rounds.run(conn).round
        (row,) = _proposal_rows(conn)

        assert row["work_order_ref"] == ref
        assert [one["user"] for one in row["assignees"]] == [str(ANA)]
        assert row["priority_reason"] != ""
        assert row["state"] == ProposalState.PENDING.value
        assert row["band"] == decided.band.value
        assert row["load_ratio"] == pytest.approx(decided.load_ratio)
        assert row["shift_id"] == str(AFTERNOON)
        assert row["on_date"] == TODAY
        # Nobody has answered, so nothing may name anybody.
        assert row["decided_at"] is None and row["decided_by"] is None

    def test_the_technician_is_not_shown_work_nobody_confirmed(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        _crew(conn, ANA)
        _ticket(orders, conn)
        rounds.run(conn)

        assert work_repo.assigned_to(conn, ANA) == []

    def test_a_technician_who_reaches_it_anyway_is_told_why_not(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
    ) -> None:
        """Refused with a sentence rather than by the job doing nothing when
        pressed - somebody who kept a link is owed the reason (ADR-071 §7)."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        with pytest.raises(TransitionRefused, match="รอหัวหน้ากะยืนยัน"):
            orders.accept(conn, ref, user=ANA)

    def test_nothing_is_queued_for_a_destination_before_it_is_confirmed(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """The failure the confirmation step exists to prevent, at the seam where
        it would be one argument in one call: `deliveries.run` is handed
        `report.placed`, and in this mode that list is empty (ADR-071 §5)."""
        _crew(conn, ANA)
        _ticket(orders, conn)

        report = rounds.run(conn)

        assert report.placed == ()
        assert _outstanding(conn) == []


class TestConfirming:
    def test_confirming_makes_it_the_technicians_job(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        assert _status(conn, ref) is WorkOrderStatus.ASSIGNED
        assert [one for one, _ in work_repo.assigned_to(conn, ANA)] == [ref]

    def test_the_record_says_who_answered_and_when(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        (row,) = _proposal_rows(conn)
        assert row["state"] == ProposalState.CONFIRMED.value
        assert row["decided_by"] == str(SUP)
        assert row["decided_role"] == Role.SUPERVISOR.value
        assert row["decided_at"] == NOW

    def test_the_second_supervisor_is_told_rather_than_overwriting_the_first(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        """Two people on the same screen is ordinary, not a race worth locking
        against. What matters is that the second press does not replace the first
        answer, and says so."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        with pytest.raises(NoProposal):
            confirming.confirm(conn, ref, by=UserId("sup-2"), role=Role.SUPERVISOR)

        (row,) = _proposal_rows(conn)
        assert row["decided_by"] == str(SUP)

    def test_a_confirmed_order_is_not_proposed_again(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        assert rounds.run(conn).proposed == ()
        assert len(_proposal_rows(conn)) == 1


class TestRejecting:
    def test_the_order_is_back_in_the_queue_with_nobody_on_it(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        """The assignees go with the rejection. Left behind, they would be
        counted against that person's capacity by the next round and offered to
        them by `accept` (ADR-056: `assignees` is the present tense)."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        confirming.reject(
            conn, ref, by=SUP, role=Role.SUPERVISOR, reason="ana is on the press line"
        )

        order = work_repo.get(conn, ref)
        assert order is not None
        assert order.status is WorkOrderStatus.QUEUED
        assert order.assignees == ()

    def test_the_reason_is_kept(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        confirming.reject(
            conn, ref, by=SUP, role=Role.SUPERVISOR, reason="ana is on the press line"
        )

        (row,) = _proposal_rows(conn)
        assert row["state"] == ProposalState.REJECTED.value
        assert row["reason"] == "ana is on the press line"

    def test_the_next_round_leaves_it_alone_for_the_rest_of_the_shift(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """ADR-120, replacing ADR-071 §4. Proposed again five minutes later, a
        "not now" read as a button that did nothing; the shift lead's answer
        lasts the shift, and the round says what it is not touching and why."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.reject(conn, ref, by=SUP, role=Role.SUPERVISOR, reason="not now")

        clock.advance(timedelta(seconds=CONFIG.policy.dispatch.round_seconds))
        report = rounds.run(conn)

        assert report.proposed == ()
        assert [(one.ref, one.why) for one in report.round.set_aside] == [(ref, "not now")]

    def test_brought_back_it_is_proposed_at_the_next_round(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.reject(conn, ref, by=SUP, role=Role.SUPERVISOR, reason="not now")
        since = rounds.shift_started_at()
        assert since is not None

        confirming.bring_back(conn, ref, by=SUP, since=since)
        clock.advance(timedelta(seconds=CONFIG.policy.dispatch.round_seconds))

        assert rounds.run(conn).proposed == (ref,)

    def test_bringing_back_what_was_never_set_aside_is_refused(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        since = rounds.shift_started_at()
        assert since is not None

        with pytest.raises(NotSetAside):
            confirming.bring_back(conn, ref, by=SUP, since=since)

    def test_the_next_shift_is_asked_afresh(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """The person who said no goes home; the next lead decides for themselves."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.reject(conn, ref, by=SUP, role=Role.SUPERVISOR, reason="not now")
        started = rounds.shift_started_at()
        assert started is not None

        while rounds.shift_started_at() == started:
            clock.advance(timedelta(hours=1))

        assert all(one.ref != ref for one in rounds.decide(conn).set_aside)

    def test_rejecting_queues_nothing_for_a_destination(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        confirming.reject(conn, ref, by=SUP, role=Role.SUPERVISOR, reason="not now")

        assert _outstanding(conn) == []


class TestAJobPutDown:
    def test_a_handed_over_job_is_offered_to_the_shift_lead_again(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """ADR-120. It used to become `handed_over`, which no round placed and no
        technician's screen listed: the owner's second trial put one down and it
        was never seen again."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)
        orders.accept(conn, ref, user=ANA)
        orders.start(conn, ref, user=ANA)
        orders.hand_over(conn, ref, user=ANA, note="cover off, waiting for the seal kit")

        clock.advance(timedelta(seconds=CONFIG.policy.dispatch.round_seconds))

        assert rounds.run(conn).proposed == (ref,)
        order = work_repo.get(conn, ref)
        assert order is not None
        assert order.handover_note == "cover off, waiting for the seal kit"


class TestAProposalHoldsItsCapacity:
    def test_a_second_round_does_not_propose_the_same_work_again(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        assert rounds.run(conn).proposed == (ref,)

        assert rounds.run(conn).proposed == ()
        assert len(_proposal_rows(conn)) == 1

    def test_the_shift_reads_as_committed_to_it(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """The reason the test above passes, stated as the number the gate reads.
        A proposal costing nothing would make the shift look emptier than it is,
        and ADR-011's gate answers that by releasing more work."""
        _crew(conn, ANA)
        _ticket(orders, conn)

        before = rounds.decide(conn).committed_minutes
        rounds.run(conn)
        after = rounds.decide(conn).committed_minutes

        assert before == after
        assert after > 0

    def test_a_technicians_remaining_minutes_are_spent_by_it(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """Ninety minutes of Ana against two jobs the fallback prices at sixty:
        the first is proposed to her and the second cannot be, because a proposal
        spends the same minutes an accepted job does."""
        _crew(conn, ANA, minutes=90)
        _ticket(orders, conn, severity=Severity.HIGH, machine_id=BOTTLENECK)
        _ticket(orders, conn, severity=Severity.HIGH)

        first = rounds.run(conn)
        assert len(first.proposed) == 1
        assert len(first.round.unassigned) == 1


class TestAProposalNobodyAnswersGoesBack:
    def test_it_expires_into_the_queue(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        clock.advance(WINDOW + timedelta(minutes=1))
        report = rounds.run(conn)

        assert ref in report.expired
        (expired, _) = _proposal_rows(conn)
        assert expired["state"] == ProposalState.EXPIRED.value
        # An expiry is the system noticing, so it names nobody.
        assert expired["decided_by"] is None
        assert expired["decided_at"] is not None

    def test_the_same_round_that_swept_it_ranks_it_again(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """The sweep runs before `decide`, in the round's transaction, so the
        work is available to the round that let it go rather than one cadence
        later (ADR-071 §6)."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        clock.advance(WINDOW + timedelta(minutes=1))
        report = rounds.run(conn)

        assert report.expired == (ref,)
        assert report.proposed == (ref,)

    def test_a_proposal_inside_its_window_is_left_alone(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)

        clock.advance(WINDOW - timedelta(minutes=1))
        report = rounds.run(conn)

        assert report.expired == ()
        assert _status(conn, ref) is WorkOrderStatus.PROPOSED

    def test_the_sweep_runs_in_automatic_too(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """A plant that switches the mode mid-shift would otherwise strand every
        open proposal in a status only a confirmation can leave, holding its
        technicians' minutes against a screen that has stopped asking."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        DispatchRounds(clock, CONFIG).run(conn)
        assert _status(conn, ref) is WorkOrderStatus.PROPOSED

        clock.advance(WINDOW + timedelta(minutes=1))
        report = DispatchRounds(clock, automatic(CONFIG)).run(conn)

        assert report.expired == (ref,)
        assert _status(conn, ref) is WorkOrderStatus.ASSIGNED


class TestAutomaticIsTheSameRoundWithoutTheQuestion:
    def test_it_places_and_records_no_proposal(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """Nothing was asked of anybody, so there is nothing to record. What the
        system is judged by in this mode is the record that already exists: the
        technician's disagreements (ADR-059) and the outcome of the work."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)

        report = DispatchRounds(clock, automatic(CONFIG)).run(conn)

        assert report.placed == (ref,)
        assert report.proposed == ()
        assert _proposal_rows(conn) == []
        assert _status(conn, ref) is WorkOrderStatus.ASSIGNED

    def test_the_two_modes_decide_the_same_thing(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        """The claim ADR-071 §2 makes about there being one path: the gate, the
        score and the crewing are identical, and only the status differs. Anything
        else moving would mean the mode had reached into `dispatch()`."""
        _crew(conn, ANA, BEN)
        _ticket(orders, conn, severity=Severity.HIGH, machine_id=BOTTLENECK)
        _ticket(orders, conn, severity=Severity.LOW)

        supervised = DispatchRounds(clock, CONFIG).decide(conn)
        automated = DispatchRounds(clock, automatic(CONFIG)).decide(conn)

        assert [one.ref for one in supervised.placed] == [one.ref for one in automated.placed]
        assert [one.priority_reason for one in supervised.placed] == [
            one.priority_reason for one in automated.placed
        ]
        assert [one.assignees for one in supervised.placed] == [
            one.assignees for one in automated.placed
        ]
        assert supervised.summary == automated.summary


class TestTheJobStaysOnTheScreenAfterARound:
    """The regression test for the defect ADR-071 §7 records.

    `myWork` filtered `round.placed`, `decide()` places only what is `queued`,
    and the two disagreed from the instant a round committed. Written against
    both modes because the fix is the read path rather than the mode.
    """

    def test_in_automatic_the_technician_still_has_it_after_the_round_writes(
        self, conn: Connection[Any], orders: WorkOrders, clock: SimulatedClock
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds = DispatchRounds(clock, automatic(CONFIG))

        rounds.run(conn)

        # What the old screen read, and what the fixed one reads.
        assert rounds.decide(conn).placed == ()
        assert [one for one, _ in work_repo.assigned_to(conn, ANA)] == [ref]

    def test_in_supervisor_mode_it_appears_when_it_is_confirmed_and_not_before(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        assert work_repo.assigned_to(conn, ANA) == []

        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        assert [one for one, _ in work_repo.assigned_to(conn, ANA)] == [ref]

    def test_it_is_the_rank_layer_three_decided_and_not_a_fresh_one(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        """Ordered by the `priority_score` frozen onto the order at placement, so
        the queue does not re-order itself under a technician already walking to
        a machine (design.md 6.2)."""
        _crew(conn, ANA)
        urgent = _ticket(orders, conn, severity=Severity.HIGH, machine_id=BOTTLENECK)
        minor = _ticket(orders, conn, severity=Severity.LOW)
        rounds.run(conn)
        for ref in (urgent, minor):
            confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        mine = [one for one, _ in work_repo.assigned_to(conn, ANA)]

        assert mine == [urgent, minor]

    def test_somebody_elses_work_is_not_on_it(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

        assert work_repo.assigned_to(conn, BEN) == []


class TestAnAnswerToAQuestionNobodyAsked:
    def test_confirming_an_order_with_no_proposal_is_a_lookup_failure(
        self, conn: Connection[Any], confirming: Confirmations, orders: WorkOrders
    ) -> None:
        _crew(conn, ANA)
        ref = _ticket(orders, conn)

        with pytest.raises(NoProposal):
            confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)

    def test_confirming_one_the_sweep_took_first_is_refused(
        self,
        conn: Connection[Any],
        rounds: DispatchRounds,
        confirming: Confirmations,
        orders: WorkOrders,
        clock: SimulatedClock,
    ) -> None:
        """The order goes back to the queue and the proposal row stays open only
        if the two writes disagree, which they cannot inside one transaction.
        This is the other side: the row is open, the order is not `proposed`, and
        confirming would assign somebody to a decision with no crew on it."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        rounds.run(conn)
        # The sweep's half, without the round: the order is released and the
        # question is left standing, which is the state the guard is written for.
        dispatch_repo.return_to_queue(conn, ref)

        with pytest.raises(AlreadyAnswered):
            confirming.confirm(conn, ref, by=SUP, role=Role.SUPERVISOR)


class TestAPredictionOvertakenWhileItWaits:
    def test_its_unconfirmed_ticket_is_withdrawn_and_leaves_the_board(
        self, conn: Connection[Any], rounds: DispatchRounds, orders: WorkOrders
    ) -> None:
        """A prediction's ticket waits in `proposed` for the shift lead (ADR-071).

        On 2026-09-29 the detection that superseded a prediction issued its own
        ticket, the prediction's was not withdrawn because the withdrawal only
        looked at `queued`, and the board then held three tickets for one fault on
        MC-004 - each one a technician the shift lead could send."""
        _crew(conn, ANA)
        ref = _ticket(orders, conn)
        conn.execute(
            "UPDATE work_order SET finding_ref = 'F-PREDICTED' WHERE work_order_ref = %s", (ref,)
        )
        rounds.run(conn)
        assert _status(conn, ref) is WorkOrderStatus.PROPOSED

        withdrawn = orders.withdraw_for_finding(conn, FindingRef("F-PREDICTED"))
        dispatch_repo.withdraw_pending(conn, withdrawn, at=NOW)

        assert withdrawn == [ref]
        assert _status(conn, ref) is WorkOrderStatus.CANCELLED
        assert [row["state"] for row in _proposal_rows(conn)] == [ProposalState.EXPIRED.value]

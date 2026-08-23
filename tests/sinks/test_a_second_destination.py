"""One implementation never proves an interface (ADR-069, #74).

With a single sink `TicketSink` was a class with one subclass. This file is what
makes "swappable" a property something can fail on, and the test that carries it
is `TestTheSameRoundTwoDestinations`: the same round, run against each sink,
places the same work for the same stated reasons and lands it in two different
places. Anything else that differed would mean the choice of destination had
reached back into layer 3, which is the thing ADR-012 exists to prevent.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    MachineId,
    MachineModel,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Technician,
    UserId,
    WorkOrderRef,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.service import DispatchRounds
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.platform.config.schema import SinkPolicy
from pdm.sinks import Deliveries, FileSink, OwnSystemSink
from pdm.sinks import repo as delivery
from pdm.sinks.domain import DeliveryFailed, Ticket
from pdm.sinks.registry import NAMES, TicketDirectoryNotSet, UnknownDestination, build
from pdm.work import WorkOrders
from tests.modes import automatic

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)  # 15:00 in Bangkok: the afternoon shift
AFTERNOON = ShiftId("afternoon")
TODAY = date(2026, 3, 3)
MACHINE = MachineId("MC-001")
R2000 = MachineModel("R-2000iC")
ANA = UserId("tech-ana")
ALL_SKILLS = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)

# These tests are about layer 4 and about a round meeting a database that moved
# under it, neither of which is what ADR-071's confirmation step is for. They run
# the plant in `automatic`, which is a supported mode rather than a convenience:
# the supervisor path is asserted end to end in
# `tests/dispatch/test_the_confirmation_gate.py`, where it is the subject.
CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


class TestTheConfigAndTheRegistryAgree:
    """`SinkPolicy` repeats the registry's names as a `Literal` because
    `pdm.platform` may not import `pdm.sinks` (ADR-030). Duplication with a
    guard, rather than duplication - this is the guard."""

    def test_every_name_the_registry_knows_is_one_the_config_accepts(self) -> None:
        accepted = set(SinkPolicy.model_fields["destination"].annotation.__args__)  # type: ignore[union-attr]
        assert set(NAMES) == accepted

    @pytest.mark.parametrize("name", NAMES)
    def test_and_every_accepted_name_builds_something(self, name: str, tmp_path: Path) -> None:
        sink = build(name, clock=SimulatedClock(NOW), ticket_dir=tmp_path)
        assert sink.destination == name


class TestAnUnknownDestinationStopsTheProcess:
    def test_it_raises_rather_than_falling_back(self) -> None:
        """Never a quiet fall back to own-system. A plant that configured `cmms`
        and got our own system would look like it was working, and the tickets
        nobody was reading would be the first anybody heard of it (ADR-069)."""
        with pytest.raises(UnknownDestination) as raised:
            build("cmms", clock=SimulatedClock(NOW))

        assert "cmms" in str(raised.value)
        # And says what it does have, because the next thing somebody does is
        # look for the spelling they got wrong.
        assert "own-system" in str(raised.value)

    def test_the_file_destination_will_not_guess_a_directory(self) -> None:
        """ADR-019's argument, applied to tickets: a guessed path is a stack
        that starts healthy and writes where nobody will look."""
        with pytest.raises(TicketDirectoryNotSet) as raised:
            build("file", clock=SimulatedClock(NOW))

        assert "TICKET_DIR" in str(raised.value)


class TestTheFileDestination:
    def _ticket(self) -> Ticket:
        return Ticket(
            work_order_ref=WorkOrderRef("WO-000123"),
            machine_id=MACHINE,
            severity=Severity.HIGH,
            reason="รายงานจากพนักงาน: มีเสียงบดที่แกน J2",
            priority_reason="the shift is at 64% (normal load)",
            estimated_minutes=45,
            required_skill=SkillId("robot_mechanical"),
            required_technicians=1,
            assignees=(),
            steps=(),
            playbook_warning=None,
        )

    def test_the_receipt_is_where_the_ticket_actually_went(self, tmp_path: Path) -> None:
        receipt = FileSink(tmp_path, SimulatedClock(NOW)).deliver(self._ticket())

        assert receipt.external_ref == str(tmp_path / "WO-000123.json")
        assert Path(receipt.external_ref).exists()

    def test_delivering_twice_leaves_one_file(self, tmp_path: Path) -> None:
        """At-least-once means every adapter is called again eventually
        (ADR-068). A destination that grew a file per attempt would turn a
        retry loop into a full disk."""
        sink = FileSink(tmp_path, SimulatedClock(NOW))
        sink.deliver(self._ticket())
        sink.deliver(self._ticket())

        assert [path.name for path in tmp_path.iterdir()] == ["WO-000123.json"]

    def test_thai_survives_the_journey(self, tmp_path: Path) -> None:
        """`reason` is what a technician reads, and a destination that wrote it
        as \\u0e23\\u0e32\\u0e22 would be one nobody could check by eye."""
        FileSink(tmp_path, SimulatedClock(NOW)).deliver(self._ticket())

        written = (tmp_path / "WO-000123.json").read_text(encoding="utf-8")
        assert "มีเสียงบดที่แกน J2" in written
        assert json.loads(written)["ticket"]["machine_id"] == "MC-001"

    def test_a_directory_it_cannot_write_is_a_refusal_not_a_crash(self, tmp_path: Path) -> None:
        """The cheapest honest version of a CMMS that is down. ADR-068 §3 wants
        it raised as `DeliveryFailed`, so the round records it and retries."""
        blocked = tmp_path / "read-only" / "tickets"
        blocked.parent.mkdir()
        blocked.parent.chmod(0o500)
        try:
            with pytest.raises(DeliveryFailed) as raised:
                FileSink(blocked, SimulatedClock(NOW)).deliver(self._ticket())
        finally:
            blocked.parent.chmod(0o700)

        assert str(blocked) in str(raised.value)


# ── the same round, two destinations ────────────────────────────────────────

pytestmark_db = pytest.mark.db


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "ticket_delivery CASCADE"
        )
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _placed(conn: Connection[Any], clock: SimulatedClock) -> tuple[WorkOrderRef, Any]:
    dispatch_repo.add_technician(conn, Technician(user=ANA, skills=ALL_SKILLS), now=NOW)
    dispatch_repo.assign_to_shift(
        conn,
        ShiftAssignment(shift_id=AFTERNOON, on_date=TODAY, technician=ANA, available_minutes=480),
    )
    ref = (
        WorkOrders(clock, fallback_minutes=FALLBACK)
        .from_report(
            conn,
            machine_id=MACHINE,
            machine_model=R2000,
            severity=Severity.MEDIUM,
            reported_by=UserId("supervisor"),
            description="reported in a test",
        )
        .ref
    )
    report = DispatchRounds(clock, automatic(CONFIG)).run(conn)
    assert report.placed == (ref,)
    return WorkOrderRef(ref), report


@pytest.mark.db
class TestTheSameRoundTwoDestinations:
    """The test this slice exists for.

    Layer 3 is given the same world twice and must produce the same schedule
    both times; only the delivery differs. If anything else moved, the choice of
    destination would have reached back into the scheduler (ADR-012).
    """

    def _round_against(self, conn: Connection[Any], sink: Any) -> dict[str, Any]:
        clock = SimulatedClock(NOW)
        ref, report = _placed(conn, clock)
        Deliveries(sink, clock).run(conn, placed=[ref])
        row = delivery.state_of(conn, ref)
        assert row is not None
        from pdm.work import repo as work

        order = work.get(conn, str(ref))
        assert order is not None
        return {
            "placed": report.placed,
            "priority_reason": order.priority_reason,
            "priority_score": order.priority_score,
            "assignees": tuple(one.user for one in order.assignees),
            "delivery": row,
        }

    def test_the_schedule_is_identical_and_only_the_destination_moves(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        own = self._round_against(conn, OwnSystemSink())
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "ticket_delivery CASCADE"
        )
        to_file = self._round_against(conn, FileSink(tmp_path, SimulatedClock(NOW)))

        # Layer 3 did not notice. Not the refs themselves: `work_order_ref`
        # comes from a sequence that TRUNCATE does not reset, so the second
        # round's order is a different row by construction. What must match is
        # everything the scheduler decided about it.
        assert len(own["placed"]) == len(to_file["placed"]) == 1
        assert own["priority_reason"] == to_file["priority_reason"]
        assert own["priority_score"] == to_file["priority_score"]
        assert own["assignees"] == to_file["assignees"]

        # Layer 4 did.
        assert own["delivery"]["destination"] == "own-system"
        assert to_file["delivery"]["destination"] == "file"
        assert own["delivery"]["external_ref"] != to_file["delivery"]["external_ref"]

    def test_the_delivery_record_has_the_same_shape_either_way(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        """A second destination that needed a column of its own would mean the
        record was built for the first one rather than for delivery."""
        own = self._round_against(conn, OwnSystemSink())
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "ticket_delivery CASCADE"
        )
        to_file = self._round_against(conn, FileSink(tmp_path, SimulatedClock(NOW)))

        assert own["delivery"].keys() == to_file["delivery"].keys()
        for row in (own["delivery"], to_file["delivery"]):
            assert row["state"] == "delivered"
            assert row["attempts"] == 1
            assert row["delivered_at"] is not None
            assert row["last_error"] is None

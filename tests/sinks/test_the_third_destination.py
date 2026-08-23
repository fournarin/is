"""The first destination that fails the way real ones do (ADR-070, ADR-074, #82).

`OwnSystemSink` cannot fail and a directory can only be unwritable. A CMMS
reached over a socket can hang, refuse, answer something that is not JSON, or
accept the ticket and name nothing - and ADR-068's refusal path has until now
been exercised only by a double that was asked to fail.

So the fake here is a real HTTP server on a real port. It is slower to write
than a stub and that is the point of the slice: `urllib`'s own behaviour on a
timeout, on a 500 and on a closed port is exactly what is under test, and a
stub would only be asserting that our own double does what we told it to.

What is *not* under test is whether the plant's system accepts this request.
The contract is ours (ADR-070 §2), and no fake can close that gap.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from datetime import UTC, date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
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
from pdm.sinks import Deliveries, FileSink, OwnSystemSink
from pdm.sinks import repo as delivery
from pdm.sinks.cmms import CmmsSink
from pdm.sinks.domain import DeliveryFailed, Ticket
from pdm.sinks.registry import CmmsEndpointNotSet, build
from pdm.work import WorkOrders
from pdm.work import repo as work
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
TOKEN = "a-token-that-exists-only-in-this-test"

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}


def _ticket() -> Ticket:
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


# ── a CMMS that behaves badly on purpose ────────────────────────────────────


class QuietServer(ThreadingHTTPServer):
    """A client that gave up mid-response is the subject of a test here, not an
    incident. Without this, every timeout case prints a broken-pipe traceback
    into output somebody is meant to read."""

    def handle_error(self, request: Any, client_address: Any) -> None:
        return


class FakeCmms:
    """A destination on a real socket, with the failure modes a network has.

    Every knob is one ADR-070 §2 names as the reason a third destination is
    worth building: it can be slow, it can refuse, and it can issue a second
    identifier for a ticket it has already been given.
    """

    def __init__(
        self,
        *,
        status: int = 201,
        body: str | None = None,
        delay_seconds: float = 0.0,
        deduplicates: bool = True,
    ) -> None:
        self.status = status
        self.body = body
        self.delay_seconds = delay_seconds
        self.deduplicates = deduplicates
        self.received: list[dict[str, Any]] = []
        self.issued: dict[str, str] = {}
        self._issued_count = 0
        self._lock = Lock()
        self._stopped = False

        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length)
                fake.received.append(
                    {
                        "path": self.path,
                        "headers": dict(self.headers),
                        "raw": raw,
                        "body": json.loads(raw.decode("utf-8")),
                    }
                )
                if fake.delay_seconds:
                    # The one sleep in this file, and it is the subject rather
                    # than a wait for something to settle: a destination that
                    # hangs is what the timeout under test exists for.
                    time.sleep(fake.delay_seconds)

                answer = fake.body if fake.body is not None else fake.answer_for(raw)
                encoded = answer.encode("utf-8")
                self.send_response(fake.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: Any) -> None:
                """Quiet. pytest's captured output is not a web server log."""

        self._server = QuietServer(("127.0.0.1", 0), Handler)
        self._thread = Thread(target=self._server.serve_forever, daemon=True)

    def answer_for(self, raw: bytes) -> str:
        """A CMMS work-order number - the same one twice only if it deduplicates."""
        key = str(json.loads(raw.decode("utf-8"))["ticket"]["work_order_ref"])
        with self._lock:
            if not (self.deduplicates and key in self.issued):
                self._issued_count += 1
                self.issued[key] = f"CMMS-{self._issued_count:04d}"
            return json.dumps({"id": self.issued[key]})

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def cmms() -> Iterator[FakeCmms]:
    fake = FakeCmms()
    fake.start()
    try:
        yield fake
    finally:
        fake.stop()


def _sink(fake: FakeCmms, *, timeout_seconds: float = 5.0) -> CmmsSink:
    return CmmsSink(fake.base_url, token=TOKEN, timeout_seconds=timeout_seconds)


# ── the contract, which is ours ─────────────────────────────────────────────


class TestTheRequestIsTheOneADR074WroteDown:
    """A contract being ours is worth something only if it is fixed somewhere
    other than in the adapter implementing it. ADR-074 §1 is that somewhere,
    and this is what holds the code to it."""

    def test_the_method_the_path_and_the_credential(self, cmms: FakeCmms) -> None:
        _sink(cmms).deliver(_ticket())

        sent = cmms.received[0]
        assert sent["path"] == "/work-orders"
        assert sent["headers"]["Authorization"] == f"Bearer {TOKEN}"
        assert sent["headers"]["Content-Type"] == "application/json; charset=utf-8"

    def test_the_body_is_the_ticket_under_one_key(self, cmms: FakeCmms) -> None:
        """Wrapped rather than bare, so a field can be added later without every
        existing one moving in somebody else's system (ADR-074 §1)."""
        _sink(cmms).deliver(_ticket())

        body = cmms.received[0]["body"]
        assert set(body) == {"ticket"}
        assert body["ticket"]["work_order_ref"] == "WO-000123"
        assert body["ticket"]["machine_id"] == "MC-001"
        assert body["ticket"]["priority_reason"] == "the shift is at 64% (normal load)"

    def test_the_idempotency_key_is_the_work_order_ref(self, cmms: FakeCmms) -> None:
        """In the header for a destination that deduplicates at its edge, and in
        the body for one that deduplicates in its application (ADR-074 §1)."""
        _sink(cmms).deliver(_ticket())

        sent = cmms.received[0]
        assert sent["headers"]["Idempotency-Key"] == "WO-000123"
        assert sent["body"]["ticket"]["work_order_ref"] == "WO-000123"

    def test_thai_arrives_as_thai(self, cmms: FakeCmms) -> None:
        """`reason` is what a technician reads. A body that arrived escaped is
        one nobody can check by eye against the screen they are looking at."""
        _sink(cmms).deliver(_ticket())

        assert "มีเสียงบดที่แกน J2".encode() in cmms.received[0]["raw"]
        assert cmms.received[0]["body"]["ticket"]["reason"].startswith("รายงานจากพนักงาน")


class TestTheReceiptIsSomebodyElsesIdentifier:
    """The thing the first two destinations cannot produce. `OwnSystemSink`
    returns our own ref and `FileSink` returns a path we chose; this is the
    first receipt whose contents were decided elsewhere (ADR-068 §1)."""

    def test_the_destinations_own_number_is_what_is_recorded(self, cmms: FakeCmms) -> None:
        receipt = _sink(cmms).deliver(_ticket())

        assert receipt.external_ref == "CMMS-0001"
        assert receipt.external_ref in cmms.issued.values()


# ── what a network does that a directory cannot ─────────────────────────────


class TestEveryWayANetworkSaysNoIsARefusal:
    """ADR-074 §3. All of these are `DeliveryFailed`, recorded on the delivery
    row and retried next round; none is a defect that should take the round's
    transaction down with it."""

    def test_a_destination_that_hangs_is_given_up_on(self) -> None:
        fake = FakeCmms(delay_seconds=2.0)
        fake.start()
        try:
            with pytest.raises(DeliveryFailed) as raised:
                _sink(fake, timeout_seconds=0.2).deliver(_ticket())
        finally:
            fake.stop()

        assert fake.base_url in str(raised.value)

    def test_a_five_hundred_names_the_status(self) -> None:
        fake = FakeCmms(status=500, body=json.dumps({"error": "database is down"}))
        fake.start()
        try:
            with pytest.raises(DeliveryFailed) as raised:
                _sink(fake).deliver(_ticket())
        finally:
            fake.stop()

        assert "500" in str(raised.value)
        assert fake.base_url in str(raised.value)

    def test_a_port_with_nothing_behind_it(self, cmms: FakeCmms) -> None:
        """The destination that is down rather than one refusing a ticket. Same
        treatment: the round records it and tries again."""
        address = cmms.base_url
        cmms.stop()

        with pytest.raises(DeliveryFailed) as raised:
            CmmsSink(address, token=TOKEN, timeout_seconds=1.0).deliver(_ticket())

        assert address in str(raised.value)

    def test_a_body_that_is_not_json(self) -> None:
        """A proxy's HTML error page answering 200 means the destination is not
        what we think it is, which is not the same as our own code being wrong."""
        fake = FakeCmms(status=200, body="<html>gateway</html>")
        fake.start()
        try:
            with pytest.raises(DeliveryFailed) as raised:
                _sink(fake).deliver(_ticket())
        finally:
            fake.stop()

        assert "JSON" in str(raised.value)

    def test_accepting_the_ticket_and_naming_nothing_is_not_a_delivery(self) -> None:
        """ADR-074 §4, and the case ADR-070 §2 says a CMMS adds. Recording our
        own ref here would leave a row that cannot reconcile the two systems,
        which is the only thing `external_ref` is for (ADR-068 §1)."""
        fake = FakeCmms(status=201, body=json.dumps({"status": "queued"}))
        fake.start()
        try:
            with pytest.raises(DeliveryFailed) as raised:
                _sink(fake).deliver(_ticket())
        finally:
            fake.stop()

        assert "identifier" in str(raised.value)


class TestAtLeastOnceMeetsADestinationThatCannotDeduplicate:
    """ADR-068 §1 chose at-least-once and documented `deliver` as safe to call
    again. What that costs is visible only against a destination with a record
    of its own, so it is measured here rather than asserted in a docstring."""

    def test_a_destination_that_reads_the_key_issues_one_number(self, cmms: FakeCmms) -> None:
        sink = _sink(cmms)
        first = sink.deliver(_ticket())
        second = sink.deliver(_ticket())

        assert first.external_ref == second.external_ref == "CMMS-0001"
        assert len(cmms.received) == 2  # it was sent twice
        assert len(cmms.issued) == 1  # and one record came of it

    def test_a_destination_that_ignores_it_issues_two_and_we_record_what_it_said(self) -> None:
        """The honest trade, in a test. A duplicate ticket is the failure this
        project chose over a missing one, and the second receipt says where the
        ticket that exists now is - not where the first one went."""
        fake = FakeCmms(deduplicates=False)
        fake.start()
        try:
            sink = _sink(fake)
            first = sink.deliver(_ticket())
            second = sink.deliver(_ticket())
        finally:
            fake.stop()

        assert first.external_ref == "CMMS-0001"
        assert second.external_ref == "CMMS-0002"


# ── the numbers, and where they come from ───────────────────────────────────


class TestTheTimeoutIsDerivedRatherThanChosen:
    def test_a_full_batch_cannot_outlast_the_round_that_started_it(self) -> None:
        """ADR-074 §2. Both numbers this is derived from live somewhere else and
        can be changed by somebody who never reads that record, so the
        derivation is a test rather than a comment.

        Without a timeout at all, ADR-068 §4's cap on the batch bounds nothing:
        a destination that accepts a connection and never answers holds the pass
        open for as long as the operating system allows.
        """
        batch = Deliveries(OwnSystemSink(), SimulatedClock(NOW)).batch
        worst_case = batch * CmmsSink.TIMEOUT_SECONDS

        assert worst_case <= CONFIG.policy.dispatch.round_seconds


# ── composition ─────────────────────────────────────────────────────────────


class TestTheRegistryWillNotGuessAnEndpoint:
    """`TICKET_DIR`'s argument, one destination further out (ADR-069 §1,
    ADR-074 §5): a sink pointed at a guessed host looks healthy while writing
    nowhere, so it fails at composition rather than at the first ticket."""

    def test_a_base_url_is_required(self) -> None:
        with pytest.raises(CmmsEndpointNotSet) as raised:
            build("cmms", clock=SimulatedClock(NOW), cmms_token=TOKEN)

        assert "CMMS_BASE_URL" in str(raised.value)

    def test_a_credential_is_required(self) -> None:
        with pytest.raises(CmmsEndpointNotSet) as raised:
            build("cmms", clock=SimulatedClock(NOW), cmms_base_url="https://cmms.example")

        assert "CMMS_TOKEN" in str(raised.value)

    @pytest.mark.parametrize("address", ["file:///var/tmp/tickets", "ftp://cmms.example"])
    def test_a_destination_that_is_not_a_network_address_is_refused(self, address: str) -> None:
        """`urllib` opens `file://` as readily as an address, and a sink that
        reported every delivery as successful while writing to a local path
        would be the failure ADR-069 §2 refuses, arriving by another route."""
        with pytest.raises(CmmsEndpointNotSet) as raised:
            build("cmms", clock=SimulatedClock(NOW), cmms_base_url=address, cmms_token=TOKEN)

        assert "http" in str(raised.value)

    def test_with_both_it_builds(self) -> None:
        sink = build(
            "cmms",
            clock=SimulatedClock(NOW),
            cmms_base_url="https://cmms.example/api/",
            cmms_token=TOKEN,
        )

        assert sink.destination == "cmms"


# ── the same round, three destinations ──────────────────────────────────────
#
# ADR-069's consequence, one destination further out. Layer 3 is given the same
# world three times and must produce the same schedule every time; only the
# delivery differs. Anything else moving would mean the choice of destination
# had reached back into the scheduler, which is what ADR-012 exists to prevent -
# and the third sink is the first one where that could plausibly happen, because
# it is the first that can fail for reasons of its own.


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        _truncate(connection)
        yield connection
    finally:
        connection.rollback()
        connection.close()


def _truncate(connection: Connection[Any]) -> None:
    connection.execute(
        "TRUNCATE work_order, finding, job, shift_assignment, technician, ticket_delivery CASCADE"
    )
    connection.commit()


def _round_against(conn: Connection[Any], sink: Any) -> dict[str, Any]:
    """One round in an empty world, delivered to `sink`, described for comparison.

    The plant runs in `automatic` here for the reason
    `test_a_second_destination.py` gives: ADR-071's confirmation step is asserted
    where it is the subject, and this test is about layer 4.
    """
    clock = SimulatedClock(NOW)
    dispatch_repo.add_technician(conn, Technician(user=ANA, skills=ALL_SKILLS), now=NOW)
    dispatch_repo.assign_to_shift(
        conn,
        ShiftAssignment(shift_id=AFTERNOON, on_date=TODAY, technician=ANA, available_minutes=480),
    )
    ref = WorkOrderRef(
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

    Deliveries(sink, clock).run(conn, placed=[ref])
    row = delivery.state_of(conn, ref)
    order = work.get(conn, str(ref))
    assert row is not None
    assert order is not None
    return {
        "priority_reason": order.priority_reason,
        "priority_score": order.priority_score,
        "assignees": tuple(one.user for one in order.assignees),
        "delivery": row,
    }


@pytest.mark.db
class TestTheSameRoundThreeDestinations:
    def test_the_schedule_is_identical_and_only_the_delivery_moves(
        self, conn: Connection[Any], cmms: FakeCmms, tmp_path: Path
    ) -> None:
        sinks: dict[str, Any] = {
            "own-system": OwnSystemSink(),
            "file": FileSink(tmp_path, SimulatedClock(NOW)),
            "cmms": _sink(cmms),
        }

        rounds: dict[str, dict[str, Any]] = {}
        for name, sink in sinks.items():
            _truncate(conn)
            rounds[name] = _round_against(conn, sink)

        # Layer 3 did not notice. Not the refs themselves: `work_order_ref` comes
        # from a sequence TRUNCATE does not reset, so each round's order is a
        # different row by construction. What must match is what was decided.
        decisions = [
            (one["priority_reason"], one["priority_score"], one["assignees"])
            for one in rounds.values()
        ]
        assert decisions[0] == decisions[1] == decisions[2]

        # Layer 4 did, and the third destination's receipt is the only one this
        # system did not choose the contents of.
        assert [one["delivery"]["destination"] for one in rounds.values()] == list(sinks)
        assert rounds["cmms"]["delivery"]["external_ref"] == "CMMS-0001"
        assert len({one["delivery"]["external_ref"] for one in rounds.values()}) == 3

    def test_the_delivery_record_has_the_same_shape_for_all_three(
        self, conn: Connection[Any], cmms: FakeCmms, tmp_path: Path
    ) -> None:
        """A destination that needed a column of its own would mean the record
        was built for the first sink rather than for delivery (ADR-069)."""
        rows = []
        for sink in (OwnSystemSink(), FileSink(tmp_path, SimulatedClock(NOW)), _sink(cmms)):
            _truncate(conn)
            rows.append(_round_against(conn, sink)["delivery"])

        assert rows[0].keys() == rows[1].keys() == rows[2].keys()
        for row in rows:
            assert row["state"] == "delivered"
            assert row["attempts"] == 1
            assert row["delivered_at"] is not None
            assert row["last_error"] is None

    def test_a_cmms_that_is_down_leaves_the_work_placed_and_the_ticket_outstanding(
        self, conn: Connection[Any], tmp_path: Path
    ) -> None:
        """ADR-068 §2 through the first destination that can really be down. The
        technician keeps the job they can already see; the ticket comes back
        next round."""
        fake = FakeCmms(status=503, body=json.dumps({"error": "maintenance window"}))
        fake.start()
        try:
            _truncate(conn)
            state = _round_against(conn, _sink(fake))
        finally:
            fake.stop()

        assert state["delivery"]["state"] == "failed"
        assert state["delivery"]["attempts"] == 1
        assert "503" in state["delivery"]["last_error"]
        # The round's decision stands. A destination being down is a fact about
        # the destination.
        assert state["assignees"] == (ANA,)

"""The line as the overview will draw it (slice 9.4).

The advisor's first requirement was "monitor **and** predict", and until this
endpoint both were visible in exactly one place: a ticket in one technician's
hand. The specification is `CLAUDE.md`, ADR-020, ADR-021 and ADR-050 rather than
the handler, and three properties carry the slice:

  * **the pair is the contract.** A predicted station carries its ETA *and* the
    interval, always. "About six hours" reads as more trustworthy than "about
    six hours, give or take two" and is a promise the system cannot keep, so the
    response model refuses to serialise one without the other (ADR-020);
  * **the topology is read, never hardcoded.** A test moves a buffer in a
    fixture `plant.yaml` and the response moves with it, which is what makes
    ADR-021's "assumed values carry the work through the term" true;
  * **nothing is computed twice.** The shift figures come from the same round
    `/dispatch/round` reports, so a screen and the scheduler cannot disagree
    about how loaded the shift is (ADR-050).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg_pool import ConnectionPool

from pdm.api.overview import StationState, StationView, group_by_machine, read_the_line
from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    FindingStatus,
    Line,
    LineId,
    MachineId,
    MachineModel,
    Role,
    RuleId,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    Station,
    StationId,
    SymptomCode,
    Technician,
    UserId,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.triggers import repo as triggers
from pdm.work import WorkOrders

# 08:00 UTC is 15:00 in Bangkok: the afternoon shift, filed under the 3rd. The
# same moment the other API tests use, for the same reason - a shift that exists.
NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
AFTERNOON = ShiftId("afternoon")

R2000 = MachineModel("R-2000iC")

# The machines and stations of `config/plant.yaml`, named rather than invented so
# that what the endpoint resolves is the plant's answer and not the test's.
BUFFERED = MachineId("MC-001")  # st-01, 20 units of buffer
QUIET = MachineId("MC-004")  # st-02, 8 units
BOTTLENECK = MachineId("MC-012")  # st-03, no buffer, multiplier 3.0
FAR_END = MachineId("MC-018")  # st-04, 12 units

PASSWORD = "correct horse battery staple"
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
}

LINE_A = Line(line_id=LineId("line-a"), takt_seconds=60.0)


def station(
    station_id: str, *, seq: int, machines: tuple[MachineId, ...], buffer_units: int = 0
) -> Station:
    return Station(
        station_id=StationId(station_id),
        line_id=LINE_A.line_id,
        seq=seq,
        buffer_units=buffer_units,
        bottleneck_multiplier=1.0,
        machine_ids=machines,
    )


def detected(
    machine_id: MachineId,
    *,
    detected_at: datetime = NOW,
    severity: Severity = Severity.HIGH,
    rule_id: str = "R-1",
    symptom_code: str = "SYM-014",
) -> Finding:
    return Finding(
        machine_id=machine_id,
        component=ComponentLabel("spindle_motor"),
        symptom_code=SymptomCode(symptom_code),
        severity=severity,
        rule_id=RuleId(rule_id),
        detected_at=detected_at,
        evidence={"value": 92.0, "threshold": 85.0},
        kind=FindingKind.DETECTED,
        status=FindingStatus.OPEN,
    )


def predicted(
    machine_id: MachineId,
    *,
    eta: datetime,
    confidence: timedelta = timedelta(hours=2),
    detected_at: datetime = NOW,
    severity: Severity = Severity.MEDIUM,
    rule_id: str = "R-1/trend",
) -> Finding:
    return Finding(
        machine_id=machine_id,
        component=ComponentLabel("spindle_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=severity,
        rule_id=RuleId(rule_id),
        detected_at=detected_at,
        evidence={"slope": 0.4},
        kind=FindingKind.PREDICTED,
        eta=eta,
        eta_confidence=confidence,
        status=FindingStatus.OPEN,
    )


class TestWhatAStationShows:
    """One state per station, chosen from whatever is live on its machines."""

    def test_a_station_with_nothing_live_is_normal_and_carries_no_eta(self) -> None:
        drawn = read_the_line(
            LINE_A,
            [station("st-01", seq=1, machines=(BUFFERED,), buffer_units=20)],
            live={},
            now=NOW,
        )

        assert [one.state for one in drawn] == [StationState.NORMAL]
        assert drawn[0].eta is None
        assert drawn[0].eta_confidence_minutes is None
        assert drawn[0].over_threshold_minutes is None
        assert drawn[0].machine_id is None

    def test_a_detected_finding_says_how_long_it_has_been_over(self) -> None:
        drawn = read_the_line(
            LINE_A,
            [station("st-03", seq=3, machines=(BOTTLENECK,))],
            live={BOTTLENECK: [detected(BOTTLENECK, detected_at=NOW - timedelta(minutes=20))]},
            now=NOW,
        )

        assert drawn[0].state is StationState.OVER_THRESHOLD
        assert drawn[0].over_threshold_minutes == 20
        assert drawn[0].machine_id == BOTTLENECK
        assert drawn[0].severity is Severity.HIGH

    def test_a_predicted_finding_carries_its_eta_and_its_interval(self) -> None:
        """ADR-020: the interval is the half a technician plans around."""
        crossing = NOW + timedelta(hours=6)
        drawn = read_the_line(
            LINE_A,
            [station("st-02", seq=2, machines=(QUIET,), buffer_units=8)],
            live={QUIET: [predicted(QUIET, eta=crossing, confidence=timedelta(hours=2))]},
            now=NOW,
        )

        assert drawn[0].state is StationState.PREDICTED
        assert drawn[0].eta == crossing
        assert drawn[0].eta_confidence_minutes == 120
        assert drawn[0].over_threshold_minutes is None

    def test_a_crossing_that_has_happened_outranks_one_that_is_expected(self) -> None:
        """Both can be live at once and ADR-023 section 7 says why: a detection
        supersedes an open prediction, and until it does the station has two.
        The one already costing production is the one the screen shows."""
        drawn = read_the_line(
            LINE_A,
            [station("st-03", seq=3, machines=(BOTTLENECK,))],
            live={
                BOTTLENECK: [
                    predicted(BOTTLENECK, eta=NOW + timedelta(hours=1), rule_id="R-1/trend"),
                    detected(BOTTLENECK, detected_at=NOW - timedelta(minutes=5)),
                ]
            },
            now=NOW,
        )

        assert drawn[0].state is StationState.OVER_THRESHOLD
        assert drawn[0].over_threshold_minutes == 5

    def test_the_worse_of_two_faults_leads_and_the_other_is_still_counted(self) -> None:
        """A station is one marker and may hold several faults. The marker takes
        the worst of them; the count says how many there are, because a screen
        showing one of three without saying so reads as though there were one."""
        drawn = read_the_line(
            LINE_A,
            [station("st-01", seq=1, machines=(BUFFERED, QUIET), buffer_units=20)],
            live={
                BUFFERED: [
                    detected(
                        BUFFERED,
                        severity=Severity.LOW,
                        detected_at=NOW - timedelta(hours=3),
                        rule_id="R-low",
                    )
                ],
                QUIET: [
                    detected(
                        QUIET,
                        severity=Severity.CRITICAL,
                        detected_at=NOW - timedelta(minutes=2),
                        rule_id="R-critical",
                    )
                ],
            },
            now=NOW,
        )

        assert drawn[0].machine_id == QUIET
        assert drawn[0].severity is Severity.CRITICAL
        assert drawn[0].live_findings == 2

    def test_between_equals_the_one_that_has_been_over_longest_leads(self) -> None:
        drawn = read_the_line(
            LINE_A,
            [station("st-01", seq=1, machines=(BUFFERED, QUIET), buffer_units=20)],
            live={
                BUFFERED: [detected(BUFFERED, detected_at=NOW - timedelta(minutes=90))],
                QUIET: [detected(QUIET, detected_at=NOW - timedelta(minutes=10))],
            },
            now=NOW,
        )

        assert drawn[0].machine_id == BUFFERED
        assert drawn[0].over_threshold_minutes == 90

    def test_the_soonest_crossing_leads_among_predictions(self) -> None:
        soon = NOW + timedelta(hours=2)
        drawn = read_the_line(
            LINE_A,
            [station("st-01", seq=1, machines=(BUFFERED, QUIET), buffer_units=20)],
            live={
                BUFFERED: [predicted(BUFFERED, eta=NOW + timedelta(hours=9))],
                QUIET: [predicted(QUIET, eta=soon)],
            },
            now=NOW,
        )

        assert drawn[0].machine_id == QUIET
        assert drawn[0].eta == soon

    def test_a_prediction_may_not_be_serialised_without_its_interval(self) -> None:
        """The one thing on this screen an ordinary maintenance board does not
        have, made structurally impossible to drop (ADR-020, ADR-043 section 3).

        Asserted on the response model rather than on the handler: a later screen
        assembling a `StationView` by hand has to obey it too.
        """
        with pytest.raises(ValueError, match="interval"):
            StationView(
                station_id=StationId("st-03"),
                seq=3,
                buffer_units=0,
                buffer_minutes=0.0,
                bottleneck=True,
                bottleneck_multiplier=3.0,
                machines=(BOTTLENECK,),
                state=StationState.PREDICTED,
                eta=NOW + timedelta(hours=6),
            )

    def test_a_normal_station_may_not_carry_an_eta_either(self) -> None:
        with pytest.raises(ValueError, match="normal"):
            StationView(
                station_id=StationId("st-01"),
                seq=1,
                buffer_units=20,
                buffer_minutes=20.0,
                bottleneck=False,
                bottleneck_multiplier=1.0,
                machines=(BUFFERED,),
                state=StationState.NORMAL,
                eta=NOW + timedelta(hours=6),
                eta_confidence_minutes=120,
            )


class TestTheTopologyIsRead:
    def test_stations_come_back_in_line_order_whatever_order_they_arrive_in(self) -> None:
        drawn = read_the_line(
            LINE_A,
            [
                station("st-03", seq=3, machines=(BOTTLENECK,)),
                station("st-01", seq=1, machines=(BUFFERED,), buffer_units=20),
                station("st-02", seq=2, machines=(QUIET,), buffer_units=8),
            ],
            live={},
            now=NOW,
        )

        assert [one.station_id for one in drawn] == ["st-01", "st-02", "st-03"]

    def test_the_buffer_is_reported_in_minutes_at_the_line_s_takt(self) -> None:
        """The edge the overview draws (ADR-021). Units alone cannot be drawn
        against a repair time; the conversion is the line's takt and nothing
        else, which is why it is `Station.buffer_minutes` and not arithmetic
        here."""
        slow = Line(line_id=LINE_A.line_id, takt_seconds=120.0)
        drawn = read_the_line(
            slow,
            [station("st-01", seq=1, machines=(BUFFERED,), buffer_units=20)],
            live={},
            now=NOW,
        )

        assert drawn[0].buffer_units == 20
        assert drawn[0].buffer_minutes == pytest.approx(40.0)

    def test_a_multiplier_above_one_is_what_makes_a_station_a_bottleneck(self) -> None:
        drawn = read_the_line(
            LINE_A,
            [
                Station(
                    station_id=StationId("st-03"),
                    line_id=LINE_A.line_id,
                    seq=3,
                    buffer_units=0,
                    bottleneck_multiplier=3.0,
                    machine_ids=(BOTTLENECK,),
                ),
                station("st-01", seq=1, machines=(BUFFERED,), buffer_units=20),
            ],
            live={},
            now=NOW,
        )

        assert [(one.station_id, one.bottleneck) for one in drawn] == [
            ("st-01", False),
            ("st-03", True),
        ]


class TestMachinesThatLeftTheLayout:
    def test_a_finding_on_a_machine_at_no_station_is_named_not_dropped(self) -> None:
        """ADR-048 section 3, as `/overview/gaps` already does it: the layout
        moved on and the machine went with it, and a screen that silently
        discarded its Findings would report a line that is quieter than it is."""
        gone = MachineId("MC-999")
        grouped, unplaced = group_by_machine(
            [detected(BUFFERED), detected(gone, rule_id="R-2")], known={BUFFERED, QUIET}
        )

        assert set(grouped) == {BUFFERED}
        assert unplaced == [gone]


# ─────────────────────────────────────────────────────────────
# Over HTTP, against a real PostgreSQL (ADR-031)
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


def _config_dir(tmp_path: Path, *, buffers: dict[str, int]) -> Path:
    """A copy of `config/` with some buffers moved.

    A copy rather than a hand-written plant, so the fixture cannot drift from
    the file the application actually loads and cross-file validation still has
    the rules and the policy to check against.
    """
    directory = tmp_path / f"config-{'-'.join(f'{k}{v}' for k, v in sorted(buffers.items()))}"
    directory.mkdir()
    for name in ("plant.yaml", "rules.yaml", "policy.yaml"):
        (directory / name).write_text(
            Path("config", name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    plant = yaml.safe_load((directory / "plant.yaml").read_text(encoding="utf-8"))
    for line in plant["lines"]:
        for one in line["stations"]:
            if one["station_id"] in buffers:
                one["buffer_units"] = buffers[one["station_id"]]
    (directory / "plant.yaml").write_text(yaml.safe_dump(plant), encoding="utf-8")
    return directory


@pytest.fixture
def world(database_url: str, clock: SimulatedClock) -> Iterator[ConnectionPool]:
    """A shift with one technician, two open orders and three live Findings.

    Ninety minutes of technician against two sixty-minute jobs puts the ratio
    past the heavy boundary, so the gate has something to hold - which is the
    state the overview's shift band exists to report.
    """
    auth = Authentication(LocalAccounts(), clock)
    orders = WorkOrders(
        clock, fallback_minutes={str(R2000): {severity: 60 for severity in Severity}}
    )

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE work_order, work_order_override, finding, job, shift_assignment, "
            "technician, access_log, session, account CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        dispatch_repo.add_technician(
            conn,
            Technician(user=UserId("tech-1"), skills=frozenset({SkillId("robot_mechanical")})),
            now=NOW,
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=AFTERNOON,
                on_date=NOW.date(),
                technician=UserId("tech-1"),
                available_minutes=90,
            ),
        )

        # st-03, the bottleneck: over threshold for twenty minutes.
        triggers.raise_finding(
            conn, detected(BOTTLENECK, detected_at=NOW - timedelta(minutes=20), rule_id="R-hot")
        )
        # st-04: a crossing expected in about six hours, give or take two.
        triggers.raise_finding(
            conn,
            predicted(FAR_END, eta=NOW + timedelta(hours=6), confidence=timedelta(hours=2)),
        )
        # A machine that is not in the layout any more (ADR-048 section 3).
        triggers.raise_finding(
            conn, detected(MachineId("MC-999"), rule_id="R-gone", symptom_code="SYM-099")
        )

        for severity in (Severity.HIGH, Severity.LOW):
            orders.from_report(
                conn,
                machine_id=BOTTLENECK if severity is Severity.HIGH else BUFFERED,
                machine_model=R2000,
                severity=severity,
                reported_by=UserId("sup-1"),
                description="reported by the shift lead",
            )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield pool
    finally:
        pool.close()


def _client(
    pool: ConnectionPool, clock: SimulatedClock, tmp_path: Path, config_dir: Path
) -> Iterator[TestClient]:
    from pdm.api.app import create_app

    app = create_app(
        pool=pool,
        library=DocumentLibrary(FilesystemObjectStore(tmp_path / "store"), clock),
        clock=clock,
        config_dir=config_dir,
    )
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client(world: ConnectionPool, clock: SimulatedClock, tmp_path: Path) -> Iterator[TestClient]:
    yield from _client(world, clock, tmp_path, Path("config"))


def _signed_in(client: TestClient, role: Role) -> TestClient:
    user, _ = PEOPLE[role]
    assert (
        client.post("/sessions", json={"user": str(user), "password": PASSWORD}).status_code == 201
    )
    return client


@pytest.mark.db
class TestTheLineEndpoint:
    def test_the_stations_arrive_in_line_order_with_their_buffers(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/overview/line").json()

        stations = body["lines"][0]["stations"]
        assert [one["station_id"] for one in stations] == ["st-01", "st-02", "st-03", "st-04"]
        assert [one["buffer_units"] for one in stations] == [20, 8, 0, 12]
        # 20 units at a 60s takt is twenty minutes of cover (ADR-021).
        assert stations[0]["buffer_minutes"] == pytest.approx(20.0)
        assert [one["bottleneck"] for one in stations] == [False, False, True, False]

    def test_moving_a_buffer_in_the_config_moves_it_on_the_response(
        self, world: ConnectionPool, clock: SimulatedClock, tmp_path: Path
    ) -> None:
        """ADR-021's promise that the real buffer map changes a file and nothing
        else. If any of these numbers were in code, this is the test that fails.
        """
        seen = []
        for buffers in ({"st-01": 20, "st-03": 0}, {"st-01": 4, "st-03": 30}):
            for test_client in _client(
                world, clock, tmp_path, _config_dir(tmp_path, buffers=buffers)
            ):
                _signed_in(test_client, Role.SUPERVISOR)
                body = test_client.get("/overview/line").json()
                seen.append(
                    {
                        one["station_id"]: (one["buffer_units"], one["buffer_minutes"])
                        for one in body["lines"][0]["stations"]
                    }
                )

        assert seen[0]["st-01"] == (20, pytest.approx(20.0))
        assert seen[1]["st-01"] == (4, pytest.approx(4.0))
        assert seen[1]["st-03"] == (30, pytest.approx(30.0))

    def test_a_predicted_station_never_serialises_an_eta_without_its_interval(
        self, client: TestClient
    ) -> None:
        """The pair is the contract (ADR-020), asserted where it would be
        dropped: on the wire, not in the model that was already checked."""
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/overview/line").json()

        predictions = [
            one for line in body["lines"] for one in line["stations"] if one["state"] == "predicted"
        ]
        assert predictions, "the fixture raised a prediction; the endpoint lost it"
        for one in predictions:
            assert one["eta"] is not None
            assert one["eta_confidence_minutes"] is not None

    def test_the_station_over_its_threshold_says_for_how_long(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/overview/line").json()

        by_id = {one["station_id"]: one for one in body["lines"][0]["stations"]}
        assert by_id["st-03"]["state"] == "over_threshold"
        assert by_id["st-03"]["over_threshold_minutes"] == 20
        assert by_id["st-01"]["state"] == "normal"

    def test_a_machine_that_left_the_layout_is_named(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/overview/line").json()

        assert body["unplaced_machines"] == ["MC-999"]

    def test_the_shift_band_is_the_round_and_not_a_second_summation(
        self, client: TestClient
    ) -> None:
        """ADR-050: one implementation of the gate produces both the decision and
        every screen that reports it. A copy is a thing that can drift, quietly,
        because both would look plausible."""
        _signed_in(client, Role.SUPERVISOR)

        overview = client.get("/overview/line").json()["shift"]
        the_round = client.get("/dispatch/round").json()

        assert overview["band"] == the_round["band"]
        assert overview["load_ratio"] == the_round["load_ratio"]
        assert overview["capacity_minutes"] == the_round["capacity_minutes"]
        assert overview["committed_minutes"] == the_round["committed_minutes"]
        assert overview["held"] == len(the_round["held"])
        assert overview["shift_id"] == the_round["shift_id"]
        assert overview["summary"] == the_round["summary"]

    def test_the_open_queue_is_read_once(
        self, client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "Nothing on the response is computed twice" as something the build can
        check. A second pass over the same orders is how the screen and the
        scheduler come to disagree."""
        from pdm.work import repo as work_repo

        original = work_repo.open_orders
        calls: list[int] = []

        def counted(*args: Any, **kwargs: Any) -> Any:
            calls.append(1)
            return original(*args, **kwargs)

        monkeypatch.setattr(work_repo, "open_orders", counted)

        _signed_in(client, Role.SUPERVISOR)
        assert client.get("/overview/line").status_code == 200

        assert len(calls) == 1

    def test_the_shift_names_how_many_people_are_on_it_and_how_much_is_open(
        self, client: TestClient
    ) -> None:
        _signed_in(client, Role.SUPERVISOR)

        shift = client.get("/overview/line").json()["shift"]

        assert shift["technicians_on_shift"] == 1
        assert shift["open_orders"] == 2

    def test_the_time_it_was_computed_comes_from_the_clock(self, client: TestClient) -> None:
        _signed_in(client, Role.SUPERVISOR)

        body = client.get("/overview/line").json()

        assert datetime.fromisoformat(body["at"].replace("Z", "+00:00")) == NOW
        assert body["timezone"] == "Asia/Bangkok"

    def test_an_engineer_may_read_it_and_a_technician_may_not(self, client: TestClient) -> None:
        _signed_in(client, Role.ENGINEER)
        assert client.get("/overview/line").status_code == 200

        _signed_in(client, Role.TECHNICIAN)
        assert client.get("/overview/line").status_code == 403

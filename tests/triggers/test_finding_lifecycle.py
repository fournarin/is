"""The Finding lifecycle against a real PostgreSQL (ADR-023, ADR-042).

The pure tests next door prove what the engine decides. These prove the store
holds it: one live record per (machine, rule) whatever anybody writes, a count
that survives two workers, a cooldown that starts when the condition ended, and a
prediction that is superseded rather than duplicated when the thing it predicted
happens.

The one to read first is `TestInvariantEight::test_the_database_refuses_a_second
_live_finding_whoever_writes_it`. The alarm flood ADR-023 was written about is
the failure that ends the system in its first hour on real data, and a defence
that lives only in a query is a defence until somebody writes a second query.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    FindingRef,
    FindingStatus,
    MachineId,
    RuleId,
    Severity,
    Signal,
    SymptomCode,
)
from pdm.platform.clock import SimulatedClock
from pdm.platform.config import load_config
from pdm.triggers import Triggers
from pdm.triggers import repo as findings
from pdm.triggers.repo import AlreadyLive

pytestmark = pytest.mark.db

NOW = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MOTOR = MachineId("MC-001")
BELT_MOTOR = ComponentLabel("belt_motor")
TEMP_RULE = RuleId("R-motor-temp-high")

CONFIG = load_config(Path("config"))
COOLDOWN = timedelta(minutes=CONFIG.policy.triggers.cooldown_minutes)
GRACE = timedelta(minutes=CONFIG.policy.triggers.eta_grace_minutes)


@pytest.fixture
def conn() -> Iterator[Connection[Any]]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    connection = connect(url)
    try:
        connection.execute("TRUNCATE finding CASCADE")
        connection.commit()
        yield connection
    finally:
        connection.rollback()
        connection.close()


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(NOW)


@pytest.fixture
def triggers(clock: SimulatedClock) -> Triggers:
    return Triggers(clock, CONFIG.rules.rules, cooldown=COOLDOWN, eta_grace=GRACE)


def _hot(at: datetime, value: float = 91.0) -> Signal:
    return Signal(timestamp=at, machine_id=MOTOR, metric_name="motor_temp_c", value=value, unit="C")


def _two_minutes_of_heat(start: datetime = NOW) -> list[Signal]:
    """Enough to satisfy the rule's `for_seconds`, sampled every thirty seconds.

    Six samples: the first four are inside the two minutes the rule requires, the
    fifth reaches it and raises, and the sixth is the first repeat. Those counts
    are asserted below rather than rounded off, because "about right" in a
    debounce is how a rule ends up firing on a single spike.
    """
    return [_hot(start + timedelta(seconds=30 * step)) for step in range(6)]


def _prediction(at: datetime, *, eta_in: timedelta = timedelta(hours=6)) -> Finding:
    return Finding(
        machine_id=MOTOR,
        component=BELT_MOTOR,
        symptom_code=SymptomCode("SYM-014"),
        severity=Severity.HIGH,
        rule_id=RuleId("R-motor-temp-trend"),
        detected_at=at,
        evidence={"slope_per_hour": 1.4},
        kind=FindingKind.PREDICTED,
        eta=at + eta_in,
        eta_confidence=timedelta(hours=2),
    )


class TestRaisingOne:
    def test_two_minutes_of_heat_becomes_one_finding(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        observed = triggers.observe(conn, _two_minutes_of_heat())

        assert len(observed.raised) == 1
        assert observed.raised[0].finding_ref.startswith("F-")
        stored = findings.get(conn, observed.raised[0].finding_ref)
        assert stored is not None
        assert stored.status is FindingStatus.OPEN
        assert stored.evidence["threshold"] == 85.0

    def test_a_single_hot_sample_becomes_nothing(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        observed = triggers.observe(conn, [_hot(NOW)])

        assert observed.raised == ()
        assert observed.quiet == 1
        assert findings.live(conn) == {}


class TestInvariantEight:
    """One rule firing repeatedly is one Finding, whoever is writing."""

    def test_a_hundred_more_readings_update_the_one_record(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        triggers.observe(conn, _two_minutes_of_heat())
        later = [_hot(NOW + timedelta(minutes=5 + index)) for index in range(100)]

        observed = triggers.observe(conn, later)

        assert observed.raised == ()
        assert observed.repeated == 100
        live = findings.live(conn)
        assert len(live) == 1
        # 1 on creation, 1 from the last signal of the first batch, 100 here.
        assert live[(MOTOR, TEMP_RULE)].occurrence_count == 102

    def test_the_database_refuses_a_second_live_finding_whoever_writes_it(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """A defence that lives only in a query is a defence until somebody
        writes a second query. This one is a partial unique index.
        """
        triggers.observe(conn, _two_minutes_of_heat())
        live = findings.live(conn)
        duplicate = live[(MOTOR, TEMP_RULE)]

        with pytest.raises(AlreadyLive):
            findings.raise_finding(conn, duplicate)
        conn.rollback()

    def test_a_resolved_finding_frees_the_pair_again(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        observed = triggers.observe(conn, _two_minutes_of_heat())
        triggers.resolve(conn, observed.raised[0].finding_ref)
        clock.advance(COOLDOWN + timedelta(minutes=1))

        again = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=2)))

        assert len(again.raised) == 1


class TestTheCooldown:
    """ADR-023 section 3, with the value from policy.yaml rather than a literal."""

    def test_inside_the_cooldown_the_rule_stays_quiet(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        observed = triggers.observe(conn, _two_minutes_of_heat())
        triggers.resolve(conn, observed.raised[0].finding_ref)
        clock.advance(COOLDOWN - timedelta(minutes=5))

        again = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(minutes=20)))

        assert again.raised == ()
        # All six, not two: the value never came back inside the threshold, so
        # the debounce still holds from the first batch and every sample clears
        # the two minutes immediately. That is the machine still being hot while
        # the Finding it raised has been marked resolved - which is exactly the
        # oscillation the cooldown is for.
        assert again.in_cooldown == 6

    def test_the_cooldown_is_measured_from_when_it_was_resolved(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        """Not from when it was raised. A Finding open for a day and resolved a
        minute ago is a condition that ended a minute ago."""
        observed = triggers.observe(conn, _two_minutes_of_heat())
        clock.advance(timedelta(days=1))
        triggers.resolve(conn, observed.raised[0].finding_ref)

        again = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(days=1, hours=1)))

        assert again.raised == ()
        assert again.in_cooldown > 0


class TestSupersession:
    """ADR-023 section 7, which is also ADR-020's measurement point."""

    def test_a_detection_supersedes_the_prediction_that_foresaw_it(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        predicted = findings.raise_finding(conn, _prediction(NOW))

        observed = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=1)))

        assert observed.raised[0].superseded == predicted
        assert findings.status_of(conn, predicted) is FindingStatus.SUPERSEDED

    def test_the_superseded_record_names_what_replaced_it(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """The moment a prediction is superseded is the moment its error becomes
        known, and an error nobody can attribute to a forecast measures
        nothing (ADR-020)."""
        predicted = findings.raise_finding(conn, _prediction(NOW))

        observed = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=1)))

        stored = findings.get(conn, predicted)
        assert stored is not None
        assert stored.superseded_by == observed.raised[0].finding_ref

    def test_a_prediction_about_another_component_is_left_alone(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        other = _prediction(NOW).model_copy(update={"component": ComponentLabel("cooling_fan")})
        predicted = findings.raise_finding(conn, other)

        triggers.observe(conn, _two_minutes_of_heat())

        assert findings.status_of(conn, predicted) is FindingStatus.OPEN


class TestExpiry:
    """ADR-023 section 6: a prediction whose moment passed without event."""

    def test_a_prediction_past_its_eta_and_grace_expires(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        predicted = findings.raise_finding(conn, _prediction(NOW, eta_in=timedelta(hours=6)))
        clock.advance(timedelta(hours=6) + GRACE + timedelta(minutes=1))

        expired = triggers.expire_stale_predictions(conn)

        assert expired == [predicted]
        assert findings.status_of(conn, predicted) is FindingStatus.EXPIRED

    def test_one_still_inside_its_grace_is_left_open(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        predicted = findings.raise_finding(conn, _prediction(NOW, eta_in=timedelta(hours=6)))
        clock.advance(timedelta(hours=6) + GRACE - timedelta(minutes=5))

        assert triggers.expire_stale_predictions(conn) == []
        assert findings.status_of(conn, predicted) is FindingStatus.OPEN

    def test_an_expired_prediction_is_kept_rather_than_deleted(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        """A prediction that did not come true is half of the accuracy
        measurement. A table holding only the successful ones would describe a
        system that never gets it wrong (ADR-020)."""
        predicted = findings.raise_finding(conn, _prediction(NOW))
        clock.advance(timedelta(days=1))
        triggers.expire_stale_predictions(conn)

        assert findings.get(conn, predicted) is not None


class TestAcknowledgement:
    def test_an_acknowledged_finding_still_suppresses(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """Somebody having seen it does not mean it stopped happening."""
        observed = triggers.observe(conn, _two_minutes_of_heat())
        triggers.acknowledge(conn, observed.raised[0].finding_ref)

        again = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(minutes=30)))

        assert again.raised == ()
        assert again.repeated > 0

    def test_acknowledging_something_already_acknowledged_changes_nothing(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        observed = triggers.observe(conn, _two_minutes_of_heat())
        ref = observed.raised[0].finding_ref

        assert triggers.acknowledge(conn, ref) is True
        assert triggers.acknowledge(conn, ref) is False


class TestWhatTheBatchReports:
    def test_the_counts_separate_the_kinds_of_silence(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """A rule suppressed a thousand times an hour and a rule that fires once
        are different problems; a return value holding only the Findings would
        make them look the same."""
        triggers.observe(conn, _two_minutes_of_heat())

        observed = triggers.observe(
            conn,
            _two_minutes_of_heat(NOW + timedelta(minutes=10)),
            under_repair={MOTOR: Severity.CRITICAL},
        )

        assert observed.repeated == 6
        assert observed.anything_happened is True

    def test_a_second_breach_inside_one_batch_is_a_repeat_not_a_second_record(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """The in-memory copy of what is live is corrected as the batch raises.

        Without that the unique index refuses the second insert - correctly - and
        the batch ends in an exception rather than in a count.
        """
        signals = [
            *_two_minutes_of_heat(),
            _hot(NOW + timedelta(minutes=5)),
            _hot(NOW + timedelta(minutes=6)),
        ]

        observed = triggers.observe(conn, signals)

        assert len(observed.raised) == 1
        # One from the last sample of the two minutes, two from the extra pair.
        assert observed.repeated == 3
        assert len(findings.live(conn)) == 1


class TestNothingHereReadsTheWallClock:
    def test_detected_at_follows_the_simulated_clock(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        """A compressed demo must produce Findings stamped with the demo's time,
        or the ETA measurement is measuring the wrong axis (ADR-028)."""
        clock.advance(timedelta(days=30))

        observed = triggers.observe(conn, _two_minutes_of_heat())

        stored = findings.get(conn, observed.raised[0].finding_ref)
        assert stored is not None
        assert stored.detected_at == NOW + timedelta(days=30)


def _ref(observed: Any) -> FindingRef:  # pragma: no cover - readability helper
    return FindingRef(observed.raised[0].finding_ref)


class TestWhatMutationTestingFound:
    def test_a_repeat_touches_only_the_live_record(
        self, conn: Connection[Any], triggers: Triggers, clock: SimulatedClock
    ) -> None:
        """The status filter on the UPDATE, which no test noticed was missing.

        Without it a repeat matches every historical Finding for the pair as
        well: the resolved ones have their occurrence_count changed - corrupting
        the record of how often that rule fired before somebody fixed it - and
        `rowcount == 1` becomes False, so the function reports failure while
        having written to three rows.
        """
        first = triggers.observe(conn, _two_minutes_of_heat())
        old_ref = first.raised[0].finding_ref
        triggers.resolve(conn, old_ref)
        old = findings.get(conn, old_ref)
        assert old is not None
        count_when_resolved = old.occurrence_count

        clock.advance(COOLDOWN + timedelta(minutes=1))
        second = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=2)))
        assert second.raised

        untouched = findings.get(conn, old_ref)
        assert untouched is not None
        assert untouched.occurrence_count == count_when_resolved
        assert untouched.status is FindingStatus.RESOLVED

    def test_a_duplicate_does_not_poison_the_whole_transaction(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """The batch that hits this is writing other Findings in the same
        transaction (ADR-017). Without a savepoint, one collision aborts all of
        it - and the collision is the case where suppression is working."""
        observed = triggers.observe(conn, _two_minutes_of_heat())
        live = findings.live(conn)

        with pytest.raises(AlreadyLive):
            findings.raise_finding(conn, live[(MOTOR, TEMP_RULE)])

        # The connection is still usable: no rollback, no aborted transaction.
        assert findings.status_of(conn, observed.raised[0].finding_ref) is FindingStatus.OPEN

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
        # 98, not 100: this batch starts five minutes after the last one ended,
        # which is longer than the rule's own window, so the run is treated as
        # new and the first two readings are inside the debounce again. A gap
        # that long is a stream nobody was watching, and the alternative - a
        # Finding claiming five minutes of sustained excess on the strength of
        # one sample - is the failure the gap check exists for.
        assert observed.repeated == 98
        live = findings.live(conn)
        assert len(live) == 1
        # 1 on creation, 1 from the last signal of the first batch, 98 here.
        assert live[(MOTOR, TEMP_RULE)].occurrence_count == 100

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
        # Two: the batch arrives twenty minutes later, which is a gap longer than
        # the rule's window, so the run restarts and the first four samples are
        # back inside the debounce. The two that clear it meet the cooldown -
        # which is the machine hot again while the Finding it raised has been
        # marked resolved, exactly the oscillation ADR-023 section 3 is about.
        assert again.in_cooldown == 2

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
            under_repair={MOTOR: frozenset({RuleId("R-motor-temp-high")})},
        )

        # Two of the six: the batch is ten minutes after the last, so the run
        # restarts and four samples are spent re-establishing it.
        assert observed.repeated == 2
        assert observed.anything_happened is True

    def test_a_second_breach_inside_one_batch_is_a_repeat_not_a_second_record(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """The in-memory copy of what is live is corrected as the batch raises.

        Without that the unique index refuses the second insert - correctly - and
        the batch ends in an exception rather than in a count.
        """
        # Kept continuous on purpose: this is about two breaches inside one
        # batch, not about what a gap does to the run.
        signals = [_hot(NOW + timedelta(seconds=30 * step)) for step in range(9)]

        observed = triggers.observe(conn, signals)

        assert len(observed.raised) == 1
        # The fifth sample raises; the four after it are repeats.
        assert observed.repeated == 4
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

    def test_a_raise_another_worker_got_to_first_is_counted_not_thrown(
        self, conn: Connection[Any], triggers: Triggers, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two workers on one machine, which is what the unique index is for.

        Forced rather than raced: a genuine interleaving needs two connections
        and a timing assumption, and what has to be proved here is not that
        PostgreSQL locks correctly but that **the batch survives**. The batch
        that loses is also writing other Findings and work orders in the same
        transaction (ADR-017), and ending it with an exception would discard all
        of that in the case where suppression is working.
        """

        def already_live(*args: Any, **kwargs: Any) -> FindingRef:
            raise AlreadyLive("another worker raised it first")

        monkeypatch.setattr(findings, "raise_finding", already_live)

        observed = triggers.observe(conn, _two_minutes_of_heat())

        assert observed.raised == ()
        # Both of the samples that cleared the debounce: the in-memory copy is
        # only corrected when a raise succeeds, so every later breach in the
        # batch tries and loses too. Counted, every time, rather than ending the
        # batch on the first one.
        assert observed.lost_races == 2
        assert observed.quiet == 4

    def test_a_supersession_that_matched_nothing_is_not_reported(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """Reported from the lookup rather than from the UPDATE, this handed
        ADR-020's accuracy loop a measurement of something that never
        happened."""
        predicted = findings.raise_finding(conn, _prediction(NOW))
        findings.resolve(conn, predicted, now=NOW)

        observed = triggers.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=1)))

        assert observed.raised[0].superseded is None

    def test_a_finding_is_written_in_the_callers_transaction(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """ADR-017's pairing, which an earlier savepoint quietly broke.

        `conn.transaction()` opens a real transaction when none is running, so a
        Finding raised as the first statement on a connection committed on its
        own - and a rollback of the work order it belonged to would have left it
        behind.
        """
        observed = triggers.observe(conn, _two_minutes_of_heat())
        assert observed.raised
        conn.rollback()

        assert findings.live(conn) == {}


class TestPredictedFindings:
    """The other half of ADR-020, through the same lifecycle as detection."""

    @pytest.fixture
    def predicting(self, clock: SimulatedClock) -> Triggers:
        return Triggers(
            clock,
            CONFIG.rules.rules,
            cooldown=COOLDOWN,
            eta_grace=GRACE,
            trend_window=timedelta(minutes=CONFIG.policy.triggers.trend.window_minutes),
            trend_min_samples=CONFIG.policy.triggers.trend.min_samples,
            trend_horizon=timedelta(hours=CONFIG.policy.triggers.trend.max_horizon_hours),
        )

    def _warming(self, *, per_hour: float = 2.0, count: int = 24) -> list[Signal]:
        """Rising towards 85 but not there yet, every five minutes."""
        step = per_hour * (5 / 60)
        return [
            _hot(NOW + timedelta(minutes=5 * index), value=70.0 + step * index)
            for index in range(count)
        ]

    def test_a_rising_trend_raises_a_predicted_finding(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        observed = predicting.observe(conn, self._warming())

        assert observed.forecast
        assert observed.raised == ()
        stored = findings.get(conn, observed.forecast[0].finding_ref)
        assert stored is not None
        assert stored.kind is FindingKind.PREDICTED
        assert stored.eta is not None and stored.eta_confidence is not None

    def test_the_forecast_is_filed_under_its_own_rule_id(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        """ADR-043 section 4. Filed under the threshold rule's id, the detection
        that should supersede it could not be written at all: the unique index
        would refuse it first."""
        observed = predicting.observe(conn, self._warming())

        assert observed.forecast[0].decision.rule_id == "R-motor-temp-high/trend"
        live = findings.live(conn)
        assert (MOTOR, RuleId("R-motor-temp-high/trend")) in live

    def test_a_prediction_and_its_detection_can_both_be_live(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        """And the detection then supersedes it, which is where a prediction's
        error becomes measurable (ADR-023 section 7, ADR-020)."""
        predicting.observe(conn, self._warming())
        forecast_ref = findings.live(conn)[(MOTOR, RuleId("R-motor-temp-high/trend"))]
        assert forecast_ref.kind is FindingKind.PREDICTED

        observed = predicting.observe(conn, _two_minutes_of_heat(NOW + timedelta(hours=3)))

        assert observed.raised
        assert observed.raised[0].superseded is not None
        assert findings.status_of(conn, observed.raised[0].superseded) is FindingStatus.SUPERSEDED

    def test_the_same_forecast_updates_rather_than_duplicating(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        """Invariant 8 covers forecasts too: a window that keeps predicting the
        same crossing is one record with a count, not a record a minute."""
        predicting.observe(conn, self._warming())

        predicting.observe(conn, self._warming(count=30)[24:])

        live = findings.live(conn)
        forecasts = [key for key in live if key[1].endswith("/trend")]
        assert len(forecasts) == 1

    def test_prediction_is_off_when_no_window_is_configured(
        self, conn: Connection[Any], triggers: Triggers
    ) -> None:
        """The detection-only engine the rest of this file uses. A mechanism that
        could not be turned off would have to be reasoned about in every test of
        the other half."""
        observed = triggers.observe(conn, self._warming())

        assert observed.forecast == ()

    def test_a_resolved_forecast_is_not_re_raised_on_the_next_reading(
        self, conn: Connection[Any], predicting: Triggers, clock: SimulatedClock
    ) -> None:
        """Detections had the cooldown and forecasts did not.

        A technician who looked, found nothing and resolved the prediction would
        have had it back on the next sample - ADR-023 section 3's oscillating
        sensor wearing a different hat.
        """
        first = predicting.observe(conn, self._warming())
        predicting.resolve(conn, first.forecast[0].finding_ref)

        again = predicting.observe(conn, self._warming(count=30)[24:])

        assert again.forecast == ()
        assert again.in_cooldown > 0

    def test_a_forecast_does_not_supersede_another_forecast(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        """Supersession is a detection meeting the prediction that foresaw it
        (ADR-023 section 7). A forecast marking an older forecast superseded
        would hand ADR-020's accuracy loop a crossing that never happened."""
        observed = predicting.observe(conn, self._warming())

        assert observed.forecast[0].superseded is None

    def test_a_refit_moves_the_eta_rather_than_only_counting(
        self, conn: Connection[Any], predicting: Triggers
    ) -> None:
        """Otherwise a live prediction carries its first window's answer for
        life, and a technician checking at noon reads a crossing computed at
        eight from data six hours stale."""
        predicting.observe(conn, self._warming())
        first = findings.live(conn)[(MOTOR, RuleId("R-motor-temp-high/trend"))]

        # Steeper: the machine is heating faster than the first window suggested.
        steeper = [
            _hot(NOW + timedelta(minutes=120 + 5 * index), value=80.0 + 0.5 * index)
            for index in range(12)
        ]
        predicting.observe(conn, steeper)

        after = findings.live(conn)[(MOTOR, RuleId("R-motor-temp-high/trend"))]
        assert first.eta is not None and after.eta is not None
        assert after.eta != first.eta
        assert after.occurrence_count > first.occurrence_count

    def test_the_eta_is_on_the_clock_the_system_decides_by(
        self, conn: Connection[Any], predicting: Triggers, clock: SimulatedClock
    ) -> None:
        """ADR-028's two axes, joined where they have to be.

        The crossing is computed in source time; `eta` is read by the expiry
        sweep, the scheduler and the screen, which all live in decision time.
        Stored as source time, a replayed scenario would have every prediction
        expired the moment it was written.
        """
        clock.advance(timedelta(days=400))
        observed = predicting.observe(conn, self._warming())
        assert observed.forecast

        stored = findings.get(conn, observed.forecast[0].finding_ref)
        assert stored is not None and stored.eta is not None
        assert stored.eta > clock.now()
        assert predicting.expire_stale_predictions(conn) == []

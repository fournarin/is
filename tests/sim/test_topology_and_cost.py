"""The line, the buffers, and what a stopped machine costs (ADR-021).

The whole reason this simulator models topology is that two identical faults are
not equally expensive. A test suite that only checked "the fault was repaired"
would pass just as happily against a simulator that costed downtime per line,
and the comparison in slice 7.3 would then be measuring nothing.

So the tests here are written to fail against a per-line constant: an outage
shorter than the buffer at st-01 costs nothing at all, the same outage at the
unbuffered bottleneck costs three times its length in units, and no single
number per line can produce both.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pdm.contracts import LineId, MachineId, StationId
from pdm.platform.config import load_config
from pdm.sim import ProductionLine

REPO_CONFIG = Path("config")
LINE_A = LineId("line-a")

# st-01: twenty units of buffer, no bottleneck multiplier.
BUFFERED = MachineId("MC-001")
# st-03: no buffer, multiplier 3.0. The station plant.yaml exists to describe.
BOTTLENECK = MachineId("MC-012")


@pytest.fixture(scope="module")
def line() -> ProductionLine:
    return ProductionLine.from_config(load_config(REPO_CONFIG), LINE_A)


class TestTheLineComesFromConfig:
    def test_stations_are_ordered_along_the_line(self, line: ProductionLine) -> None:
        """Ascending seq, because a line is a sequence and buffers sit between
        consecutive stations. Reading them in file order would be right by
        accident today and wrong the first time somebody appends a station."""
        assert [station.seq for station in line.stations] == sorted(
            station.seq for station in line.stations
        )

    def test_every_machine_resolves_to_the_station_it_stands_at(self, line: ProductionLine) -> None:
        assert line.station_of(BUFFERED).station_id == StationId("st-01")
        assert line.station_of(BOTTLENECK).station_id == StationId("st-03")

    def test_a_machine_on_another_line_is_an_error_rather_than_a_zero(
        self, line: ProductionLine
    ) -> None:
        """Scoring an unknown machine at zero would make a whole station's work
        look free, and nothing would report it (invariant 13)."""
        with pytest.raises(KeyError):
            line.station_of(MachineId("MC-999"))

    def test_the_takt_becomes_a_production_rate(self, line: ProductionLine) -> None:
        # plant.yaml: 60 seconds a unit, so one unit a minute.
        assert line.units_per_minute == pytest.approx(1.0)

    def test_an_unknown_line_is_refused(self) -> None:
        with pytest.raises(KeyError):
            ProductionLine.from_config(load_config(REPO_CONFIG), LineId("line-z"))


class TestWhatAStoppedMachineCosts:
    """ADR-021: rate x max(0, downtime - buffer) x bottleneck multiplier."""

    def test_the_buffer_absorbs_a_short_outage_completely(self, line: ProductionLine) -> None:
        station = line.station_of(BUFFERED)
        # Twenty units at one a minute is twenty minutes of cover.
        assert line.units_lost(station, 15.0) == pytest.approx(0.0)

    def test_beyond_the_buffer_only_the_excess_is_lost(self, line: ProductionLine) -> None:
        station = line.station_of(BUFFERED)
        assert line.units_lost(station, 30.0) == pytest.approx(10.0)

    def test_the_bottleneck_pays_from_the_first_minute_and_pays_more(
        self, line: ProductionLine
    ) -> None:
        station = line.station_of(BOTTLENECK)
        # No buffer, multiplier 3.0: thirty minutes down, ninety units gone.
        assert line.units_lost(station, 30.0) == pytest.approx(90.0)

    def test_the_same_fault_costs_differently_at_two_stations(self, line: ProductionLine) -> None:
        """The test a per-line constant cannot pass.

        One outage, one duration, two stations, and the ratio between them is
        nine to one. Replace `units_lost` with anything that does not read the
        station and this assertion fails, which is what it is here for.
        """
        buffered = line.units_lost(line.station_of(BUFFERED), 30.0)
        bottleneck = line.units_lost(line.station_of(BOTTLENECK), 30.0)
        assert bottleneck > buffered
        assert bottleneck == pytest.approx(9.0 * buffered)

    def test_a_negative_outage_is_refused(self, line: ProductionLine) -> None:
        """Time does not run backwards here either (ADR-028). Silently clamping
        would hide an engine that closed an outage before it opened."""
        with pytest.raises(ValueError, match="negative"):
            line.units_lost(line.station_of(BUFFERED), -1.0)

    def test_a_station_from_another_line_cannot_be_costed(self, line: ProductionLine) -> None:
        other = line.stations[0].model_copy(update={"line_id": LineId("line-b")})
        with pytest.raises(ValueError, match="line-a"):
            line.units_lost(other, 30.0)


class TestBufferMinutes:
    def test_buffer_cover_is_units_times_takt(self, line: ProductionLine) -> None:
        """Sanity on the unit conversion, which is the easiest thing here to get
        wrong by a factor of sixty."""
        assert line.station_of(BUFFERED).buffer_minutes(line.line) == pytest.approx(20.0)
        assert line.station_of(BOTTLENECK).buffer_minutes(line.line) == pytest.approx(0.0)


def test_the_window_of_a_scenario_is_not_needed_to_cost_an_outage(
    line: ProductionLine,
) -> None:
    """`units_lost` takes minutes, not two datetimes, so an outage still open at
    the end of a run can be costed against the part that happened."""
    began = datetime(2026, 3, 3, 6, 0, tzinfo=UTC)
    ended = began + timedelta(minutes=45)
    minutes = (ended - began).total_seconds() / 60.0
    assert line.units_lost(line.station_of(BOTTLENECK), minutes) == pytest.approx(135.0)

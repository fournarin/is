"""A plant export read back as signals (ADR-091).

The specification is the `SignalSource` port and ADR-091, not the parser: time
never goes backwards, a reading is emitted once, and a file that cannot be read
honestly is refused with every bad line named.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pdm.platform.clock import SystemClock
from pdm.signals import Feed, ReplayFileError, ReplaySource, SignalSource
from pdm.signals.replay import parse
from pdm.workers.runtime.__main__ import build_feed

HEADER = "timestamp,machine_id,metric_name,value,unit\n"


def _lines(*rows: str) -> list[str]:
    return [HEADER, *(f"{row}\n" for row in rows)]


class TestWhatAFileBecomes:
    def test_rows_become_signals_with_their_source_time(self) -> None:
        signals = parse(_lines("2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68.2,C"))

        assert len(signals) == 1
        assert signals[0].timestamp == datetime(2026, 3, 1, 23, 0, tzinfo=UTC)
        assert signals[0].machine_id == "R-01"
        assert signals[0].value == 68.2

    def test_an_export_grouped_by_tag_comes_out_in_time_order(self) -> None:
        signals = parse(
            _lines(
                "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68,C",
                "2026-03-02T06:02:00+07:00,R-01,motor_temp_c,70,C",
                "2026-03-02T06:01:00+07:00,R-01,servo_current_a,9,A",
            )
        )

        times = [signal.timestamp for signal in signals]
        assert times == sorted(times)
        assert [signal.metric_name for signal in signals][1] == "servo_current_a"

    def test_an_exact_duplicate_from_overlapping_exports_is_emitted_once(self) -> None:
        row = "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68,C"
        assert len(parse(_lines(row, row))) == 1

    def test_two_values_for_one_tag_at_one_instant_are_both_kept(self) -> None:
        signals = parse(
            _lines(
                "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68,C",
                "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,91,C",
            )
        )
        assert [signal.value for signal in signals] == [68, 91]

    def test_columns_may_come_in_any_order_and_with_a_byte_order_mark(self, tmp_path: Path) -> None:
        path = tmp_path / "export.csv"
        path.write_text(
            "unit,value,metric_name,machine_id,timestamp\r\nC,68,motor_temp_c,R-01,"
            "2026-03-02T06:00:00+07:00\r\n",
            encoding="utf-8-sig",
        )

        assert [signal.value for signal in ReplaySource(path).stream()] == [68]


class TestWhatIsRefused:
    def test_a_timestamp_with_no_offset_is_refused_rather_than_guessed(self) -> None:
        with pytest.raises(ReplayFileError, match=r":2: .*no UTC offset"):
            parse(_lines("2026-03-02T06:00:00,R-01,motor_temp_c,68,C"))

    def test_every_bad_line_is_named_not_only_the_first(self) -> None:
        with pytest.raises(ReplayFileError) as refused:
            parse(
                _lines(
                    "yesterday,R-01,motor_temp_c,68,C",
                    "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,hot,C",
                    "2026-03-02T06:00:00+07:00,,motor_temp_c,68,C",
                    "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,nan,C",
                )
            )

        message = str(refused.value)
        for line in (":2:", ":3:", ":4:", ":5:"):
            assert line in message

    def test_a_header_that_is_not_the_signal_contract_is_refused(self) -> None:
        with pytest.raises(ReplayFileError, match="missing unit"):
            parse(["timestamp,machine_id,metric_name,value\n"])

    def test_a_file_with_no_readings_is_refused(self) -> None:
        with pytest.raises(ReplayFileError, match="no signals"):
            parse([HEADER])


class TestItIsASignalSource:
    def test_it_satisfies_the_port(self, tmp_path: Path) -> None:
        assert isinstance(ReplaySource(tmp_path / "x.csv"), SignalSource)

    def test_constructing_it_opens_nothing(self, tmp_path: Path) -> None:
        ReplaySource(tmp_path / "does-not-exist.csv")

    def test_a_feed_hands_it_over_against_decision_time(self, tmp_path: Path) -> None:
        path = tmp_path / "export.csv"
        path.write_text(
            "".join(
                _lines(
                    "2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68,C",
                    "2026-03-02T06:10:00+07:00,R-01,motor_temp_c,70,C",
                )
            ),
            encoding="utf-8",
        )
        origin = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)
        feed = Feed(ReplaySource(path), decision_origin=origin)

        assert [signal.value for signal in feed.due(origin)] == [68]
        assert [signal.value for signal in feed.due(origin + timedelta(minutes=10))] == [70]


class TestTheRuntimeWorkerChoosesIt:
    def test_replay_reads_the_file_named_in_the_environment(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "export.csv"
        path.write_text(
            "".join(_lines("2026-03-02T06:00:00+07:00,R-01,motor_temp_c,68,C")),
            encoding="utf-8",
        )
        monkeypatch.setenv("SIGNAL_SOURCE", "replay")
        monkeypatch.setenv("SIGNAL_REPLAY_FILE", str(path))

        assert build_feed(SystemClock()) is not None

    def test_replay_without_a_file_stops_the_boot(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIGNAL_SOURCE", "replay")
        monkeypatch.delenv("SIGNAL_REPLAY_FILE", raising=False)

        with pytest.raises(ValueError, match="SIGNAL_REPLAY_FILE"):
            build_feed(SystemClock())

    def test_a_bad_export_stops_the_boot_with_its_line_numbers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        path = tmp_path / "export.csv"
        path.write_text("".join(_lines("2026-03-02T06:00:00,R-01,m,1,C")), encoding="utf-8")
        monkeypatch.setenv("SIGNAL_SOURCE", "replay")
        monkeypatch.setenv("SIGNAL_REPLAY_FILE", str(path))

        with pytest.raises(ReplayFileError, match=r"export\.csv:2"):
            build_feed(SystemClock())

    def test_live_is_still_refused_by_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SIGNAL_SOURCE", "live")

        with pytest.raises(ValueError, match="not built yet"):
            build_feed(SystemClock())

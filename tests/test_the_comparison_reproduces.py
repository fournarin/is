"""The comparison has to reproduce, or its table is an anecdote.

Slice 7.3's whole claim is that one command rebuilds the numbers in
`docs/results/`. That is only worth anything if the same command run twice gives
the same numbers, so the property is asserted here rather than assumed from the
absence of obvious randomness.

Kept small on purpose - two seeds, two buffer settings, one arrival rate. The
committed table is 1,080 runs and takes a few seconds; what this file checks is
that the machinery is deterministic, not that the figures are the ones in the
repository, which would make every honest re-measurement a failing test.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# `scripts/` is a directory of entry points rather than a package, so it is not
# importable by name. mypy checks the file as source and cannot also resolve an
# import of it without treating the directory as a package root, which would
# make every other script a top-level module - so the ignore is here, on one
# line, rather than in a configuration change that touches all of them.
sys.path.insert(0, str(REPO / "scripts"))

from compare_policies import (  # type: ignore[import-not-found]  # noqa: E402
    GateAndScore,
    Row,
    _policies,
    compare,
    summarise,
    with_roster,
    with_arrival_multiplier,
    with_uniform_buffers,
    write_csv,
    write_markdown,
)

from pdm.platform.config import load_config  # noqa: E402
from pdm.sim.scenarios import LINE_A_ONE_SHIFT  # noqa: E402

CONFIG = load_config(REPO / "config")
SEEDS = (0, 1)
BUFFERS: tuple[int | None, ...] = (None, 20)
ARRIVALS = (1.0,)


@pytest.fixture(scope="module")
def rows() -> list[Row]:
    grid: list[Row] = compare(seeds=SEEDS, buffers=BUFFERS, arrivals=ARRIVALS, config=CONFIG)
    return grid


class TestItReproduces:
    def test_the_same_grid_twice_gives_the_same_rows(self, rows: list[Row]) -> None:
        again = compare(seeds=SEEDS, buffers=BUFFERS, arrivals=ARRIVALS, config=CONFIG)
        assert rows == again

    def test_every_cell_of_the_grid_is_present(self, rows: list[Row]) -> None:
        policies = len(_policies(CONFIG))
        assert policies == 4, "3A, 3B, 3C and 3D; a fifth needs a row in this file too"
        # Plus the oracle, which is a bound rather than a policy (ADR-124).
        assert len(rows) == len(SEEDS) * len(BUFFERS) * len(ARRIVALS) * (policies + 1)
        assert len({row.policy for row in rows}) == policies + 1


class TestTheGridVariesWhatItSaysItVaries:
    def test_thicker_buffers_change_the_result(self, rows: list[Row]) -> None:
        """If they did not, the sweep would be six copies of one row and ADR-021
        would have nothing to show for itself."""
        by_buffer = {
            units: sum(row.units_lost for row in rows if row.buffer_units == units)
            for units in (None, 20)
        }

        assert by_buffer[None] != by_buffer[20]

    def test_the_arrival_multiplier_reaches_the_generator(self) -> None:
        busier = with_arrival_multiplier(LINE_A_ONE_SHIFT, 0.5)
        quieter = with_arrival_multiplier(LINE_A_ONE_SHIFT, 2.0)

        for original, faster, slower in zip(
            LINE_A_ONE_SHIFT.windows, busier.windows, quieter.windows, strict=True
        ):
            assert faster.mean_hours_between_failures < original.mean_hours_between_failures
            assert slower.mean_hours_between_failures > original.mean_hours_between_failures

    def test_the_buffer_sweep_moves_only_the_buffers(self) -> None:
        """Changing two things at once would produce a table nobody could read a
        cause out of."""
        shaped = with_uniform_buffers(CONFIG, 20)

        for station_id, station in CONFIG.stations.items():
            changed = shaped.stations[station_id]
            assert changed.buffer_units == 20
            assert changed.bottleneck_multiplier == station.bottleneck_multiplier
            assert changed.machine_ids == station.machine_ids


class TestTheGateIsMeasuredAsWellAsRun:
    def test_only_the_policies_with_a_gate_report_bands_and_held_work(
        self, rows: list[Row]
    ) -> None:
        """The baselines have no gate, so those columns are empty for them -
        which is a fact about what they are, not a gap in the measurement.

        3D has the same gate as 3C and reports the same way (ADR-054 §1). If it
        ever stopped, the gate would have been folded into its objective, which
        is the one thing that record forbids.
        """
        for row in rows:
            if row.policy.startswith(("3C", "3D")):
                assert row.light_rounds + row.normal_rounds + row.heavy_rounds > 0
            else:
                assert row.held_rounds == 0
                assert row.light_rounds == row.normal_rounds == row.heavy_rounds == 0

    def test_the_shift_reaches_both_bands(self) -> None:
        """ADR-011's claim is that behaviour changes between the bands. A
        comparison run entirely in one of them could not show it. Since ADR-124
        the shipped three-technician shift stays light, so the claim is checked
        on the one-technician grid, where it is exercised."""
        thin = compare(
            seeds=SEEDS,
            buffers=BUFFERS,
            arrivals=ARRIVALS,
            config=CONFIG,
            scenario=with_roster(LINE_A_ONE_SHIFT, 1),
        )
        gate = [row for row in thin if row.policy.startswith("3C")]

        assert any(row.light_rounds > 0 for row in gate)
        assert any(row.heavy_rounds > 0 for row in gate)

    def test_a_fresh_gate_per_run(self) -> None:
        """`GateAndScore` accumulates the rounds it decided. One instance shared
        across seeds would report the second shift's gate on top of the first's."""
        first = GateAndScore(CONFIG)
        second = GateAndScore(CONFIG)

        assert first.rounds is not second.rounds
        assert first.held == 0


class TestTheOutputIsWritable:
    def test_both_files_are_produced_and_carry_their_parameters(
        self, rows: list[Row], tmp_path: Path
    ) -> None:
        """A result nobody can reproduce is not evidence, so the seed and every
        parameter are in the file rather than in somebody's shell history."""
        write_csv(rows, tmp_path / "comparison.csv")
        write_markdown(rows, tmp_path / "comparison.md", seeds=SEEDS)

        table = (tmp_path / "comparison.md").read_text(encoding="utf-8")
        assert "seeds: 0, 1" in table
        assert "arrival multipliers" in table
        assert "as configured" in table

        rows_written = (tmp_path / "comparison.csv").read_text(encoding="utf-8").splitlines()
        assert len(rows_written) == len(rows) + 1  # a header, then one line per run

    def test_the_summary_groups_by_the_three_things_that_vary(self, rows: list[Row]) -> None:
        summaries = summarise(rows)

        assert len(summaries) == len(
            {(r.policy, r.buffer_label, r.arrival_multiplier) for r in rows}
        )
        assert all(one.runs for one in summaries)

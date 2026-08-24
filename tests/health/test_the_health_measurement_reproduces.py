"""The measurement has to reproduce, or the figure in `health.md` is an anecdote.

Same argument as `test_the_comparison_reproduces.py`: what is checked here is
that the machinery is deterministic and that its claim holds in the direction it
claims, not that the figures are the ones committed - which would make every
honest re-measurement a failing test.

Kept to a handful of seeds. The committed run is forty.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
# `scripts/` is a directory of entry points rather than a package, so it is not
# importable by name; the same one-line ignore the comparison's test carries.
sys.path.insert(0, str(REPO / "scripts"))

from measure_health import measure, rank_one  # type: ignore[import-not-found]  # noqa: E402

from fixtures.history import LINE_A_ONE_YEAR  # noqa: E402

SEEDS = 8


class TestItReproduces:
    def test_the_same_seeds_twice_give_the_same_rows(self) -> None:
        first = measure(LINE_A_ONE_YEAR, seeds=SEEDS)
        again = measure(LINE_A_ONE_YEAR, seeds=SEEDS)
        assert first == again

    def test_one_draw_ranks_every_machine_exactly_once(self) -> None:
        ranked = rank_one(LINE_A_ONE_YEAR, seed=0)
        assert [r.machine_id for r in ranked] != []
        assert sorted(str(r.machine_id) for r in ranked) == sorted(
            str(m) for m in LINE_A_ONE_YEAR.machine_ids
        )


class TestWhatItClaims:
    def test_the_degraded_machines_rank_above_the_healthy_ones_on_average(self) -> None:
        result = measure(LINE_A_ONE_YEAR, seeds=SEEDS)
        assert result.mean_rank(degraded=True) < result.mean_rank(degraded=False)

    def test_they_also_failed_more_which_is_the_reason_they_rank_there(self) -> None:
        """The ranking would be right for the wrong reason if this were not so."""
        result = measure(LINE_A_ONE_YEAR, seeds=SEEDS)
        assert result.mean_rate(degraded=True) > result.mean_rate(degraded=False)

    def test_the_top_places_go_to_the_degraded_machines_in_most_draws(self) -> None:
        """Deliberately "most" and not "all": the committed run misses one of
        forty, and a test that demanded perfection here would be asserting that
        a stochastic generator never draws an unlucky year."""
        result = measure(LINE_A_ONE_YEAR, seeds=SEEDS)
        assert result.top_slots_correct >= SEEDS - 1

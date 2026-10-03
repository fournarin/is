"""Policy differences tested at the level of the seed, with the multiplicity corrected.

Run by hand after `scripts/compare_policies.py`:

    PYTHONPATH=. uv run python scripts/seed_level_statistics.py

Why this and not `paired_statistics.py` alone (ADR-124). That script gives a
t-interval per (buffer, multiplier) cell. An examiner pointed out three things
wrong with reading significance off it:

* the six buffer settings of one multiplier run on the **same seeds**, so the
  six cells are not six independent experiments;
* two-thirds of the seed pairs were exact ties, a point mass at zero that a
  t-interval on twenty values describes badly;
* eighteen cells per pair, four pairs and two measures is a family of tests, and
  none of the per-cell intervals had a multiplicity correction.

So here the unit is the seed. For each (policy, multiplier, seed) the six buffer
settings are averaged into one number, the paired difference between two
policies is taken per seed, and two distribution-free tests are run on those
twenty differences: the exact sign test and the exact Wilcoxon signed-rank test
(zeros dropped, average ranks for ties, the null distribution enumerated rather
than approximated). The p-values of every test in one measure's family are then
adjusted with Holm's step-down method.

Standard library only (ADR-008).
"""

from __future__ import annotations

import csv
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean, median

RESULTS = Path("docs/results")
PAIRS = (
    ("3D", "3A"),
    ("3D", "3C"),
    ("3C", "3A"),
    ("3B", "3A"),
    ("0", "3A"),
    ("0", "3C"),
)
MEASURES = (("units_lost", "units lost"), ("mean_response_minutes", "mean response (min)"))
NAMES = {
    "0": "oracle (nobody waits)",
    "3A": "first-come-first-served",
    "3B": "priority matrix",
    "3C": "gate + score",
    "3D": "gate + CP-SAT",
}


def load(path: Path) -> dict[tuple[str, str, int], dict[str, list[float]]]:
    """(policy code, multiplier, seed) -> measure -> its value under each buffer."""
    table: dict[tuple[str, str, int], dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            key = (row["policy"].split()[0], row["arrival_multiplier"], int(row["seed"]))
            for name, _ in MEASURES:
                if row[name]:
                    table[key][name].append(float(row[name]))
    return table


def sign_test(differences: list[float]) -> float:
    """Exact two-sided sign test; zeros carry no direction and are dropped."""
    positive = sum(1 for one in differences if one > 0)
    negative = sum(1 for one in differences if one < 0)
    count = positive + negative
    if count == 0:
        return 1.0
    tail: float = sum(math.comb(count, k) for k in range(min(positive, negative) + 1)) / 2**count
    return min(1.0, 2.0 * tail)


def wilcoxon(differences: list[float]) -> float:
    """Exact two-sided Wilcoxon signed-rank p-value, ties by average rank.

    Ranks are doubled so an average of two ranks is still an integer, and the
    null distribution of the positive rank sum is built by dynamic programming
    over every assignment of signs - exact, with ties, at any n this grid has.
    """
    nonzero = [one for one in differences if one != 0]
    if not nonzero:
        return 1.0
    ordered = sorted(range(len(nonzero)), key=lambda index: abs(nonzero[index]))
    doubled = [0] * len(nonzero)
    position = 0
    while position < len(ordered):
        end = position
        while end + 1 < len(ordered) and abs(nonzero[ordered[end + 1]]) == abs(
            nonzero[ordered[position]]
        ):
            end += 1
        # Ranks position+1 .. end+1 share their mean; doubled it is an integer.
        shared = (position + 1) + (end + 1)
        for index in ordered[position : end + 1]:
            doubled[index] = shared
        position = end + 1
    observed = sum(rank for rank, one in zip(doubled, nonzero, strict=True) if one > 0)
    total = sum(doubled)
    ways = [0] * (total + 1)
    ways[0] = 1
    for rank in doubled:
        for value in range(total, rank - 1, -1):
            ways[value] += ways[value - rank]
    combinations = 2 ** len(doubled)
    centre = total / 2
    distance = abs(observed - centre)
    extreme = sum(count for value, count in enumerate(ways) if abs(value - centre) >= distance)
    share: float = extreme / combinations
    return min(1.0, share)


def holm(p_values: list[float]) -> list[float]:
    """Holm's step-down adjustment, returned in the input order."""
    order = sorted(range(len(p_values)), key=lambda index: p_values[index])
    adjusted = [0.0] * len(p_values)
    running = 0.0
    for step, index in enumerate(order):
        running = max(running, (len(p_values) - step) * p_values[index])
        adjusted[index] = min(1.0, running)
    return adjusted


def main() -> int:
    # An optional directory, for the roster sweeps that write their own
    # comparison.csv beside the shipped one (`compare_policies.py --technicians`).
    results = Path(sys.argv[1]) if len(sys.argv) > 1 else RESULTS
    source = results / "comparison.csv"
    if not source.exists():
        print(f"no {source}: run scripts/compare_policies.py first")
        return 1
    table = load(source)
    multipliers = sorted({key[1] for key in table}, key=float)
    seeds = sorted({key[2] for key in table})

    lines = [
        "# Policy differences at the level of the seed",
        "",
        "**Generated by `scripts/seed_level_statistics.py` from `comparison.csv`. "
        "Do not edit by hand.**",
        "",
        f"Unit of analysis: the seed ({len(seeds)} per multiplier). For each policy, "
        "multiplier and seed the six buffer settings are averaged into one value; "
        "each row below compares two policies on those paired values. `better / "
        "worse / tied` counts seeds on which the first policy was lower / higher / "
        "equal. p-values are exact two-sided sign and Wilcoxon signed-rank tests; "
        "**Holm** adjusts the Wilcoxon p-value over every row of the same measure. "
        "Policy codes: " + ", ".join(f"`{code}` {name}" for code, name in NAMES.items()) + ".",
        "",
    ]
    for measure, label in MEASURES:
        rows: list[tuple[str, str, list[float]]] = []
        for first, second in PAIRS:
            for multiplier in multipliers:
                differences = []
                for seed in seeds:
                    a = table.get((first, multiplier, seed), {}).get(measure)
                    b = table.get((second, multiplier, seed), {}).get(measure)
                    if a and b:
                        differences.append(mean(a) - mean(b))
                if differences:
                    rows.append((f"{first} - {second}", multiplier, differences))
        p_wilcoxon = [wilcoxon(one) for _, _, one in rows]
        adjusted = holm(p_wilcoxon)
        lines += [
            f"## {label}",
            "",
            "| pair | multiplier | mean difference | median | better / worse / tied "
            "| sign test p | Wilcoxon p | Holm-adjusted p |",
            "|---|---|---:|---:|---|---:|---:|---:|",
        ]
        for (pair, multiplier, differences), p_w, p_h in zip(
            rows, p_wilcoxon, adjusted, strict=True
        ):
            better = sum(1 for one in differences if one < 0)
            worse = sum(1 for one in differences if one > 0)
            tied = len(differences) - better - worse
            mark = " **\\***" if p_h < 0.05 else ""
            lines.append(
                f"| {pair} | {multiplier} | {mean(differences):+.1f} | "
                f"{median(differences):+.1f} | {better} / {worse} / {tied} | "
                f"{sign_test(differences):.3f} | {p_w:.3f} | {p_h:.3f}{mark} |"
            )
        lines.append("")
    lines += [
        "**\\*** = Holm-adjusted p below 0.05 across every row of that measure.",
        "",
        "Read with `comparison.md`, which gives the cell means, and `README.md`, "
        "which says what this simulator is not.",
        "",
    ]
    out = results / "seed-level-statistics.md"
    out.write_text("\n".join(lines))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

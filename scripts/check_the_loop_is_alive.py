"""Silence is reported, because the thing that went wrong did not report itself.

Between 26 August and 18 September 2026 this repository received no work at all.
The unattended loop had been disabled on 24 August after a run hit a spending
limit, and nothing said so. The backlog looked healthy, both open pull requests
were green, and a disabled schedule leaves no failed run to read. Twenty-three
days went missing from a fourteen-week term, and the way it was found was
somebody wondering.

Every other gate in this repository catches something that happens. This one
catches something that stops happening, which is why it cannot live where the
loop lives: a watcher inside the same schedule, on the same budget, fails
silently for the same reason and at the same moment. It runs from GitHub's own
scheduler instead.

## The part that is not obvious

An alarm on silence has to answer "silent compared to what", and the honest
answer changes during a term. Weeks 1 to 11 expect a commit every couple of
days. Week 12 is a feature freeze. Weeks 13 and 14 are for writing a report, and
an alarm that fires through them is an alarm somebody turns off - which is the
failure this exists to prevent, arriving by a different route.

So the cadence is declared in `config/cadence.yaml` with an end date, and
**standing down is a dated statement in the repository rather than a switch
nobody can see**. After that date this check passes and says why. Before it,
silence past the threshold fails.

This file decides. It reads no clock and calls nothing: the workflow hands it
the time of the last commit and the time now, which is invariant 14's habit
applied to a script, and is what lets the awkward cases be tested rather than
argued about.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
CADENCE = REPO / "config" / "cadence.yaml"


def as_utc(moment: datetime) -> datetime:
    """Both inputs in UTC, whether or not they arrived with an offset.

    `git log --format=%cI` carries one and `date -u` does not, so the first
    run of the workflow subtracted an aware timestamp from a naive one and
    raised. The workflow reads a crash as silence, so the alarm would have
    fired every morning with a traceback in the issue - and an alarm that is
    wrong daily is muted inside a week, which is the failure this whole check
    exists to prevent, arriving by a shorter route.

    A timestamp with no offset is taken as UTC rather than refused: somebody
    running this by hand should not have to know that.
    """
    return moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    message: str


def read_cadence(path: Path = CADENCE) -> tuple[int, date, str]:
    """Hours of silence tolerated, the date the expectation ends, and why."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return (
        int(loaded["quiet_hours_allowed"]),
        loaded["expected_until"],
        str(loaded["after_that"]),
    )


def judge(*, last_commit: datetime, now: datetime, cadence: tuple[int, date, str]) -> Verdict:
    allowed, expected_until, after_that = cadence
    now, last_commit = as_utc(now), as_utc(last_commit)
    quiet = (now - last_commit).total_seconds() / 3600

    if now.date() > expected_until:
        return Verdict(
            True,
            f"Past {expected_until.isoformat()}, so no cadence is expected: {after_that}\n"
            f"Last commit was {quiet:.0f} hours ago, which is not being judged.",
        )

    if quiet <= allowed:
        return Verdict(True, f"Last commit {quiet:.0f} hours ago, within {allowed}.")

    return Verdict(
        False,
        f"No commit for {quiet:.0f} hours, against {allowed} allowed until "
        f"{expected_until.isoformat()}.\n"
        f"\n"
        f"This is the check for the failure of 24 August to 18 September 2026: the\n"
        f"unattended loop was disabled after hitting a spending limit and nothing\n"
        f"reported it. Three things to look at, in this order:\n"
        f"\n"
        f"  1. Is the routine enabled? A disabled schedule leaves no failed run.\n"
        f"  2. Did a run hit a usage or spending limit? That disables it silently.\n"
        f"  3. Is the backlog empty? If so it should have opened an issue saying so.\n"
        f"\n"
        f"If the quiet is deliberate, change config/cadence.yaml and say why there\n"
        f"rather than turning this off.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--last-commit", required=True, help="ISO 8601, from the workflow")
    parser.add_argument("--now", required=True, help="ISO 8601, from the workflow")
    args = parser.parse_args(argv)

    verdict = judge(
        last_commit=datetime.fromisoformat(args.last_commit),
        now=datetime.fromisoformat(args.now),
        cadence=read_cadence(),
    )
    print(verdict.message)
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())

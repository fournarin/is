"""The scenario the tests and the comparison run on.

One morning shift on line A, arranged so that the run passes through both of the
bands ADR-011 defines: four quiet hours where the gate should be releasing
secondary work, then four busy ones where it should be holding work back. A run
that stayed in one band could not show that the gate does anything, and slice 7.3
would have nothing to compare across.

Every number here except the two arrival rates is read from configuration: the
shift is the morning shift `plant.yaml` declares, the machines are the ones
standing on line A, and each failure's duration is what `policy.yaml` prices that
severity at. **The two rates are assumptions with no measurement behind them**
and they are the reason this scenario is a starting point rather than a result.
They were chosen so that the offered load lands either side of `light_below` and
`heavy_at_or_above`, which a test asserts across several seeds - the band is a
property of the scenario, not of a lucky draw.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pdm.contracts import LineId, ShiftAssignment, ShiftId, SkillId, Technician, UserId
from pdm.sim.scenario import ArrivalWindow, SimScenario

LINE_A = LineId("line-a")
MORNING = ShiftId("morning")

# 06:00 to 14:00, the morning shift in plant.yaml. A date in March, matching the
# signal scenario in `pdm.signals`, so a demo can run both over one timeline.
_STARTS_AT = datetime(2026, 3, 3, 6, 0, tzinfo=UTC)
_SHIFT = timedelta(hours=8)

# The whole skill vocabulary, because a ticket priced from `fallback_minutes`
# carries no required skill at all (ADR-041): guessing one sends the wrong
# person. Nothing in this scenario therefore exercises skill matching, and the
# w3 term of the score is not something a run of it can say anything about.
_EVERY_SKILL = frozenset(
    SkillId(name) for name in ("robot_mechanical", "robot_controls", "electrical", "hydraulics")
)

# Three technicians. Provenance: none - the plant has not said how many are on a
# shift. It is a scenario parameter and 7.3 is expected to vary it, because the
# roster size is the other half of every load ratio in this file.
_ROSTER = tuple(
    Technician(user=UserId(f"tech-{index}"), skills=_EVERY_SKILL) for index in (1, 2, 3)
)


LINE_A_ONE_SHIFT = SimScenario(
    name="line-a-one-shift",
    line_id=LINE_A,
    starts_at=_STARTS_AT,
    duration=_SHIFT,
    # design.md 6.2: a dispatch round about every five minutes.
    round_interval=timedelta(minutes=5),
    shift_id=MORNING,
    technicians=_ROSTER,
    assignments=tuple(
        ShiftAssignment(
            shift_id=MORNING,
            on_date=_STARTS_AT.date(),
            technician=technician.user,
            available_minutes=int(_SHIFT.total_seconds() // 60),
        )
        for technician in _ROSTER
    ),
    windows=(
        # Roughly one failure per machine every six hours over four hours across
        # four machines: a handful of jobs against 720 person-minutes, which is
        # the light band. This is the stretch the advisor's "release the
        # secondary work" behaviour is about.
        ArrivalWindow(
            name="quiet",
            starts_after=timedelta(0),
            lasts=timedelta(hours=4),
            mean_hours_between_failures=6.0,
        ),
        # A failure roughly every thirty-six minutes per machine. Deliberately
        # harsh: three technicians and jobs priced at forty-five to ninety
        # minutes only reach the heavy band when work arrives faster than they
        # can absorb it, which is what the band means. It is a stress case, not
        # a claim about how often a real line stops - and the run must come out
        # of it with work unfinished, or the gate had nothing to decide.
        ArrivalWindow(
            name="busy",
            starts_after=timedelta(hours=4),
            lasts=timedelta(hours=4),
            mean_hours_between_failures=0.6,
        ),
    ),
)

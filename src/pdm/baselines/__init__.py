"""What a plant does today, written so it can be measured.

Two policies, both implementing `sim.Policy`, neither knowing that
`pdm.dispatch` exists. That last part is the point rather than tidiness: a
baseline written against the interface of the thing it is being compared to is
not a baseline, it is that thing with pieces removed, and a comparison against
it measures the pieces rather than the approach (ADR-046 §5).

`plan.md` names the two:

  **3A, first come first served** - the order the tickets arrived in. This is
  what a queue does when nobody is scheduling it.
  **3B, a priority matrix** - severity crossed with how much the line matters,
  the laminated sheet on the wall of a maintenance office.

Neither reads a clock, a database or a station's buffer. Slice 7.3 measures what
that costs.
"""

from pdm.baselines.policies import FirstComeFirstServed, PriorityMatrix

__all__ = ["FirstComeFirstServed", "PriorityMatrix"]

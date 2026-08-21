"""The two baselines, and the one thing they are allowed to share.

They differ in **ordering** and in nothing else. Both must still describe a
shift that could have happened - the crew is the size the ticket asks for,
nobody is in two places, and nobody is given minutes the shift does not have
(ADR-046 §5, ADR-047) - so the mechanics of "who could take this" are shared
between them. Sharing that is not sharing a scheduling idea; it is both of them
obeying the same physics.

Nothing here reads a clock or a connection. A policy is a function of the
`RoundState` it is handed, which is what lets slice 7.3 run the same scenario
against all three and compare the results rather than the weather.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pdm.contracts import MachineId, Severity, UserId
from pdm.sim import Placement, RoundState, Ticket


def _free(state: RoundState) -> list[tuple[UserId, int]]:
    """Who can start something now, and how many minutes they have left.

    Rostered, active, and not already under a machine. Sorted by user id so that
    two runs of the same scenario hand the same jobs to the same people - the
    engine compares event logs with `==`, and a set's iteration order reaching
    an output would make reproducibility a property of the interpreter.
    """
    left = dict(state.remaining_minutes)
    return sorted(
        (technician.user, left.get(technician.user, 0))
        for technician in state.technicians
        if technician.active and technician.user not in state.busy
    )


def _place(ordered: Sequence[Ticket], state: RoundState, *, name: str) -> tuple[Placement, ...]:
    """Take the ranked list and hand out what the shift can actually do.

    Down the list in order: the first people with enough minutes left, or nobody
    at all. `required_technicians` or none - half a two-person job cannot be
    started and would spend one person's shift achieving nothing (ADR-025).

    A ticket that cannot be crewed is skipped rather than ending the round,
    because the one behind it may be smaller. That is not a scheduling decision
    dressed up as a mechanic: both baselines would otherwise stall on a job the
    shift can never do, and the comparison would measure the stall.
    """
    free = _free(state)
    placements: list[Placement] = []

    for ticket in ordered:
        crew = ticket.order.required_technicians
        minutes = ticket.order.estimated_minutes
        fits = [user for user, left in free if left >= minutes]
        if len(fits) < crew:
            continue
        chosen = tuple(fits[:crew])
        free = [(user, left) for user, left in free if user not in chosen]
        placements.append(Placement(ref=ticket.ref, users=chosen, priority_reason=name))
    return tuple(placements)


class FirstComeFirstServed:
    """3A. The order they arrived in, and nothing else.

    No severity, no line, no load. What a queue does when nobody is scheduling
    it, and the reason a plant can be running a maintenance backlog in which the
    most expensive fault on the line is behind six routine ones.

    The failure slice 7.3 measures is exactly that: a low-severity ticket
    released ahead of a critical one that arrived a minute later.
    """

    name = "fifo"

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        ordered = sorted(state.pending, key=lambda ticket: (ticket.created_at, ticket.ref))
        return _place(ordered, state, name="oldest first")


class PriorityMatrix:
    """3B. Severity crossed with how much the line matters.

    The laminated sheet on the wall of a maintenance office: four severities
    down one side, the lines across the top, and a number in each cell. It is a
    real improvement on 3A and it is still not a scheduler, because of what it
    cannot see - a station's buffer.

    **Two identical faults are not equally urgent** (ADR-021): thirty minutes at
    a station with twenty units queued ahead of it costs the line nothing, and
    thirty minutes at the unbuffered bottleneck stops it. A matrix has no cell
    for that, so it ranks the two the same, and slice 7.3 is where the cost of
    that shows up.

    `importance_of` is supplied rather than read from configuration: the table
    is the plant's own document, not a fact about the plant, and putting a
    number for it in `plant.yaml` would make it look measured. The default -
    every machine equally important - is the honest reading of a plant that has
    one line.
    """

    name = "matrix"

    def __init__(self, importance_of: Callable[[MachineId], float] | None = None) -> None:
        self._importance_of = importance_of or (lambda _: 1.0)

    def cell(self, ticket: Ticket) -> float:
        """One cell of the matrix. Severity's rank against the line's weight."""
        return ticket.order.severity.rank * self._importance_of(ticket.order.machine_id)

    def choose(self, state: RoundState) -> tuple[Placement, ...]:
        # Highest cell first; arrival, then reference, break the ties - and ties
        # are the normal case here, not an edge one. Four severities and one
        # line give four distinct values for a whole shift's work, which is
        # precisely how coarse the instrument is.
        ordered = sorted(
            state.pending,
            key=lambda ticket: (-self.cell(ticket), ticket.created_at, ticket.ref),
        )
        return _place(ordered, state, name="severity against line importance")


def severity_ranks() -> dict[Severity, int]:
    """The matrix's rows, for a test or a report to print.

    Taken from `Severity.rank` rather than restated, so the baseline and the
    system it is compared against cannot disagree about what "high" means.
    """
    return {severity: severity.rank for severity in Severity}

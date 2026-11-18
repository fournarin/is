"""What machines exist, for the screens that have to name one.

One route, and it reads `plant.yaml` rather than the database: the floor is
configuration (ADR-021), and a screen that let somebody type a machine number
into a box would collect typos on a phone at a machine and answer them with a
422.

Every role may read it. It is the list painted on the machines themselves, and
the report screen is useless without it (ADR-077 section 1).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from pdm.api.deps import Plant, requires
from pdm.contracts import Role
from pdm.platform.auth.domain import Account

router = APIRouter(tags=["plant"])

_MAY_READ = (Role.TECHNICIAN, Role.ENGINEER, Role.SUPERVISOR, Role.OPERATOR)


class MachineOnTheFloor(BaseModel):
    """A machine, and enough of where it stands to be recognised.

    The station and the line are here because "MC-012" means nothing to somebody
    who has been on the line for a week, and "st-03 on line-a" means where they
    are standing.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    machine_id: str
    model: str
    station_id: str
    line_id: str
    seq: int
    # The name the floor uses for the station (REQ-P-03), when plant.yaml gives one.
    station_name: str | None = None


@router.get("/machines", response_model=list[MachineOnTheFloor])
def machines(
    plant: Plant,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_machines"))],
) -> list[MachineOnTheFloor]:
    """Every machine on the floor, in line order.

    Line order rather than alphabetical, because that is the order somebody walks
    past them, and a list in that order is one they can check themselves against.
    """
    return sorted(
        (
            MachineOnTheFloor(
                machine_id=str(machine_id),
                model=str(plant.model_of(machine_id)),
                station_id=str(station.station_id),
                line_id=str(station.line_id),
                seq=station.seq,
                station_name=station.name,
            )
            for station in plant.stations.values()
            for machine_id in station.machine_ids
        ),
        key=lambda machine: (machine.line_id, machine.seq, machine.machine_id),
    )

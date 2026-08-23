"""Which destination a name means, and the one place that knows (ADR-069).

`policy.yaml` names a destination; this turns the name into a sink. Two rules
hold it together:

  * **The names live here.** `SinkPolicy.destination` in the config schema
    repeats them as a `Literal` so that `python -m pdm.platform.config config`
    rejects an unknown one before anything starts, and a test asserts the two
    lists agree. The schema cannot import this module - `pdm.platform` is
    underneath everything and importing a layer above it would invert the
    package layout (ADR-030) - so the duplication is deliberate and guarded.

  * **An unknown name is a failure with the name in it.** Never a quiet fall
    back to `own-system`: a plant that configured `cmms` and got our own system
    would look like it was working, and the tickets nobody was reading would be
    the first anybody heard of it.
"""

from __future__ import annotations

from pathlib import Path

from pdm.platform.clock import Clock
from pdm.sinks.cmms import SCHEMES, CmmsSink, is_a_network_address
from pdm.sinks.domain import TicketSink
from pdm.sinks.file import FileSink
from pdm.sinks.own_system import OwnSystemSink

# The destinations this build can reach. `SinkPolicy.destination` repeats them.
#
# `cmms` being here is not a claim that the plant's system is reachable. It is
# an adapter written against a contract of our own (ADR-070 §2, ADR-074), and
# `policy.yaml` keeps `own-system` until somebody with access says otherwise.
NAMES = ("own-system", "file", "cmms")


class UnknownDestination(Exception):
    """Raised at startup, before a round has run. See the module docstring."""


class TicketDirectoryNotSet(Exception):
    """`file` was configured and nothing said where.

    A path is a deployment fact rather than a plant policy, so it comes from the
    environment and has no default - the argument ADR-019 makes for
    `STORAGE_DIR`. A guessed directory is a stack that starts healthy and writes
    tickets somewhere nobody will look (ADR-069).
    """


class CmmsEndpointNotSet(Exception):
    """`cmms` was configured and the environment does not say where, or with what.

    The same argument as `TicketDirectoryNotSet`, one destination further out
    (ADR-069 §1, ADR-074 §5): an endpoint and a credential are deployment facts
    with no sensible default, and a sink pointed at a guessed host looks healthy
    while writing nowhere. The scheme is checked here too, because `urllib`
    would open a `file://` base URL as readily as an address.
    """


def build(
    name: str,
    *,
    clock: Clock,
    ticket_dir: Path | None = None,
    cmms_base_url: str | None = None,
    cmms_token: str | None = None,
) -> TicketSink:
    """The destination `policy.yaml` asked for, or a failure that says why."""
    if name == "own-system":
        return OwnSystemSink()
    if name == "file":
        if ticket_dir is None:
            raise TicketDirectoryNotSet(
                "destination 'file' needs TICKET_DIR, and it has no default - "
                "see the worker services in docker-compose.yml"
            )
        return FileSink(ticket_dir, clock)
    if name == "cmms":
        return _cmms(cmms_base_url, cmms_token)
    raise UnknownDestination(
        f"policy.yaml asks for destination {name!r}, which this build does not have. "
        f"Known destinations: {', '.join(NAMES)}"
    )


def _cmms(base_url: str | None, token: str | None) -> CmmsSink:
    """Three refusals, all of them before the first round rather than during it."""
    if not base_url:
        raise CmmsEndpointNotSet(
            "destination 'cmms' needs CMMS_BASE_URL, and it has no default - "
            "see the worker services in docker-compose.yml"
        )
    if not token:
        raise CmmsEndpointNotSet(
            "destination 'cmms' needs CMMS_TOKEN, and it has no default: a bearer "
            "token is what the contract in ADR-074 authenticates with"
        )
    if not is_a_network_address(base_url):
        raise CmmsEndpointNotSet(
            f"CMMS_BASE_URL is {base_url!r}, which is not a network address. "
            f"Accepted schemes: {', '.join(SCHEMES)} - a sink built on anything "
            f"else would report every delivery as successful while writing to a "
            f"local path (ADR-074 section 5)"
        )
    return CmmsSink(base_url, token=token)

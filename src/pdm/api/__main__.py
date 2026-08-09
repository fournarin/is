"""Entrypoint for the `api` container (ADR-026).

One image, three roles, chosen by the command in docker-compose.yml. This is the
role that serves HTTP; the other two claim jobs from the queue.

Nothing is configured here beyond the port. Where the database and the documents
are comes from the environment, and both fail loudly at boot rather than
defaulting - a service that starts against the wrong directory looks healthy
while writing manuals somewhere nobody backs up (ADR-019, ADR-031).
"""

from __future__ import annotations

import os

import uvicorn

from pdm.api.app import create_app


def main() -> None:
    uvicorn.run(
        create_app(),
        # Every interface, because inside the compose network that is the only
        # way the port mapping reaches it. The service is not exposed beyond the
        # plant's own network (ADR-029).
        host="0.0.0.0",
        port=int(os.environ.get("API_PORT", "8000")),
        # No access log from uvicorn: ADR-019's access log is in the database,
        # carries who and what, and is the one somebody reads after an incident.
        # A second one in stdout with neither would invite reading the wrong one.
        access_log=False,
    )


if __name__ == "__main__":
    main()

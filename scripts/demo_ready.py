"""Is this stack ready to be shown to somebody, and if not, which link is missing.

    DATABASE_URL=... uv run python scripts/demo_ready.py

`scripts/rehearse.py` proves the screens answer. That is not the same claim as
"there is something on them": every check seeds its own world and truncates it
again, so a rehearsal can pass in full and leave a stack whose supervisor screen
is empty because no round has run yet.

This is the other claim. It walks the chain the demo walks - signals become
Findings, Findings become tickets, a round proposes them, a person confirms -
and names the first link that is missing rather than reporting a total. "No
proposals" has five different causes and they are fixed five different ways.

Exit 0 when there is something for the shift lead to confirm - or, where
`confirmation: automatic` is configured, something assigned. Exit 1 with the
missing link named.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from psycopg import connect
from psycopg.rows import dict_row

from pdm.contracts import shift_at
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1

    config = load_config(Path(os.environ.get("CONFIG_DIR", "config")))
    now = SystemClock().now()
    window = shift_at(config.shifts.values(), now, config.timezone)
    confirmation = config.policy.dispatch.confirmation

    with connect(url, row_factory=dict_row) as conn:
        counts = conn.execute("""
            SELECT
              (SELECT count(*) FROM account)                                    AS accounts,
              (SELECT count(*) FROM document)                                   AS manuals,
              (SELECT count(*) FROM playbook WHERE status = 'approved')         AS playbooks,
              (SELECT count(*) FROM technician WHERE active)                    AS technicians,
              (SELECT count(*) FROM finding
                WHERE status IN ('open', 'acknowledged'))                       AS findings,
              (SELECT count(*) FROM work_order WHERE status = 'queued')         AS queued,
              (SELECT count(*) FROM work_order WHERE status = 'assigned')       AS assigned
        """).fetchone()
        assert counts is not None

        rostered = 0
        if window is not None:
            row = conn.execute(
                "SELECT count(*) AS n FROM shift_assignment WHERE shift_id = %s AND on_date = %s",
                (str(window.shift_id), window.on_date),
            ).fetchone()
            rostered = int(row["n"]) if row else 0

        proposed = 0
        if confirmation == "supervisor":
            row = conn.execute(
                # `state`, and `pending` - the column and the value the
                # confirmation gate actually uses (migration 0012).
                "SELECT count(*) AS n FROM dispatch_proposal WHERE state = 'pending'"
            ).fetchone()
            proposed = int(row["n"]) if row else 0

    where = f"{window.shift_id} on {window.on_date}" if window else "no shift is running now"
    print(
        f"accounts {counts['accounts']} · manuals {counts['manuals']} · "
        f"approved playbooks {counts['playbooks']} · technicians {counts['technicians']} "
        f"({rostered} on {where})"
    )
    print(
        f"open findings {counts['findings']} · queued {counts['queued']} · "
        f"assigned {counts['assigned']} · awaiting confirmation {proposed}"
    )

    # The chain, in the order it runs. The first broken link is the only useful
    # thing to say: everything downstream of it is empty for the same reason.
    if counts["accounts"] == 0:
        return _missing("no accounts", "uv run python scripts/seed_demo.py")
    if counts["technicians"] == 0 or rostered == 0:
        return _missing(
            "nobody is rostered on the shift that is running now",
            "uv run python scripts/seed_demo_roster.py  (ADR-078)",
        )
    if counts["findings"] == 0 and counts["queued"] == 0 and counts["assigned"] == 0:
        return _missing(
            "no signals have become Findings",
            "check SIGNAL_SOURCE on worker-runtime, and that it is running",
        )
    if counts["queued"] == 0 and counts["assigned"] == 0 and proposed == 0:
        return _missing(
            "Findings exist but no ticket was written",
            "read worker-runtime's log: a Finding that cannot be priced is skipped",
        )
    if confirmation == "supervisor" and proposed == 0 and counts["assigned"] == 0:
        return _missing(
            "tickets are queued but no round has proposed one yet",
            f"a round runs every {config.policy.dispatch.round_seconds}s; "
            "worker-runtime has to be up",
        )

    if proposed:
        print(f"\nready: {proposed} proposal(s) waiting for the shift lead to confirm")
    else:
        print(f"\nready: {counts['assigned']} ticket(s) assigned")
    if counts["playbooks"] == 0:
        # Not a broken link - a ticket with no playbook is a ticket, priced from
        # `fallback_minutes` and saying so (ADR-041). It is worth naming because
        # the technician's screen will have no steps on it, which looks like a
        # defect to somebody seeing this for the first time.
        print("note: no approved playbook, so tickets carry no steps and a fallback estimate")
    return 0


def _missing(what: str, fix: str) -> int:
    print(f"\nnot ready: {what}")
    print(f"  {fix}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

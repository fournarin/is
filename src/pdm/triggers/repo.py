"""SQL for the finding table. No business logic, no connections opened here.

Every function takes a connection first (ADR-031), so raising a Finding and the
work order it produces commit together (ADR-017) - the pairing that stops a
Finding existing with no ticket behind it.

Two queries here are the lifecycle rather than storage, and both are written to
be right when two workers run them at the same moment:

  * `repeat` is a single UPDATE, never read-then-write, so `occurrence_count`
    counts firings rather than workers (ADR-042 section 4);
  * `raise_finding` relies on the partial unique index from migration 0007
    rather than on having checked first.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingRef,
    FindingStatus,
    MachineId,
    RuleId,
)

_COLUMNS = """
    machine_id, component, symptom_code, severity, rule_id, detected_at,
    evidence, kind, eta, eta_confidence, status, occurrence_count,
    last_seen_at, superseded_by
"""

LIVE = ("open", "acknowledged")


class AlreadyLive(Exception):
    """An open or acknowledged Finding already exists for this (machine, rule).

    Raised rather than swallowed: the caller asked to raise one and did not, and
    a repeat is a different operation with a different meaning (ADR-023).
    """


def _to_finding(row: dict[str, Any]) -> Finding:
    row.pop("finding_ref", None)
    row.pop("resolved_at", None)
    return Finding.model_validate(row)


def raise_finding(conn: Connection[Any], finding: Finding) -> FindingRef:
    """Write a new Finding, or say that one is already live.

    The uniqueness is the database's (migration 0007), not a check performed
    first: between a check and an insert there is room for the second worker,
    and this is the table where a duplicate becomes a duplicate work order.
    """
    # A savepoint, so a duplicate does not poison the caller's transaction. The
    # batch that hits this is raising other Findings and writing work orders in
    # the same transaction (ADR-017); without the savepoint, one collision would
    # abort all of it, and the collision is the case where the system is working
    # exactly as ADR-023 intends.
    with conn.transaction(), conn.cursor(row_factory=dict_row) as cur:
        try:
            cur.execute(
                f"""
                INSERT INTO finding ({_COLUMNS})
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING finding_ref
                """,
                (
                    finding.machine_id,
                    finding.component,
                    finding.symptom_code,
                    finding.severity.value,
                    finding.rule_id,
                    finding.detected_at,
                    Jsonb(finding.evidence),
                    finding.kind.value,
                    finding.eta,
                    finding.eta_confidence,
                    finding.status.value,
                    finding.occurrence_count,
                    finding.last_seen_at,
                    finding.superseded_by,
                ),
            )
        except UniqueViolation as error:
            raise AlreadyLive(
                f"{finding.machine_id}/{finding.rule_id} already has a live Finding; "
                "a repeat updates it rather than adding another (ADR-023)"
            ) from error
        row = cur.fetchone()
    assert row is not None
    return FindingRef(str(row["finding_ref"]))


def repeat(conn: Connection[Any], *, machine_id: MachineId, rule_id: RuleId, now: datetime) -> bool:
    """The same condition again: one more occurrence, seen just now.

    One statement. Read-then-write would let two evaluations racing on one
    machine each read the same count and write it back, and the number that tells
    an engineer a threshold is too sensitive would be counting workers.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE finding
               SET occurrence_count = occurrence_count + 1, last_seen_at = %s
             WHERE machine_id = %s AND rule_id = %s
               AND status IN ('open', 'acknowledged')
            """,
            (now, machine_id, rule_id),
        )
        return cur.rowcount == 1


def live(conn: Connection[Any]) -> dict[tuple[MachineId, RuleId], Finding]:
    """Every open or acknowledged Finding, keyed for suppression.

    Loaded once per batch by the loop rather than once per signal: a plant's
    worth of channels at a sample a minute would otherwise be a query a second
    to answer a question whose answer changes a few times an hour.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM finding WHERE status IN ('open', 'acknowledged')")
        rows = cur.fetchall()
    return {(row["machine_id"], row["rule_id"]): _to_finding(dict(row)) for row in rows}


def refs_of_live(conn: Connection[Any]) -> dict[tuple[MachineId, RuleId], FindingRef]:
    """The same set, as references. What the caller needs to act on one."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT machine_id, rule_id, finding_ref FROM finding "
            "WHERE status IN ('open', 'acknowledged')"
        )
        return {(row[0], row[1]): FindingRef(row[2]) for row in cur.fetchall()}


def last_resolved(conn: Connection[Any]) -> dict[tuple[MachineId, RuleId], datetime]:
    """When each pair was most recently resolved, for the cooldown."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT machine_id, rule_id, max(resolved_at)
              FROM finding
             WHERE status = 'resolved' AND resolved_at IS NOT NULL
             GROUP BY machine_id, rule_id
            """
        )
        return {(row[0], row[1]): row[2] for row in cur.fetchall()}


def get(conn: Connection[Any], finding_ref: FindingRef) -> Finding | None:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(f"SELECT {_COLUMNS} FROM finding WHERE finding_ref = %s", (finding_ref,))
        row = cur.fetchone()
    return _to_finding(row) if row else None


def acknowledge(conn: Connection[Any], finding_ref: FindingRef) -> bool:
    """Somebody has seen it. It stays live, and stays suppressing."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE finding SET status = 'acknowledged' WHERE finding_ref = %s AND status = 'open'",
            (finding_ref,),
        )
        return cur.rowcount == 1


def resolve(conn: Connection[Any], finding_ref: FindingRef, *, now: datetime) -> bool:
    """The condition is over. The cooldown starts from this moment."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE finding SET status = 'resolved', resolved_at = %s "
            "WHERE finding_ref = %s AND status IN ('open', 'acknowledged')",
            (now, finding_ref),
        )
        return cur.rowcount == 1


def open_prediction_for(
    conn: Connection[Any], *, machine_id: MachineId, component: ComponentLabel
) -> FindingRef | None:
    """A live prediction about this part, if there is one (ADR-023 section 7)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT finding_ref FROM finding
             WHERE machine_id = %s AND component = %s
               AND kind = 'predicted' AND status IN ('open', 'acknowledged')
             ORDER BY detected_at
             LIMIT 1
            """,
            (machine_id, component),
        )
        row = cur.fetchone()
    return FindingRef(str(row[0])) if row else None


def supersede(conn: Connection[Any], *, predicted: FindingRef, by: FindingRef) -> bool:
    """The thing predicted has happened.

    Two work orders for one fault is the immediate reason (ADR-023 section 7),
    and the other is that this row is now a measurement: the moment a prediction
    is superseded is the moment its error becomes known, which is the whole of
    ADR-020's accuracy loop.
    """
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE finding SET status = 'superseded', superseded_by = %s "
            "WHERE finding_ref = %s AND status IN ('open', 'acknowledged')",
            (by, predicted),
        )
        return cur.rowcount == 1


def expire_overdue_predictions(
    conn: Connection[Any], *, now: datetime, grace: timedelta
) -> list[FindingRef]:
    """Predictions whose ETA plus grace has passed with nothing happening.

    Expired rather than deleted: a prediction that did not come true is the
    other half of the accuracy measurement, and a table holding only the
    successful ones would report a system that never gets it wrong (ADR-020).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE finding SET status = 'expired'
             WHERE kind = 'predicted' AND status IN ('open', 'acknowledged')
               AND eta IS NOT NULL AND eta + %s < %s
            RETURNING finding_ref
            """,
            (grace, now),
        )
        return [FindingRef(str(row[0])) for row in cur.fetchall()]


def status_of(conn: Connection[Any], finding_ref: FindingRef) -> FindingStatus | None:
    with conn.cursor() as cur:
        cur.execute("SELECT status FROM finding WHERE finding_ref = %s", (finding_ref,))
        row = cur.fetchone()
    return FindingStatus(row[0]) if row else None

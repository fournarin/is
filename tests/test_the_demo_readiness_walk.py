"""What `scripts/demo_ready.py` says, and in what order it says it.

The script exists to answer one question a person asks with somebody waiting in
the room - *is there anything on these screens?* - and its value is entirely in
naming the **first** broken link rather than the last. "No proposals" has five
causes; four of them are upstream, and reporting the wrong one sends somebody to
restart the wrong container.

Its own SQL is the other reason for this file. The first version of the query
against `dispatch_proposal` named a column that does not exist, which mypy
cannot see and a reader did not: it would have failed at the end of a
twenty-minute rehearsal and reported a stack that never placed work.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from psycopg import Connection, connect

from pdm.contracts import (
    Assignee,
    AssigneeRole,
    ComponentLabel,
    Finding,
    MachineId,
    Role,
    RuleId,
    Severity,
    ShiftAssignment,
    SkillId,
    SymptomCode,
    Technician,
    UserId,
    shift_at,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.dispatch.domain import Band
from pdm.dispatch.proposals import Proposal
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.triggers import repo as findings_repo
from pdm.work import WorkOrders
from scripts import demo_ready, seed_demo_roster

pytestmark = pytest.mark.db

CONFIG = load_config(Path("config"))
FALLBACK = {str(model): dict(rows) for model, rows in CONFIG.policy.fallback_minutes.items()}
MACHINE = MachineId("MC-001")
DEMO_ACCOUNTS = [
    (UserId("tech-1"), Role.TECHNICIAN),
    (UserId("eng-1"), Role.ENGINEER),
    (UserId("sup-1"), Role.SUPERVISOR),
    (UserId("op-1"), Role.OPERATOR),
]


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def conn(database_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[Connection[Any]]:
    monkeypatch.setenv("DATABASE_URL", database_url)
    connection = connect(database_url, autocommit=True)
    try:
        connection.execute(
            "TRUNCATE dispatch_proposal, work_order, finding, shift_assignment, technician, "
            "playbook, document_page, document, access_log, session, account CASCADE"
        )
        yield connection
    finally:
        connection.close()


def _accounts(conn: Connection[Any]) -> None:
    auth = Authentication(LocalAccounts(), SystemClock())
    for user, role in DEMO_ACCOUNTS:
        auth.create_account(
            conn, user=user, display_name=str(user), role=role, password="demo-password"
        )


def _roster(conn: Connection[Any]) -> None:
    now = SystemClock().now()
    window = shift_at(CONFIG.shifts.values(), now, CONFIG.timezone)
    assert window is not None
    for index in (1, 2, 3):
        user = UserId(f"tech-{index}")
        dispatch_repo.add_technician(
            conn,
            Technician(user=user, skills=frozenset(SkillId(str(s)) for s in CONFIG.skills)),
            now=now,
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=window.shift_id,
                on_date=window.on_date,
                technician=user,
                available_minutes=seed_demo_roster.AVAILABLE_MINUTES,
            ),
        )


def _propose(conn: Connection[Any], work_order_ref: str) -> None:
    """One pending proposal, which is what "ready" means under the shipped
    `confirmation: supervisor` (ADR-071)."""
    now = SystemClock().now()
    window = shift_at(CONFIG.shifts.values(), now, CONFIG.timezone)
    assert window is not None
    dispatch_repo.propose(
        conn,
        Proposal(
            work_order_ref=work_order_ref,
            proposed_at=now,
            assignees=(Assignee(user=UserId("tech-1"), role=AssigneeRole.PRIMARY),),
            priority_score=1.0,
            priority_reason="because this is a test",
            band=Band.NORMAL,
            load_ratio=0.1,
            shift_id=window.shift_id,
            on_date=window.on_date,
        ),
    )


def _a_finding(conn: Connection[Any]) -> Finding:
    finding = Finding(
        machine_id=MACHINE,
        component=ComponentLabel("belt_motor"),
        symptom_code=SymptomCode("SYM-014"),
        severity=Severity.HIGH,
        rule_id=RuleId("R-motor-temp-high"),
        detected_at=SystemClock().now(),
        evidence={"value": 91.0, "threshold": 85.0},
    )
    findings_repo.raise_finding(conn, finding)
    return finding


class TestItNamesTheFirstBrokenLink:
    def test_an_empty_database_is_missing_its_accounts(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert demo_ready.main() == 1
        assert "no accounts" in capsys.readouterr().out

    def test_accounts_without_a_roster_name_the_roster(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Not "no proposals", which is true and useless: nothing downstream of
        an empty roster can be anything else."""
        _accounts(conn)

        assert demo_ready.main() == 1
        out = capsys.readouterr().out
        assert "nobody is rostered" in out
        assert "seed_demo_roster" in out

    def test_a_roster_with_no_findings_names_the_signal_source(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _accounts(conn)
        _roster(conn)

        assert demo_ready.main() == 1
        assert "no signals have become Findings" in capsys.readouterr().out

    def test_findings_with_no_ticket_name_the_worker_that_should_have_written_one(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _accounts(conn)
        _roster(conn)
        _a_finding(conn)

        assert demo_ready.main() == 1
        assert "no ticket was written" in capsys.readouterr().out

    def test_a_queued_ticket_with_no_round_yet_says_so_and_says_how_long_a_round_is(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _accounts(conn)
        _roster(conn)
        orders = WorkOrders(SystemClock(), fallback_minutes=FALLBACK)
        orders.from_report(
            conn,
            machine_id=MACHINE,
            machine_model="R-2000iC",
            severity=Severity.MEDIUM,
            reported_by=UserId("op-1"),
            description="oil under the base plate",
        )

        assert demo_ready.main() == 1
        out = capsys.readouterr().out
        assert "no round has proposed one yet" in out
        assert str(CONFIG.policy.dispatch.round_seconds) in out


class TestItSaysReadyWhenSomebodyCanBeShownSomething:
    def test_a_pending_proposal_is_what_ready_means_under_the_confirmation_gate(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        _accounts(conn)
        _roster(conn)
        orders = WorkOrders(SystemClock(), fallback_minutes=FALLBACK)
        issued = orders.from_report(
            conn,
            machine_id=MACHINE,
            machine_model="R-2000iC",
            severity=Severity.MEDIUM,
            reported_by=UserId("op-1"),
            description="oil under the base plate",
        )
        _propose(conn, issued.ref)

        assert demo_ready.main() == 0
        assert "ready: 1 proposal" in capsys.readouterr().out

    def test_it_names_the_absent_playbook_without_calling_the_stack_broken(
        self, conn: Connection[Any], capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A ticket with no playbook is a ticket (ADR-041). It is worth saying,
        because a screen with no steps on it looks like a defect to somebody
        seeing this system for the first time - and it is not one."""
        _accounts(conn)
        _roster(conn)
        orders = WorkOrders(SystemClock(), fallback_minutes=FALLBACK)
        issued = orders.from_report(
            conn,
            machine_id=MACHINE,
            machine_model="R-2000iC",
            severity=Severity.MEDIUM,
            reported_by=UserId("op-1"),
            description="oil under the base plate",
        )
        _propose(conn, issued.ref)

        demo_ready.main()
        assert "no approved playbook" in capsys.readouterr().out


class TestTheQueriesAreTheOnesTheSchemaHas:
    def test_every_count_it_reads_answers_rather_than_raising(self, conn: Connection[Any]) -> None:
        """The regression this file was written for: `dispatch_proposal` has
        `state`, not `status`, and the wrong name would only ever be discovered
        at the end of a rehearsal."""
        _accounts(conn)
        _roster(conn)
        assert demo_ready.main() in (0, 1)

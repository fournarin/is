"""The three lists an engineer otherwise answers from memory (slice 9.3).

The specification is `CLAUDE.md` and ADR-038, not the handler: a symptom with
nothing approved to serve is a gap **however often it has been drafted**, because
a draft is never served and from a technician's side that is the same as having
nothing (ADR-038 section 2). A `needs_review` playbook is not a gap for the
opposite reason - it *is* served, with a warning (ADR-018) - and belongs on the
third list, which is why the two are asserted against each other here.

The ranking is tested twice: once as a pure function, where the order can be
stated exactly, and once over HTTP against a real database, where what is being
checked is that the SQL counts what the pure function was given.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.api.overview import group_by_model, rank_gaps
from pdm.contracts import (
    ComponentLabel,
    DocumentId,
    Finding,
    FindingStatus,
    MachineId,
    MachineModel,
    Playbook,
    PlaybookStatus,
    PlaybookStep,
    Role,
    RuleId,
    Severity,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore
from pdm.playbooks import ProposalOrigin
from pdm.playbooks import repo as playbooks
from pdm.playbooks.domain import PendingForPair
from pdm.triggers import repo as triggers
from pdm.triggers.domain import SymptomSeen

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)

R2000IC = MachineModel("R-2000iC")
M710IC = MachineModel("M-710iC")

# Machines from config/plant.yaml, which is what the application loads. Chosen
# rather than invented so that the model each one resolves to is the plant's
# answer and not the test's.
MC_004 = MachineId("MC-004")  # R-2000iC
MC_012 = MachineId("MC-012")  # R-2000iC
MC_018 = MachineId("MC-018")  # M-710iC

FREQUENT = SymptomCode("SYM-031")
OCCASIONAL = SymptomCode("SYM-047")
ANSWERED = SymptomCode("SYM-014")
DRAFTED_ONLY = SymptomCode("SYM-052")
FLAGGED = SymptomCode("SYM-060")

PASSWORD = "correct horse battery staple"
PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
}


def seen(
    symptom_code: SymptomCode,
    machine_id: MachineId,
    *,
    findings: int = 1,
    occurrences: int = 1,
    first: datetime = START,
    last: datetime = START,
) -> SymptomSeen:
    return SymptomSeen(
        symptom_code=symptom_code,
        machine_id=machine_id,
        findings=findings,
        occurrences=occurrences,
        first_seen=first,
        last_seen=last,
    )


def model_of(machine_id: MachineId) -> MachineModel:
    """The plant, as the pure tests need it: two machines and one that left."""
    models = {MC_004: R2000IC, MC_012: R2000IC, MC_018: M710IC}
    return models[machine_id]


class TestWhatIsRankedAndWhy:
    """The ordering is the whole content of the first list (design.md 4)."""

    def test_the_symptom_seen_more_often_comes_first(self) -> None:
        ranked, _ = rank_gaps(
            [seen(OCCASIONAL, MC_012, findings=2), seen(FREQUENT, MC_012, findings=7)],
            model_of=model_of,
            served=set(),
            pending=[],
        )

        assert [row.symptom_code for row in ranked] == [FREQUENT, OCCASIONAL]

    def test_a_symptom_with_an_approved_playbook_is_not_a_gap(self) -> None:
        ranked, _ = rank_gaps(
            [seen(ANSWERED, MC_012, findings=9), seen(OCCASIONAL, MC_012)],
            model_of=model_of,
            served={(ANSWERED, R2000IC)},
            pending=[],
        )

        assert [row.symptom_code for row in ranked] == [OCCASIONAL]

    def test_but_only_for_the_model_that_has_one(self) -> None:
        """A playbook answers one (symptom, model) pair and no other (ADR-018).

        The same symptom on a machine of another model is a different gap, and
        folding it away would report a store that covers work it does not.
        """
        ranked, _ = rank_gaps(
            [seen(ANSWERED, MC_012), seen(ANSWERED, MC_018)],
            model_of=model_of,
            served={(ANSWERED, R2000IC)},
            pending=[],
        )

        assert [(row.symptom_code, row.machine_model) for row in ranked] == [(ANSWERED, M710IC)]

    def test_one_symptom_on_two_machines_of_a_model_is_one_gap(self) -> None:
        ranked, _ = rank_gaps(
            [
                seen(FREQUENT, MC_004, findings=2, occurrences=5, first=START, last=START),
                seen(
                    FREQUENT,
                    MC_012,
                    findings=3,
                    occurrences=40,
                    first=START + timedelta(hours=1),
                    last=START + timedelta(hours=9),
                ),
            ],
            model_of=model_of,
            served=set(),
            pending=[],
        )

        assert len(ranked) == 1
        assert ranked[0].findings == 5
        assert ranked[0].occurrences == 45
        assert ranked[0].machines == (MC_004, MC_012)
        assert ranked[0].first_seen == START
        assert ranked[0].last_seen == START + timedelta(hours=9)

    def test_firings_do_not_outrank_events(self) -> None:
        """ADR-023's whole argument, in the place it would be undone.

        One channel stuck over its threshold all morning is a single event with
        a large `occurrence_count`. Ranked on the firings it buries a symptom
        that arrived on three separate machines, and the engineer writes the
        wrong playbook next.
        """
        ranked, _ = rank_gaps(
            [
                seen(OCCASIONAL, MC_012, findings=1, occurrences=400),
                seen(FREQUENT, MC_004, findings=3, occurrences=3),
            ],
            model_of=model_of,
            served=set(),
            pending=[],
        )

        assert [row.symptom_code for row in ranked] == [FREQUENT, OCCASIONAL]

    def test_a_pending_draft_is_reported_and_the_symptom_still_a_gap(self) -> None:
        """A draft is not an answer, and pretending otherwise hides the symptom
        from the only list that would have got it written (ADR-038)."""
        ranked, _ = rank_gaps(
            [seen(DRAFTED_ONLY, MC_012)],
            model_of=model_of,
            served=set(),
            pending=[
                PendingForPair(
                    symptom_code=DRAFTED_ONLY,
                    machine_model=R2000IC,
                    waiting=2,
                    oldest=START,
                )
            ],
        )

        assert [row.symptom_code for row in ranked] == [DRAFTED_ONLY]
        assert ranked[0].proposals_waiting == 2

    def test_a_not_found_result_is_counted_apart_from_drafts(self) -> None:
        """Fourth trial: a "not found" counted among drafts waiting read as
        something to approve. It is carried separately, on the gap and on the
        model's queue, so the screen can say which it is."""
        pending = [
            PendingForPair(
                symptom_code=DRAFTED_ONLY,
                machine_model=R2000IC,
                waiting=3,
                oldest=START,
                not_found=1,
            )
        ]
        ranked, _ = rank_gaps(
            [seen(DRAFTED_ONLY, MC_012)], model_of=model_of, served=set(), pending=pending
        )

        assert ranked[0].proposals_waiting == 3
        assert ranked[0].proposals_not_found == 1
        (queue,) = group_by_model(pending)
        assert (queue.waiting, queue.not_found) == (3, 1)

    def test_a_machine_that_left_the_layout_is_named_not_dropped(self) -> None:
        """ADR-048 section 3: an unknown machine is counted and reported.

        Its symptoms cannot be filed under a machine model, so they cannot be
        drafted for - and a list that silently discarded them would say the
        store covers work nobody can even ask for.
        """
        ranked, unplaced = rank_gaps(
            [seen(FREQUENT, MachineId("MC-999"), findings=4), seen(OCCASIONAL, MC_012)],
            model_of=model_of,
            served=set(),
            pending=[],
        )

        assert [row.symptom_code for row in ranked] == [OCCASIONAL]
        assert unplaced == [MachineId("MC-999")]


class TestTheQueueIsGroupedTheWayItIsWorked:
    def test_proposals_are_summed_per_model_oldest_queue_first(self) -> None:
        groups = group_by_model(
            [
                PendingForPair(
                    symptom_code=FREQUENT,
                    machine_model=R2000IC,
                    waiting=2,
                    oldest=START + timedelta(days=1),
                ),
                PendingForPair(
                    symptom_code=OCCASIONAL, machine_model=R2000IC, waiting=3, oldest=START
                ),
                PendingForPair(
                    symptom_code=FREQUENT,
                    machine_model=M710IC,
                    waiting=1,
                    oldest=START + timedelta(days=2),
                ),
            ]
        )

        assert [(group.machine_model, group.waiting) for group in groups] == [
            (R2000IC, 5),
            (M710IC, 1),
        ]
        assert groups[0].oldest == START


# ─────────────────────────────────────────────────────────────
# Over HTTP, against a real PostgreSQL (ADR-031)
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


def _finding(
    symptom_code: SymptomCode,
    machine_id: MachineId,
    *,
    detected_at: datetime,
    occurrence_count: int = 1,
    rule_id: str,
) -> Finding:
    return Finding(
        machine_id=machine_id,
        component=ComponentLabel("spindle_motor"),
        symptom_code=symptom_code,
        severity=Severity.HIGH,
        rule_id=RuleId(rule_id),
        detected_at=detected_at,
        evidence={"value": 92.0, "threshold": 85.0},
        status=FindingStatus.OPEN,
        occurrence_count=occurrence_count,
        last_seen_at=detected_at,
    )


def _approved(symptom_code: SymptomCode, *, step: PlaybookStep, source_doc: DocumentId) -> Playbook:
    return Playbook(
        symptom_code=symptom_code,
        machine_model=R2000IC,
        steps=(step,),
        tools=(),
        parts=(),
        estimated_minutes=45,
        required_skill=SkillId("robot_mechanical"),
        required_technicians=1,
        source_doc=source_doc,
        page=4,
        revision=1,
        status=PlaybookStatus.APPROVED,
        approved_by=UserId("eng-1"),
        approved_at=START,
        approver_role=Role.ENGINEER,
    )


@pytest.fixture
def setup(database_url: str, tmp_path: Path) -> Iterator[dict[str, Any]]:
    """A plant that has been running: five symptoms in four different states."""
    clock = SimulatedClock(START)
    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    auth = Authentication(LocalAccounts(), clock)

    with connect(database_url) as conn:
        conn.execute(
            "TRUNCATE finding, job, playbook_proposal, playbook, access_log, session, "
            "account, chunk, document_page, document CASCADE"
        )
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)
        current, replaced = (
            library.add(
                conn,
                content=content,
                filename=filename,
                content_type="application/pdf",
                machine_model=R2000IC,
                title=title,
                uploaded_by=UserId("eng-1"),
            )
            for content, filename, title in (
                (b"%PDF-1.7 the current manual", "r-2000ic.pdf", "R-2000iC Maintenance"),
                (b"%PDF-1.7 the superseded one", "r-2000ic-2019.pdf", "R-2000iC Maintenance 2019"),
            )
        )

        # Seen three times, resolved twice: still three times seen, and the one
        # that should rank first. Raised open and then resolved, because that is
        # the only way a Finding reaches `resolved` (ADR-023) and the table
        # refuses one with no resolution time.
        for index in range(3):
            ref = triggers.raise_finding(
                conn,
                _finding(
                    FREQUENT,
                    MC_012,
                    detected_at=START + timedelta(hours=index),
                    rule_id=f"R-FREQ-{index}",
                ),
            )
            if index < 2:
                triggers.resolve(conn, ref, now=START + timedelta(hours=index, minutes=30))

        # Seen once, and it fired two hundred times while it was open. Second on
        # the list, because a stuck channel is one event (ADR-023).
        triggers.raise_finding(
            conn,
            _finding(
                OCCASIONAL,
                MC_018,
                detected_at=START + timedelta(hours=4),
                occurrence_count=200,
                rule_id="R-OCC-1",
            ),
        )

        # Answered: an approved playbook exists for this pair, so it is not a gap
        # however many times it was raised.
        triggers.raise_finding(
            conn,
            _finding(ANSWERED, MC_004, detected_at=START, occurrence_count=12, rule_id="R-ANS-1"),
        )
        # Drafted but never approved: on the list, with the draft reported.
        triggers.raise_finding(
            conn,
            _finding(
                DRAFTED_ONLY, MC_004, detected_at=START + timedelta(hours=2), rule_id="R-DRAFT-1"
            ),
        )
        # Served with a warning: the third list, not the first.
        triggers.raise_finding(
            conn,
            _finding(FLAGGED, MC_004, detected_at=START + timedelta(hours=3), rule_id="R-FLAG-1"),
        )

        for symptom_code, document in ((ANSWERED, current), (FLAGGED, replaced)):
            step = PlaybookStep(
                text="Retighten the motor mount bolts to 42 Nm.",
                source_doc=document.document_id,
                page=4,
                confidence=0.8,
            )
            playbooks.save_approved(
                conn,
                _approved(symptom_code, step=step, source_doc=document.document_id),
                approved_by=UserId("eng-1"),
                approved_at=START,
                approver_role=Role.ENGINEER,
            )

        # The older manual is replaced: the playbook citing it is still served,
        # with a warning, and lands on the third list rather than the first
        # (ADR-018).
        flagged = playbooks.flag_for_review(
            conn, replaced.document_id, reason="the manual was replaced"
        )

        step = PlaybookStep(
            text="Check the drive belt tension.",
            source_doc=current.document_id,
            page=7,
            confidence=0.6,
        )

        # Two proposals pending for the symptom nobody has approved anything for.
        for index in range(2):
            playbooks.add_proposal(
                conn,
                symptom_code=DRAFTED_ONLY,
                machine_model=R2000IC,
                origin=ProposalOrigin.DRAFTED,
                outcome="repair",
                steps=(step,),
                tools=(),
                proposed_skill=SkillId("robot_mechanical"),
                proposed_minutes=30,
                rejected=(),
                reason=f"draft {index}",
                created_at=START + timedelta(hours=index),
                created_by=None,
            )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "library": library, "clock": clock, "flagged": flagged}
    finally:
        pool.close()


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    app = create_app(pool=setup["pool"], library=setup["library"], clock=setup["clock"])
    with TestClient(app) as test_client:
        yield test_client


def _at(serialised: str) -> datetime:
    """Whatever shape the JSON encoder gives a UTC moment, as a moment."""
    return datetime.fromisoformat(serialised.replace("Z", "+00:00"))


def _log_in(client: TestClient, role: Role) -> None:
    user, _ = PEOPLE[role]
    assert client.post("/sessions", json={"user": user, "password": PASSWORD}).status_code == 201


@pytest.mark.db
class TestTheGapsEndpoint:
    def test_the_symptoms_are_ordered_by_how_often_they_were_seen(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps").json()

        codes = [row["symptom_code"] for row in body["no_playbook"]["rows"]]
        assert codes[:2] == [FREQUENT, OCCASIONAL]
        assert body["no_playbook"]["rows"][0]["findings"] == 3
        assert body["no_playbook"]["rows"][0]["machines"] == [MC_012]

    def test_an_answered_symptom_is_absent_and_a_drafted_one_is_present(
        self, client: TestClient
    ) -> None:
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps").json()

        rows = {row["symptom_code"]: row for row in body["no_playbook"]["rows"]}
        assert ANSWERED not in rows
        assert DRAFTED_ONLY in rows
        assert rows[DRAFTED_ONLY]["proposals_waiting"] == 2

    def test_a_playbook_served_with_a_warning_is_the_third_list_not_the_first(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps").json()

        assert setup["flagged"], "the cascade flagged nothing; the fixture is wrong"
        flagged = {row["symptom_code"] for row in body["manual_changed"]["rows"]}
        assert FLAGGED in flagged
        assert body["manual_changed"]["count"] == len(flagged)
        assert FLAGGED not in {row["symptom_code"] for row in body["no_playbook"]["rows"]}
        assert body["manual_changed"]["rows"][0]["review_reason"] == "the manual was replaced"

    def test_the_queue_is_counted_per_machine_model(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps").json()

        assert body["awaiting_review"]["count"] == 2
        assert [
            (row["machine_model"], row["waiting"]) for row in body["awaiting_review"]["rows"]
        ] == [(R2000IC, 2)]
        assert _at(body["awaiting_review"]["rows"][0]["oldest"]) == START

    def test_a_truncated_list_still_reports_its_total(self, client: TestClient) -> None:
        """No silent caps: a screen showing one row of four must say four."""
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps", params={"limit": 1}).json()

        assert len(body["no_playbook"]["rows"]) == 1
        assert body["no_playbook"]["count"] >= 3

    def test_the_time_it_was_computed_comes_from_the_clock(self, client: TestClient) -> None:
        """ADR-050: computed when asked, and it says when that was."""
        _log_in(client, Role.ENGINEER)

        body = client.get("/overview/gaps").json()

        assert _at(body["at"]) == START

    def test_a_supervisor_may_read_it_and_a_technician_may_not(self, client: TestClient) -> None:
        _log_in(client, Role.SUPERVISOR)
        assert client.get("/overview/gaps").status_code == 200

        _log_in(client, Role.TECHNICIAN)
        assert client.get("/overview/gaps").status_code == 403

    def test_every_count_traces_to_rows_that_already_existed(self, client: TestClient) -> None:
        """The line this endpoint may not cross (design.md 4, ADR-050).

        Each list is re-derived here from the tables themselves. If a count on
        the response ever needed a table of its own, this test is what fails.
        """
        _log_in(client, Role.ENGINEER)
        body = client.get("/overview/gaps", params={"limit": 200}).json()

        with connect(os.environ["DATABASE_URL"]) as conn:
            findings = {
                (row[0], row[1]): row[2]
                for row in conn.execute(
                    "SELECT symptom_code, machine_id, count(*) FROM finding "
                    "GROUP BY symptom_code, machine_id"
                ).fetchall()
            }
            served = {
                (row[0], row[1])
                for row in conn.execute(
                    "SELECT symptom_code, machine_model FROM playbook"
                ).fetchall()
            }
            pending = conn.execute(
                "SELECT count(*) FROM playbook_proposal WHERE status = 'pending'"
            ).fetchone()
            flagged = conn.execute(
                "SELECT count(*) FROM playbook WHERE status = 'needs_review'"
            ).fetchone()

        assert pending is not None and flagged is not None
        assert body["awaiting_review"]["count"] == pending[0]
        assert body["manual_changed"]["count"] == flagged[0]
        for row in body["no_playbook"]["rows"]:
            assert (row["symptom_code"], row["machine_model"]) not in served
            assert row["findings"] == sum(
                count
                for (symptom_code, machine_id), count in findings.items()
                if symptom_code == row["symptom_code"] and machine_id in row["machines"]
            )

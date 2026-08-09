"""The first endpoints, against a real PostgreSQL (ADR-024, ADR-019, ADR-036).

Every test here is an HTTP request. That is the point rather than a style
choice: invariant 6 says the approval endpoint must reject a non-engineer **at
the endpoint** rather than by hiding a button, and a test that calls the service
function proves the function works, not that the route uses it.

The route being guarded here is the document fetch. It is the one ADR-019
describes and the one slice 3.1 deliberately left unbuilt until there was
something to authorise against.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, connect
from psycopg_pool import ConnectionPool

from pdm.api.app import create_app
from pdm.api.deps import SESSION_COOKIE
from pdm.contracts import MachineModel, Role, UserId
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SimulatedClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore

pytestmark = pytest.mark.db

START = datetime(2026, 3, 3, 8, 0, tzinfo=UTC)
MANUAL = b"%PDF-1.7\n" + b"page of a synthetic manual. " * 40

PEOPLE = {
    Role.TECHNICIAN: (UserId("tech-1"), "Somchai"),
    Role.ENGINEER: (UserId("eng-1"), "Pranee"),
    Role.SUPERVISOR: (UserId("sup-1"), "Anan"),
    Role.OPERATOR: (UserId("op-1"), "Malee"),
}
PASSWORD = "correct horse battery staple"


@pytest.fixture
def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def clock() -> SimulatedClock:
    return SimulatedClock(START)


@pytest.fixture
def setup(database_url: str, tmp_path: Path, clock: SimulatedClock) -> Iterator[dict[str, Any]]:
    """A pool, a library, four accounts and one stored manual."""
    with connect(database_url) as conn:
        conn.execute("TRUNCATE access_log, session, account CASCADE")
        conn.execute("TRUNCATE chunk, document_page, document CASCADE")
        conn.commit()

    library = DocumentLibrary(FilesystemObjectStore(tmp_path), clock)
    auth = Authentication(LocalAccounts(), clock)

    with connect(database_url) as conn:
        for role, (user, name) in PEOPLE.items():
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)
        document = library.add(
            conn,
            content=MANUAL,
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=MachineModel("R-2000iC"),
            title="R-2000iC Maintenance Manual",
            uploaded_by=UserId("op-1"),
        )
        conn.commit()

    pool = ConnectionPool(database_url, min_size=1, max_size=3, open=True)
    try:
        yield {"pool": pool, "library": library, "document": document, "clock": clock}
    finally:
        pool.close()


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    app = create_app(pool=setup["pool"], library=setup["library"], clock=setup["clock"])
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[Any]]:
    connection = connect(database_url)
    try:
        yield connection
    finally:
        connection.close()


def _log_in(client: TestClient, role: Role) -> None:
    user, _ = PEOPLE[role]
    response = client.post("/sessions", json={"user": user, "password": PASSWORD})
    assert response.status_code == 201, response.text


class TestSigningIn:
    def test_the_right_password_opens_a_session(self, client: TestClient) -> None:
        user, name = PEOPLE[Role.ENGINEER]

        response = client.post("/sessions", json={"user": user, "password": PASSWORD})

        assert response.status_code == 201
        assert response.json() == {"user": user, "display_name": name, "role": "engineer"}
        assert client.cookies.get(SESSION_COOKIE)

    def test_the_wrong_password_does_not(self, client: TestClient) -> None:
        user, _ = PEOPLE[Role.ENGINEER]

        response = client.post("/sessions", json={"user": user, "password": "not it"})

        assert response.status_code == 401
        assert client.cookies.get(SESSION_COOKIE) is None

    def test_an_unknown_user_is_refused_the_same_way(self, client: TestClient) -> None:
        """One message for every failure. Distinguishing them turns the login
        form into a way of listing who works here (ADR-036)."""
        unknown = client.post("/sessions", json={"user": "nobody", "password": PASSWORD})
        wrong = client.post(
            "/sessions", json={"user": PEOPLE[Role.ENGINEER][0], "password": "not it"}
        )

        assert unknown.status_code == wrong.status_code == 401
        assert unknown.json() == wrong.json()

    def test_the_session_cookie_is_not_readable_by_scripts(self, client: TestClient) -> None:
        user, _ = PEOPLE[Role.ENGINEER]
        response = client.post("/sessions", json={"user": user, "password": PASSWORD})

        header = response.headers["set-cookie"].lower()
        assert "httponly" in header
        assert "samesite=strict" in header

    def test_whoami_needs_a_session(self, client: TestClient) -> None:
        assert client.get("/sessions/current").status_code == 401

    def test_logging_out_ends_the_session_server_side(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """Clearing the cookie alone would leave a row anybody holding the token
        could still use, which is the whole reason sessions are rows."""
        _log_in(client, Role.ENGINEER)
        token = client.cookies.get(SESSION_COOKIE)

        assert client.delete("/sessions").status_code == 204

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM session WHERE token = %s", (token,))
            row = cur.fetchone()
        assert row is not None and row[0] == 0


class TestASessionIsNotForever:
    def test_an_expired_session_is_refused(self, client: TestClient, setup: dict[str, Any]) -> None:
        """Twelve hours, checked against the Clock rather than the database, so
        a compressed run and the application agree about the time (ADR-028)."""
        _log_in(client, Role.ENGINEER)
        assert client.get("/sessions/current").status_code == 200

        setup["clock"].advance(timedelta(hours=13))

        assert client.get("/sessions/current").status_code == 401

    def test_withdrawing_access_takes_effect_on_the_next_request(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """Not at the next login. A role or an account withdrawn this morning
        that keeps working until somebody signs out is the failure a revocable
        session exists to prevent (ADR-036)."""
        _log_in(client, Role.ENGINEER)
        assert client.get("/sessions/current").status_code == 200

        with conn.cursor() as cur:
            cur.execute("UPDATE account SET active = false WHERE user_id = %s", ("eng-1",))
            conn.commit()

        assert client.get("/sessions/current").status_code == 401

    def test_a_changed_role_is_seen_immediately(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """The role is read from the account on every request, never carried in
        the session."""
        _log_in(client, Role.TECHNICIAN)
        assert client.get("/sessions/current").json()["role"] == "technician"

        with conn.cursor() as cur:
            cur.execute("UPDATE account SET role = 'engineer' WHERE user_id = %s", ("tech-1",))
            conn.commit()

        assert client.get("/sessions/current").json()["role"] == "engineer"


class TestReadingADocument:
    def test_no_session_no_document(self, client: TestClient, setup: dict[str, Any]) -> None:
        """ADR-019: every read through RBAC, without exception. There is no
        presigned URL and no anonymous route."""
        response = client.get(f"/documents/{setup['document'].document_id}")

        assert response.status_code == 401

    @pytest.mark.parametrize("role", list(PEOPLE))
    def test_anybody_signed_in_may_read_a_manual(
        self, client: TestClient, setup: dict[str, Any], role: Role
    ) -> None:
        """Reading is the job. The control ADR-019 asks for is that it goes
        through RBAC and into the log, not that it is rare."""
        _log_in(client, role)

        response = client.get(f"/documents/{setup['document'].document_id}")

        assert response.status_code == 200
        assert response.content == MANUAL

    def test_a_document_that_is_not_there(self, client: TestClient) -> None:
        _log_in(client, Role.ENGINEER)

        assert client.get(f"/documents/{'0' * 64}").status_code == 404

    def test_the_response_says_how_to_display_it(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        """inline rather than attachment: the point is a reviewer opening page
        47 beside a drafted step, not a download."""
        _log_in(client, Role.ENGINEER)

        response = client.get(f"/documents/{setup['document'].document_id}")

        assert response.headers["content-type"].startswith("application/pdf")
        assert response.headers["content-disposition"].startswith("inline")
        assert response.headers["accept-ranges"] == "bytes"


class TestRangeRequests:
    """ADR-019 calls this mandatory: citation to a page number is the system's
    central interaction, and without ranges every click downloads a whole
    scanned manual."""

    def test_a_range_returns_only_those_bytes(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(
            f"/documents/{setup['document'].document_id}", headers={"Range": "bytes=9-16"}
        )

        assert response.status_code == 206
        assert response.content == MANUAL[9:17]
        assert response.headers["content-range"] == f"bytes 9-16/{len(MANUAL)}"

    def test_an_open_ended_range_runs_to_the_end(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(
            f"/documents/{setup['document'].document_id}", headers={"Range": "bytes=100-"}
        )

        assert response.status_code == 206
        assert response.content == MANUAL[100:]

    def test_a_suffix_range_returns_the_last_bytes(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(
            f"/documents/{setup['document'].document_id}", headers={"Range": "bytes=-20"}
        )

        assert response.status_code == 206
        assert response.content == MANUAL[-20:]

    def test_a_range_past_the_end_is_refused(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(
            f"/documents/{setup['document'].document_id}",
            headers={"Range": f"bytes={len(MANUAL) + 10}-"},
        )

        assert response.status_code == 416
        assert response.headers["content-range"] == f"bytes */{len(MANUAL)}"

    def test_a_range_nobody_can_parse_is_refused(
        self, client: TestClient, setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.ENGINEER)

        response = client.get(
            f"/documents/{setup['document'].document_id}", headers={"Range": "pages=1-2"}
        )

        assert response.status_code == 416


class TestUploadingIsRestrictedAtTheEndpoint:
    """Invariant 6's shape, on the route this slice has for it.

    ADR-024 puts uploading a manual with the operator and the engineer. The
    check has to be the endpoint refusing, not the frontend hiding a button: a
    technician with a session and a curl command is the case that decides
    whether the rule exists.
    """

    def _upload(self, client: TestClient) -> Any:
        return client.post(
            "/documents",
            data={"machine_model": "M-710iC", "title": "M-710iC Manual"},
            files={"file": ("m710.pdf", b"%PDF-1.7\nsecond manual\n", "application/pdf")},
        )

    @pytest.mark.parametrize("role", [Role.OPERATOR, Role.ENGINEER])
    def test_the_roles_adr_024_names_may_upload(self, client: TestClient, role: Role) -> None:
        _log_in(client, role)

        response = self._upload(client)

        assert response.status_code == 201, response.text
        assert response.json()["machine_model"] == "M-710iC"

    @pytest.mark.parametrize("role", [Role.TECHNICIAN, Role.SUPERVISOR])
    def test_everybody_else_is_refused_by_the_endpoint(
        self, client: TestClient, role: Role
    ) -> None:
        _log_in(client, role)

        assert self._upload(client).status_code == 403

    def test_an_unauthenticated_upload_is_refused_before_the_role_is_considered(
        self, client: TestClient
    ) -> None:
        assert self._upload(client).status_code == 401

    def test_a_refusal_is_in_the_access_log(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """The line that matters after an incident, and the one a rolled-back
        transaction was throwing away."""
        _log_in(client, Role.TECHNICIAN)
        self._upload(client)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, role, allowed FROM access_log WHERE action = 'upload_document'"
            )
            assert list(cur.fetchall()) == [("tech-1", "technician", False)]

    def test_an_uploaded_manual_can_be_read_back(self, client: TestClient) -> None:
        """The two halves of ADR-019 meeting: stored through the API, served
        through the API, both authorised and both logged."""
        _log_in(client, Role.OPERATOR)
        document_id = self._upload(client).json()["document_id"]

        response = client.get(f"/documents/{document_id}")

        assert response.status_code == 200
        assert response.content == b"%PDF-1.7\nsecond manual\n"


class TestTheAccessLog:
    """ADR-019: every read into the log, without exception. The log is why
    documents are served through the API at all rather than by a URL."""

    def _lines(self, conn: Connection[Any], action: str) -> list[tuple[Any, ...]]:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id, role, subject, allowed FROM access_log "
                "WHERE action = %s ORDER BY id",
                (action,),
            )
            return list(cur.fetchall())

    def test_a_read_is_recorded_with_who_and_what(
        self, client: TestClient, conn: Connection[Any], setup: dict[str, Any]
    ) -> None:
        _log_in(client, Role.TECHNICIAN)
        client.get(f"/documents/{setup['document'].document_id}")

        lines = self._lines(conn, "read_document")

        assert lines == [("tech-1", "technician", setup["document"].document_id, True)]

    def test_a_failed_login_is_recorded_too(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """ "Who tried to sign in as the engineer at two in the morning" is a
        question the log should answer, and one holding only successes cannot."""
        client.post("/sessions", json={"user": "eng-1", "password": "not it"})

        assert self._lines(conn, "log_in") == [("eng-1", None, None, False)]

    def test_a_read_of_a_document_that_does_not_exist_is_still_recorded(
        self, client: TestClient, conn: Connection[Any]
    ) -> None:
        """The attempt is the interesting part. A log that only records
        successful reads cannot answer what somebody went looking for."""
        _log_in(client, Role.OPERATOR)
        client.get(f"/documents/{'0' * 64}")

        assert self._lines(conn, "read_document") == [("op-1", "operator", "0" * 64, True)]

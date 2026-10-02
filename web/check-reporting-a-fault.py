"""Report a fault through the web server, the way a phone with no JavaScript does.

Slice 16.2's "done when" asks for exactly this: somebody standing at a machine
tells the system about something no rule caught, and it appears in the queue as
their words. Every assertion goes through http://localhost:3000, so what is
checked is the screen and the web server's calls to the API - not the API alone,
which `tests/api/test_reporting_a_fault.py` covers.

The account it signs in as is an **operator**, deliberately. ADR-077 §1 is the
claim that whoever is standing there may report, and this shell has offered an
operator nothing at all since it was built; a check that signed in as a
technician would pass without ever testing the sentence.

It seeds its own accounts, like the other screen checks, so it truncates
`account` and must not run before `check-sign-in.py`. Run it against a built app
and a running API:

    export DATABASE_URL=postgresql://$USER@localhost:5432/pdm_web_check
    export STORAGE_DIR=/tmp/pdm-storage PYTHONPATH=.
    uv run alembic upgrade head
    uv run python -m pdm.api &
    cd web && npm run build
    mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/
    API_URL=http://localhost:8000 node .next/standalone/server.js &

    uv run python web/check-reporting-a-fault.py
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
import os
import re
import sys
import urllib.request

from psycopg import connect

from pdm.contracts import Role, UserId
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock

# Where the screens are. The defaults are the ports docker-compose.yml publishes
# on the host; the rehearsal runs this from inside the compose network, where
# the addresses are service names (ADR-067).
WEB = os.environ.get("PDM_WEB_URL", "http://localhost:3000")

OPERATOR = UserId("op-1")
PASSWORD = "demo-operator"
# A machine that is in `config/plant.yaml`. The screen offers a list rather than
# a text box, so a machine number that is not on the floor cannot be typed.
MACHINE = "MC-012"
SEEN = "มีน้ำมันไหลใต้ฐานเครื่อง ประมาณฝ่ามือ ตั้งแต่ต้นกะ"
SOMETHING_ELSE = "คนละเรื่องกับใบเดิม: การ์ดนิรภัยไม่ล็อก"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


def seed() -> None:
    """One account, and an empty queue.

    `work_order` is truncated because the refusal being checked below is about a
    machine that already has work open, and a queue left over from another check
    would refuse the first report as well as the second - which would look like
    the rule working when it is the fixture.
    """
    clock = SystemClock()
    auth = Authentication(LocalAccounts(), clock)
    with connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "playbook, playbook_proposal, access_log, session, account CASCADE"
        )
        auth.create_account(
            conn,
            user=OPERATOR,
            display_name="มาลี",
            role=Role.OPERATOR,
            password=PASSWORD,
        )
        conn.commit()


def hidden_fields(page: str) -> list[tuple[str, str]]:
    """The fields Next puts in a form so that it still posts without JavaScript.

    Their presence is also what makes the screen work on a phone whose bundle
    never arrived, which is the network this is built for.
    """
    fields: list[tuple[str, str]] = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', page):
        name = re.search(r'name="([^"]*)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name is not None:
            unescaped = htmllib.unescape(value.group(1)) if value is not None else ""
            fields.append((htmllib.unescape(name.group(1)), unescaped))
    return fields


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-reporting"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def readable(page: str) -> str:
    """The page with React's text-node separators taken out, so the assertions
    below are about what a person reads rather than about the renderer."""
    return re.sub(r"<!--.*?-->", "", page)


def get(path: str) -> str:
    with opener.open(f"{WEB}{path}") as response:
        return str(response.read().decode())


def submit(path: str, fields: list[tuple[str, str]]) -> str:
    body, content_type = multipart(fields)
    request = urllib.request.Request(
        f"{WEB}{path}",
        data=body,
        # Next refuses a server action whose origin it cannot check. A browser
        # sends this for free; a script has to say so.
        headers={"content-type": content_type, "origin": WEB},
        method="POST",
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in() -> None:
    """Sign in from nobody. The jar is emptied first because `/sign-in` renders
    no form to somebody who already has a session."""
    jar.clear()
    page = get("/sign-in")
    submit("/sign-in", [*hidden_fields(page), ("user", str(OPERATOR)), ("password", PASSWORD)])


def report(page: str, description: str) -> str:
    """Fill the form on `page` and send it, carrying whatever it already holds.

    The hidden fields are read back off the rendered page rather than
    remembered, which is the whole point of the retry below: `distinct_from`
    reaches the API only if the screen actually put the references back into the
    form (ADR-077 §3).
    """
    fields = [
        *hidden_fields(page),
        ("machine_id", MACHINE),
        ("severity", "medium"),
        ("description", description),
    ]
    return readable(submit("/report", fields))


def main() -> None:
    seed()

    print("\n1. an operator can reach the screen at all")
    sign_in()
    home = readable(get("/"))
    expect("แจ้งงานเสีย" in home, "the shell offers reporting to an operator (ADR-077 §1)")

    form = readable(get("/report"))
    expect(MACHINE in form, "the machines on the floor are offered as a list, not typed")
    expect('value="critical"' not in form, "critical is not on the screen (ADR-077 §2)")
    expect("โทรหาหัวหน้ากะ" in form, "and the screen says what to do instead")

    print("\n2. what they saw becomes a ticket")
    created = report(form, SEEN)
    first = re.search(r"WO-\d+", created)
    expect(first is not None, "the screen answers with the ticket number")
    assert first is not None
    expect("หัวหน้ากะยืนยัน" in created, "and says a person still releases it (ADR-071)")

    print("\n3. the same machine again is refused, naming what is already open")
    again = report(readable(get("/report")), SOMETHING_ELSE)
    expect(first.group(0) in again, "the refusal names the open ticket (ADR-077 §3)")
    expect("มีงานค้างอยู่แล้ว" in again, "and says why it is refused")
    # Without JavaScript the page comes back rendered from scratch, so a refusal
    # that dropped the fields would ask somebody standing at a machine to type it
    # all again before they could say it is something else.
    expect(SOMETHING_ELSE in again, "and what was typed is still in the form")
    expect(f'value="{MACHINE}" selected' in again, "with the machine still chosen")

    print("\n4. saying it is something else gets through, and the ticket says so")
    different = report(again, SOMETHING_ELSE)
    second = re.search(r"WO-\d+", different)
    expect(second is not None, "a second ticket is written")
    assert second is not None
    expect(
        second.group(0) != first.group(0),
        "and it is a different ticket rather than the first one again",
    )

    print("\n5. the words on the ticket are the reporter's own")
    with connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            "SELECT reason, origin, status, reported_by FROM work_order ORDER BY work_order_ref"
        ).fetchall()
    expect(len(rows) == 2, "two tickets, not four - the refusal held (ADR-023's argument)")
    reasons = [row[0] for row in rows]
    expect(SEEN in reasons[0], "the description is on the ticket unrewritten (ADR-005)")
    # The reason names them as the board does; the record keeps the sign-in (ADR-122).
    expect(rows[0][3] == str(OPERATOR), "with who reported it")
    expect(first.group(0) in reasons[1], "and the second names the ticket it was raised beside")
    expect(
        all(row[1] == "manual" and row[2] == "queued" for row in rows),
        "both are manual work, queued for a round to propose (ADR-010, ADR-071)",
    )

    print("\nreporting a fault works end to end")


if __name__ == "__main__":
    main()

"""Drive the overview the way a shift lead's browser does, with no JavaScript.

Slice 10.5's "done when", in order: buffers drawn to scale from the endpoint's
own values rather than with fixed widths, a predicted station that always
renders its interval, releasing held work that is impossible without a reason,
and every figure coming from `/overview/line`, `/overview/gaps` or
`/dispatch/round`.

The scale assertion is the one that carries the slice. `lib/line-scale.test.ts`
proves the arithmetic against two buffer maps; this proves the arithmetic
reached the markup.

Run it the same way as `check-the-technicians-screen.py` - see that file's
docstring for the environment it needs.

The confirmation panel this screen also carries (ADR-071) is driven end to end
by `check-the-technicians-screen.py`, which has to confirm before it has a job to
assert on - so the supervisor's half is exercised there rather than asserted twice
against a seeded world tuned for the load gate.
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from psycopg import connect

from pdm.contracts import (
    ComponentLabel,
    Finding,
    FindingKind,
    MachineId,
    MachineModel,
    Role,
    RuleId,
    Severity,
    ShiftAssignment,
    ShiftId,
    SkillId,
    SymptomCode,
    Technician,
    UserId,
)
from pdm.dispatch import repo as dispatch_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.triggers import repo as findings
from pdm.work import WorkOrders
from pdm.work import repo as work_repo

# Where the screens are. The defaults are the ports docker-compose.yml publishes
# on the host, which is what a person running this check by hand has. The
# rehearsal runs it from inside the compose network instead, where the addresses
# are service names (ADR-067).
WEB = os.environ.get("PDM_WEB_URL", "http://localhost:3000")
API = os.environ.get("PDM_API_URL", "http://localhost:8000")
SUPERVISOR = UserId("sup-1")
TECHNICIAN = UserId("tech-1")
PASSWORDS = {SUPERVISOR: "demo-supervisor", TECHNICIAN: "demo-technician"}
R2000 = MachineModel("R-2000iC")

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


def readable(page: str) -> str:
    """The page without React's text-node separators. See the sibling check."""
    return re.sub(r"<!--.*?-->", "", page)


def shift_now(config: object, now: datetime) -> tuple[ShiftId, datetime]:
    zone = ZoneInfo(config.plant.timezone)  # type: ignore[attr-defined]
    local = now.astimezone(zone)
    for shift in config.plant.shifts:  # type: ignore[attr-defined]
        starts, ends = shift.starts_at, shift.ends_at
        if starts < ends:
            if starts <= local.time() < ends:
                return ShiftId(str(shift.shift_id)), local
        elif local.time() >= starts:
            return ShiftId(str(shift.shift_id)), local
        elif local.time() < ends:
            return ShiftId(str(shift.shift_id)), local - timedelta(days=1)
    raise AssertionError("the shifts in plant.yaml do not cover the whole day")


def seed() -> None:
    """Two faults on the line, and a shift too full to take everything."""
    url = os.environ["DATABASE_URL"]
    clock = SystemClock()
    now = clock.now()
    config = load_config(Path("config"))
    auth = Authentication(LocalAccounts(), clock)
    fallback = {str(m): dict(rows) for m, rows in config.policy.fallback_minutes.items()}
    orders = WorkOrders(clock, fallback_minutes=fallback)
    shift_id, local = shift_now(config, now)

    # The first station in the config, and one further down: the diagram has to
    # show two different states at two different buffers.
    line = config.plant.lines[0]
    stations = list(line.stations)
    first = stations[0]
    later = stations[-1]

    with connect(url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "playbook, playbook_proposal, access_log, session, account CASCADE"
        )
        for user, name, role in [
            (SUPERVISOR, "อนันต์", Role.SUPERVISOR),
            (TECHNICIAN, "สมชาย", Role.TECHNICIAN),
        ]:
            auth.create_account(
                conn, user=user, display_name=name, role=role, password=PASSWORDS[user]
            )

        # Thirty minutes of one technician against several hours of work: the
        # shift is heavy, so the gate has something to hold and to name.
        dispatch_repo.add_technician(
            conn,
            Technician(user=TECHNICIAN, skills=frozenset({SkillId("robot_mechanical")})),
            known_skills=frozenset({SkillId("robot_mechanical")}),
            now=now,
        )
        dispatch_repo.assign_to_shift(
            conn,
            ShiftAssignment(
                shift_id=shift_id,
                on_date=local.date(),
                technician=TECHNICIAN,
                available_minutes=30,
            ),
        )

        over = MachineId(str(later.machines[0].machine_id))
        predicted_at = MachineId(str(first.machines[0].machine_id))

        detected = Finding(
            machine_id=over,
            component=ComponentLabel("belt_motor"),
            symptom_code=SymptomCode("SYM-014"),
            severity=Severity.CRITICAL,
            rule_id=RuleId("R-motor-temp-high"),
            detected_at=now - timedelta(minutes=20),
            evidence={"value": 91.0, "threshold": 85.0, "for_seconds": 1200},
        )
        orders.from_finding(
            conn,
            detected,
            finding_ref=findings.raise_finding(conn, detected),
            machine_model=R2000,
        )

        coming = Finding(
            machine_id=predicted_at,
            component=ComponentLabel("bearing"),
            symptom_code=SymptomCode("SYM-031"),
            severity=Severity.HIGH,
            rule_id=RuleId("R-vibration-trend"),
            detected_at=now - timedelta(hours=1),
            evidence={"trend": True},
            kind=FindingKind.PREDICTED,
            eta=now + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
        )
        orders.from_finding(
            conn, coming, finding_ref=findings.raise_finding(conn, coming), machine_model=R2000
        )

        # Low-severity work the heavy band will hold back, so the panel has
        # something to name and something to release (ADR-011).
        #
        # `distinct_from` carries what is already open on that machine, because a
        # report is refused while a machine has work open unless somebody says
        # this is a different fault (ADR-077 §3). Three separate faults on one
        # machine is what this fixture is for, and it now has to say so.
        for description in ("weeping seal", "loose guard", "worn belt"):
            orders.from_report(
                conn,
                machine_id=predicted_at,
                machine_model=R2000,
                severity=Severity.LOW,
                reported_by=SUPERVISOR,
                description=description,
                # Read again each time round, so the third report names the two
                # before it as well as the Finding's own order.
                distinct_from=work_repo.open_for_machine(conn, predicted_at),
            )
        conn.commit()

    print(f"seeded: {shift_id} on {local.date()}, line {line.line_id}")


def hidden_fields(page: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', page):
        name = re.search(r'name="([^"]*)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name is not None:
            unescaped = htmllib.unescape(value.group(1)) if value is not None else ""
            fields.append((htmllib.unescape(name.group(1)), unescaped))
    return fields


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-the-overview"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


# The name the API sets. `SESSION_COOKIE` in src/pdm/api/deps.py.
SESSION_COOKIE = "pdm_session"


def session_token() -> str | None:
    for cookie in jar:
        if cookie.name == SESSION_COOKIE:
            return cookie.value
    return None


def get(path: str, where: str = WEB) -> str:
    request = urllib.request.Request(f"{where}{path}")
    if where != WEB:
        # Reading the API directly means standing in for the Next server, which
        # forwards this visitor's session cookie (web/lib/api.ts). The jar will
        # not do it: the cookie was set for the web host and the API is a
        # different one.
        #
        # That is only true in the topology this ships as. Published on
        # localhost the two are one host and two ports, and cookies ignore the
        # port - so the jar sent it by accident, and the check passed for a
        # reason that has nothing to do with what it is testing. Running the
        # checks inside the stack is what exposed it (ADR-067). The sibling
        # check-sign-in.py has always done this deliberately.
        token = session_token()
        if token is not None:
            request.add_header("cookie", f"{SESSION_COOKIE}={token}")
    with opener.open(request) as response:
        return str(response.read().decode())


def submit(path: str, fields: list[tuple[str, str]], extra: list[tuple[str, str]]) -> str:
    body, content_type = multipart([*fields, *extra])
    request = urllib.request.Request(
        f"{WEB}{path}",
        data=body,
        headers={"content-type": content_type, "origin": WEB},
        method="POST",
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in(user: UserId) -> None:
    jar.clear()
    page = get("/sign-in")
    submit("/sign-in", hidden_fields(page), [("user", str(user)), ("password", PASSWORDS[user])])
    # Signing in either worked or it did not, and the next thing this check does
    # is read the API directly with whatever the jar holds. Without this line a
    # sign-in that quietly failed surfaces several calls later as an unexplained
    # 401 from a different host, which is what it did during the first
    # rehearsals of the whole stack (ADR-067) and cost an hour to place.
    expect(session_token() is not None, f"signing in as {user} left a session")


def overrides_for(ref: str) -> list[str]:
    """What was written down about one order, read from the database.

    The screen saying it recorded something is not the same as a row existing,
    and the row is the whole point of the button (ADR-059).
    """
    with connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute(
            "SELECT kind FROM work_order_override WHERE work_order_ref = %s ORDER BY at",
            (ref,),
        ).fetchall()
    return [str(row[0]) for row in rows]


def main() -> None:
    seed()
    sign_in(SUPERVISOR)

    print("\n1. the line is drawn, and drawn to scale")
    page = readable(get("/overview"))
    line = json.loads(get("/overview/line", where=API))["lines"][0]
    stations = line["stations"]

    expect(all(station["station_id"] in page for station in stations), "every station is on it")

    # The endpoint's buffers, as fractions of the widest. Fixed widths would
    # give every gap the same number and fail here whatever the map looks like.
    buffers = [max(station["buffer_units"], 0.25) for station in stations[:-1]]
    widest = max(buffers)
    wanted = [round(buffer / widest, 4) for buffer in buffers]
    drawn = [round(float(value), 4) for value in re.findall(r"flex-grow:([0-9.]+)", page)]
    expect(drawn == wanted, f"each gap is its own buffer, to scale: {drawn} == {wanted}")
    expect(len(set(drawn)) > 1, "and the gaps are not all the same width")

    print("\n2. a prediction never appears without its interval")
    predicted = [one for one in stations if one["state"] == "predicted"]
    expect(len(predicted) == 1, "the seeded prediction reached the line")
    expect("คาดว่าจะถึงเกณฑ์ราว" in page, "the screen says when it is expected")
    expect("บวกลบ" in page, "and never without the give-or-take (ADR-020)")

    over = [one for one in stations if one["state"] == "over_threshold"]
    expect(len(over) == 1, "and the detected fault is on it too")
    expect("เกินเกณฑ์มาแล้ว" in page, "said as elapsed time rather than as a forecast")

    print("\n3. the shift band, from the round rather than recomputed")
    band = json.loads(get("/overview/line", where=API))["shift"]
    expect(f"{round(band['load_ratio'] * 100)}%" in page, "the load is the figure the round gave")
    expect(band["summary"] in page, "and the gate's own sentence is quoted, not paraphrased")

    print("\n4. held work is named on the shift lead's board, not counted")
    board = readable(get("/board"))
    held = json.loads(get("/dispatch/round", where=API))["held"]
    expect(len(held) > 0, "the heavy shift is holding something back")
    expect("ระบบกันไว้ก่อน" in board, "the board has a column for it (ADR-093)")
    for one in held:
        why = one["why"]
        expect(why in board, f"why {one['ref']} is held is on the board, as the gate wrote it")

    print("\n5. releasing it without a reason is impossible from here")
    first = held[0]["ref"]
    refused = submit("/overview/release", [], [("ref", first), ("reason", "   ")])
    expect("เขียนเหตุผล" in readable(refused), "a release with no reason is refused (ADR-059)")
    expect(
        overrides_for(first) == [],
        "and nothing was written down for it",
    )

    released = submit(
        "/overview/release",
        [],
        [("ref", first), ("reason", "สาย A หยุดรอชิ้นนี้อยู่")],
    )
    expect(f"ปล่อย {first} แล้ว" in readable(released), "with a reason the screen names what it did")
    expect(
        "รอบถัดไปจะจัดช่างให้" in readable(released),
        "and says the next round places it, rather than pretending the queue moved",
    )
    expect(
        overrides_for(first) == ["release_held"],
        "and the override is on the record, once (ADR-059)",
    )

    print("\n6. what the system cannot answer has its own screen (ADR-093)")
    unanswered = json.loads(get("/overview/gaps", where=API))
    gaps_page = readable(get("/gaps"))
    expect("อาการที่ยังไม่มีขั้นตอนซ่อม" in gaps_page, "the screen exists at all")
    for row in unanswered["no_playbook"]["rows"]:
        expect(
            row["symptom_code"] in gaps_page, f"{row['symptom_code']} is named, not just counted"
        )

    print("\n7. machine health: two lists, and what the screen cannot say")
    health = json.loads(get("/overview/health", where=API))
    expect("สุขภาพเครื่องจักร" in page, "the panel is on the supervisor's overview")
    expect(
        "เสียบ่อยที่สุดในช่วงที่นับ" in page and "มีเรื่องค้างอยู่ตอนนี้" in page,
        "two lists and never one (ADR-072 §2)",
    )
    for row in health["by_history"]:
        expect(
            row["machine_id"] in page,
            f"{row['machine_id']} is on the panel",
        )
    # The reason is the backend's, quoted rather than rebuilt from the numbers
    # beside it (ADR-081 §5).
    quoted = health["by_history"][0]["history"]["reason"]
    expect(quoted in page, "the sentence on screen is the one the backend wrote")
    for sentence in health["absent"]:
        expect(sentence in page, f"the screen says what it cannot: {sentence[:40]}...")
    expect(
        all("score" not in row for row in health["by_history"]),
        "no reading carries a blended figure (ADR-072 §2)",
    )

    print("\n8. a technician is not offered this screen")
    sign_in(TECHNICIAN)
    theirs = readable(get("/overview"))
    expect("หน้านี้เป็นของหัวหน้ากะและวิศวกร" in theirs, "the page says whose it is")
    expect("flex-grow" not in theirs, "and draws no line for them")

    print("\nall checks passed")


if __name__ == "__main__":
    main()

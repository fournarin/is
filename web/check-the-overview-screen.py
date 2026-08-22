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

WEB = "http://localhost:3000"
API = "http://localhost:8000"
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
            (SUPERVISOR, "Anan (supervisor)", Role.SUPERVISOR),
            (TECHNICIAN, "Somchai (technician)", Role.TECHNICIAN),
        ]:
            auth.create_account(
                conn, user=user, display_name=name, role=role, password=PASSWORDS[user]
            )

        # Thirty minutes of one technician against several hours of work: the
        # shift is heavy, so the gate has something to hold and to name.
        dispatch_repo.add_technician(
            conn,
            Technician(user=TECHNICIAN, skills=frozenset({SkillId("robot_mechanical")})),
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
        for description in ("weeping seal", "loose guard", "worn belt"):
            orders.from_report(
                conn,
                machine_id=predicted_at,
                machine_model=R2000,
                severity=Severity.LOW,
                reported_by=SUPERVISOR,
                description=description,
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


def form_with(page: str, marker: str) -> list[tuple[str, str]]:
    for form in re.findall(r"<form\b.*?</form>", page, re.DOTALL):
        if marker in form:
            return hidden_fields(form)
    raise AssertionError(f"no form containing {marker!r}")


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-the-overview"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def get(path: str, where: str = WEB) -> str:
    with opener.open(f"{where}{path}") as response:
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

    print("\n4. held work is named, not counted")
    held = json.loads(get("/dispatch/round", where=API))["held"]
    expect(len(held) > 0, "the heavy shift is holding something back")
    for one in held:
        expect(one["ref"] in page, f"{one['ref']} is named on the screen (ADR-011)")

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
        "รอบถัดไปจะจัดคนให้" in readable(released),
        "and says the next round places it, rather than pretending the queue moved",
    )
    expect(
        overrides_for(first) == ["release_held"],
        "and the override is on the record, once (ADR-059)",
    )

    print("\n6. what the system cannot answer is on the same screen")
    unanswered = json.loads(get("/overview/gaps", where=API))
    expect("ที่ระบบยังตอบไม่ได้" in page, "the section exists at all")
    expect(
        f"({unanswered['no_playbook']['count']})" in page,
        "with the count of symptoms that have nothing to serve",
    )
    for row in unanswered["no_playbook"]["rows"]:
        expect(row["symptom_code"] in page, f"{row['symptom_code']} is named, not just counted")

    print("\n7. a technician is not offered this screen")
    sign_in(TECHNICIAN)
    theirs = readable(get("/overview"))
    expect("หน้านี้เป็นของหัวหน้ากะและวิศวกร" in theirs, "the page says whose it is")
    expect("flex-grow" not in theirs, "and draws no line for them")

    print("\nall checks passed")


if __name__ == "__main__":
    main()

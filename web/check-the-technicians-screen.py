"""Drive the technician's screen end to end, the way a phone with no JavaScript does.

Slice 10.3's "done when" asks for exactly this: see the job, read the reason,
start it, step through, hand over with a note. Every assertion below goes
through http://localhost:3000, so what is being checked is the screen and the
web server's calls to the API - not the API on its own, which
`tests/api/test_the_job_a_technician_opens.py` covers.

It seeds its own world, because a screen showing one job needs a shift with
somebody on it, a playbook, a Finding and an order, and the round has to place
the one on the other. The shift is chosen from the clock rather than hardcoded,
so the check works at whatever hour somebody runs it.

    export DATABASE_URL=postgresql://$USER@localhost:5432/pdm_web_check
    export STORAGE_DIR=/tmp/pdm-storage PYTHONPATH=.
    uv run alembic upgrade head
    uv run python -m pdm.api &
    cd web && npm run build
    mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/
    API_URL=http://localhost:8000 node .next/standalone/server.js &

    uv run python web/check-the-technicians-screen.py
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
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
    Playbook,
    PlaybookStatus,
    PlaybookStep,
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
from pdm.dispatch.service import DispatchRounds
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.config import load_config
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore, storage_root
from pdm.playbooks import repo as playbooks
from pdm.retrieval import repo as index
from pdm.retrieval.domain import Chunk, IndexedPage, PageOutcome
from pdm.triggers import repo as findings
from pdm.work import WorkOrders

# Where the screens are. The defaults are the ports docker-compose.yml publishes
# on the host, which is what a person running this check by hand has. The
# rehearsal runs it from inside the compose network instead, where the addresses
# are service names (ADR-067).
WEB = os.environ.get("PDM_WEB_URL", "http://localhost:3000")
TECHNICIAN = UserId("tech-1")
ENGINEER = UserId("eng-1")
# The shipped configuration is `confirmation: supervisor` (ADR-071), so a
# technician has nothing at all until somebody with this role presses confirm.
# The check signs in as both, in that order, because that is the plant's order.
SUPERVISOR = UserId("sup-1")
PASSWORD = "demo-technician"
ENGINEER_PASSWORD = "demo-engineer"
SUPERVISOR_PASSWORD = "demo-supervisor"
BOTTLENECK = MachineId("MC-012")
R2000 = MachineModel("R-2000iC")
SYM = SymptomCode("SYM-014")
RULE = RuleId("R-motor-temp-high/trend")
STEPS = (
    "หยุดหุ่นยนต์ด้วยปุ่มหยุดฉุกเฉิน",
    # A step that sends the technician to another page. Page 2 is indexed below;
    # page 900 is not, and the screen has to say so rather than offer a link to
    # nothing (2026-09-29: "lockout procedure on page 2" linked only page 5).
    "ตัดเบรกเกอร์ CP-3 แล้วใส่กุญแจล็อกของตัวเอง ตามขั้นตอนล็อกเอาต์ในหน้า 2",
    "ถอดฝาครอบพัดลมออก ดูรูปประกอบที่ page 900",
)
LOCKOUT_PAGE = "Safety and lockout. Open breaker CP-3 and apply a personal lock."

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


# ── the world the screen needs ────────────────────────────────────────────


def shift_now(config: object, now: datetime) -> tuple[ShiftId, datetime]:
    """The shift the plant is in right now, and the date it is filed under.

    Chosen rather than hardcoded so the check passes at any hour. Shift
    boundaries in `plant.yaml` are local wall-clock times (ADR-045 §7), and a
    night shift that runs past midnight is filed under the day it began.
    """
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


def seed() -> list[str]:
    """The world the screen needs, **including a round that has actually run**.

    This is the line the defect ADR-071 §7 records hid behind. The screen used
    to filter what a fresh round *would* place, and `dispatch()` places only work
    that is still `queued` - so the job was on the screen exactly as long as no
    round had committed. Every check here passed because `scripts/rehearse.py`
    scales `worker-runtime` to zero while they run, and nothing else ever ran one.

    Returns what the round decided, so the supervisor below can answer it.
    """
    url = os.environ["DATABASE_URL"]
    clock = SystemClock()
    now = clock.now()
    config = load_config(Path("config"))
    auth = Authentication(LocalAccounts(), clock)
    library = DocumentLibrary(FilesystemObjectStore(storage_root()), clock)
    fallback = {str(m): dict(rows) for m, rows in config.policy.fallback_minutes.items()}
    orders = WorkOrders(clock, fallback_minutes=fallback)
    shift_id, local = shift_now(config, now)

    with connect(url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, "
            "playbook, playbook_proposal, access_log, session, account CASCADE"
        )
        for user, name, role, password in [
            (TECHNICIAN, "สมชาย", Role.TECHNICIAN, PASSWORD),
            (ENGINEER, "ปราณี", Role.ENGINEER, ENGINEER_PASSWORD),
            (SUPERVISOR, "อนันต์", Role.SUPERVISOR, SUPERVISOR_PASSWORD),
        ]:
            auth.create_account(conn, user=user, display_name=name, role=role, password=password)

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
                available_minutes=240,
            ),
        )

        manual = library.add(
            conn,
            content=b"%PDF-1.4 a manual with enough bytes to range over" + b" " * 4096,
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000,
            title="R-2000iC Maintenance Manual",
            uploaded_by=ENGINEER,
        ).document_id
        index.replace_pages(
            conn,
            manual,
            [
                IndexedPage(
                    document_id=manual,
                    page=2,
                    outcome=PageOutcome.TEXT,
                    characters=len(LOCKOUT_PAGE),
                )
            ],
        )
        index.insert_chunks(conn, [Chunk(document_id=manual, page=2, ordinal=0, text=LOCKOUT_PAGE)])
        playbook = Playbook(
            symptom_code=SYM,
            machine_model=R2000,
            steps=tuple(
                PlaybookStep(text=text, source_doc=manual, page=142 + index, confidence=0.9)
                for index, text in enumerate(STEPS)
            ),
            estimated_minutes=45,
            required_skill=SkillId("robot_mechanical"),
            required_technicians=1,
            source_doc=manual,
            page=142,
            status=PlaybookStatus.APPROVED,
            approved_by=ENGINEER,
            approved_at=now,
            approver_role=Role.ENGINEER,
        )
        playbooks.save_approved(
            conn, playbook, approved_by=ENGINEER, approved_at=now, approver_role=Role.ENGINEER
        )

        finding = Finding(
            machine_id=BOTTLENECK,
            component=ComponentLabel("belt_motor"),
            symptom_code=SYM,
            severity=Severity.HIGH,
            rule_id=RULE,
            detected_at=now - timedelta(hours=1),
            evidence={"trend": True, "slope_per_hour": 1.4},
            kind=FindingKind.PREDICTED,
            eta=now + timedelta(hours=6),
            eta_confidence=timedelta(hours=2),
        )
        finding_ref = findings.raise_finding(conn, finding)
        for minute in range(3):
            findings.repeat(
                conn,
                machine_id=BOTTLENECK,
                rule_id=RULE,
                now=now - timedelta(minutes=30 - minute),
            )
        orders.from_finding(conn, finding, finding_ref=finding_ref, machine_model=R2000)
        # A second job, so the screen has something to keep collapsed.
        orders.from_report(
            conn,
            machine_id=MachineId("MC-001"),
            machine_model=R2000,
            severity=Severity.LOW,
            reported_by=ENGINEER,
            description="weeping seal on the gearbox",
        )
        report = DispatchRounds(clock, config).run(conn)
        conn.commit()

    print(
        f"seeded: {shift_id} on {local.date()}, {len(STEPS)} steps; "
        f"the round proposed {len(report.proposed)}"
    )
    assert report.proposed, "a round that proposed nothing leaves the screen with nothing to show"
    return list(report.proposed)


# ── driving the screen ────────────────────────────────────────────────────


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
    """The hidden fields of the one form containing `marker`.

    A page with two server actions on it carries two sets of `$ACTION_*` fields,
    and posting them together sends a request that names both. Scoping to one
    form is what a browser does for free.
    """
    for form in re.findall(r"<form\b.*?</form>", page, re.DOTALL):
        if marker in form:
            return hidden_fields(form)
    raise AssertionError(f"no form containing {marker!r}")


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-the-screen"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def readable(page: str) -> str:
    """The page with React's text-node separators taken out.

    Server-rendered React writes `<!-- -->` between two adjacent text nodes, so
    `ถัดไป (1)` arrives as `ถัดไป (<!-- -->1<!-- -->)`. A person reads the
    first; matching on the second would make every assertion here a statement
    about React's renderer instead of about the screen.
    """
    return re.sub(r"<!--.*?-->", "", page)


def get(path: str) -> str:
    with opener.open(f"{WEB}{path}") as response:
        return str(response.read().decode())


def submit(
    path: str, fields: list[tuple[str, str]], extra: list[tuple[str, str]] | None = None
) -> str:
    body, content_type = multipart([*fields, *(extra or [])])
    request = urllib.request.Request(
        f"{WEB}{path}",
        data=body,
        # Next refuses a server action whose origin it cannot check. A
        # browser sends this for free; a script has to say so.
        headers={"content-type": content_type, "origin": WEB},
        method="POST",
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in(user: UserId = TECHNICIAN, password: str = PASSWORD) -> None:
    """Sign in as somebody, from nobody.

    The jar is emptied first because `/sign-in` does not render a form to
    somebody who already has a session - it sends them to their own screen - and
    the hidden `$ACTION_*` field scraped from that page belongs to a different
    form. Switching account is what a person does with a second browser or after
    signing out, and this is the script's version of both.
    """
    jar.clear()
    page = get("/sign-in")
    submit("/sign-in", hidden_fields(page), [("user", str(user)), ("password", password)])


def main() -> None:
    proposed = seed()

    print("\n0. before the shift lead answers, the technician has nothing - and is told why")
    sign_in()
    waiting = readable(get("/work"))
    expect("รอหัวหน้ากะยืนยัน" in waiting, "the screen says the work is waiting on an approval")
    expect("MC-012" not in waiting, "and no unconfirmed job is on it (ADR-071 §7)")

    print("\n0b. the shift lead confirms, through their own screen")
    sign_in(SUPERVISOR, SUPERVISOR_PASSWORD)
    panel = readable(get("/board"))
    expect("รอคุณยืนยัน" in panel, "the supervisor is asked, by name, about each one")
    for ref in proposed:
        submit("/overview/confirm", [("ref", ref)])
    expect("ไม่มีงานรอยืนยัน" in readable(get("/board")), "and the list empties as they answer")

    sign_in()

    print("\n1. the queue shows one job, and says why it is that one")
    queue = get("/work")
    shown = readable(queue)
    # Split at the list of what is queued behind it (ADR-093 made it a plain
    # section rather than a collapsed one).
    above_the_fold, _, behind = shown.partition("งานถัดไปของคุณ (")
    expect("MC-012" in above_the_fold, "the machine the scheduler chose")
    expect(
        "วางแผนซ่อม" in above_the_fold,
        "a predicted job is banded as planned, never as urgent (ADR-020)",
    )
    expect("ด่วน" not in above_the_fold, "and nothing above the fold calls it urgent")
    expect("คาดว่าจะถึงเกณฑ์" in above_the_fold, "the reason the backend wrote is on it")
    expect(
        "เกิดซ้ำ" not in above_the_fold,
        "a forecast recomputed on every reading is not shown as repeated failures (ADR-093)",
    )
    expect(
        "ทำไมต้องทำงานนี้ก่อน" in above_the_fold, "the priority reason is on the first screen (ADR-005)"
    )
    expect(
        behind.startswith("1)"),
        "one more job is queued behind it, and visible",
    )
    expect(
        'href="/work/' not in behind,
        "and nothing in that list is a link, so it cannot be picked (ADR-011)",
    )

    print("\n1b. disagreeing is recorded, and the queue does not move")
    expect(
        "ไม่เห็นด้วยว่าควรทำงานนี้ก่อน" in above_the_fold, "the objection sits beside the reason (ADR-005)"
    )
    blank = submit("/work", form_with(queue, 'name="reason"'), [("reason", "  ")])
    expect("เขียนสั้น ๆ" in readable(blank), "an objection with no reason is refused (ADR-059)")

    objected = submit(
        "/work",
        form_with(queue, 'name="reason"'),
        [("reason", "MC-004 หยุดสายจริง งานนี้รอได้")],
    )
    expect(
        "ส่งความเห็นแล้วเมื่อ" in readable(objected),
        "it says what was written down, not that it hopes so",
    )
    expect("ลำดับงานยังเหมือนเดิม" in readable(objected), "and says plainly that nothing reordered")

    # The assertion the whole button rests on: a queue that could be argued down
    # is not a queue, and the load gate stops meaning anything (ADR-011, ADR-059).
    after = readable(get("/work"))
    expect(
        after.partition("งานถัดไปของคุณ (")[0] == above_the_fold,
        "the job on top is byte-for-byte the one that was there before the objection",
    )

    print("\n2. starting the job goes straight to the steps")
    steps = submit("/work", form_with(queue, "รับงานและเริ่มทำ"))
    expect("ขั้นที่ 1 จาก 3" in readable(steps), "the first step of three")
    expect(STEPS[0] in steps, "and it is the first step of the playbook that was snapshotted")
    expect("อ่านคู่มือหน้า 142" in readable(steps), "with the page it came from")
    cited = re.search(r'href="(/work/[^"]+/manual\?doc=[^"]+?page=142[^"]*)"', steps)
    expect(cited is not None, "read inside the job, not in another tab (third trial)")
    if cited is not None:
        page = get(htmllib.unescape(cited.group(1)))
        expect("หน้า 142" in readable(page), "the cited page opens with its number")
        expect("กลับไปขั้นที่ 1" in readable(page), "one tap back to the step it came from")
        expect("/manual/" in page, "and the PDF is still there, through this server (ADR-058)")

    print("\n3. stepping through")
    second = get("/work/" + ref_from(steps) + "/steps?step=2")
    expect("ขั้นที่ 2 จาก 3" in readable(second), "step two")
    expect(STEPS[1] in second, "shows the second instruction")
    last = get("/work/" + ref_from(steps) + "/steps?step=3")
    expect("ครบทุกขั้น ปิดงาน" in last, "and the last one offers closing instead of another step")

    print("\n3b. a step that names another page lets the technician open it")
    expect(
        re.search(r'href="/work/[^"]+/manual\?doc=[^"]+?page=2(&amp;|&)step=2"', second)
        is not None,
        "step two says page 2, and page 2 of the same manual is one tap away",
    )
    expect("อ่านหน้า 2 ที่ขั้นนี้อ้างถึง" in readable(second), "labelled as the page the step names")
    expect(
        re.search(r"page=900", last) is None,
        "page 900 was never read from the manual, so it is not offered as a link",
    )
    expect("หน้า 900 ที่ขั้นนี้อ้างถึง ไม่มีในคู่มือที่ระบบอ่านไว้" in readable(last), "and the screen says so")

    print("\n4. closing the job")
    ref = ref_from(steps)
    close_page = get(f"/work/{ref}/close")
    expect("ปิดงาน" in close_page, "the close screen is reachable from the steps")
    expect("ไม่พบปัญหา" in close_page, "and offers the false-alarm outcome (ADR-022)")
    expect(
        "ไม่ต้องกรอกเวลาที่ใช้" in readable(close_page),
        "and says plainly that it never asks for a duration (ADR-006, ADR-025)",
    )
    expect(
        'name="actual_minutes"' not in close_page and 'name="minutes"' not in close_page,
        "no field anywhere asks for one",
    )

    refused = submit(f"/work/{ref}/close/send", [], [("blocked_reason", "waiting_parts")])
    expect("เลือกก่อนว่างานจบอย่างไร" in readable(refused), "a close with no outcome is refused")

    # The job started seconds ago, so twenty minutes of waiting is longer than
    # the work it interrupted and the API refuses it (ADR-056). What matters
    # here is that the screen hands back the sentence saying so rather than a
    # status code, because somebody is reading it at a machine.
    impossible = submit(
        f"/work/{ref}/close/send",
        [],
        [("outcome", "fixed"), ("blocked_reason", "waiting_parts"), ("blocked_minutes", "20")],
    )
    expect(
        "เวลารอต้องไม่เกินเวลาทำงาน" in impossible,
        "an impossible number comes back as the sentence that says what to change",
    )

    closed = submit(
        f"/work/{ref}/close/send",
        [],
        [
            ("outcome", "no_problem_found"),
            ("blocked_reason", "waiting_parts"),
            ("blocked_minutes", "0"),
            ("technician_feedback", "วัดแล้วอุณหภูมิปกติ น่าจะเป็นเซนเซอร์"),
        ],
    )
    expect("งานของฉัน" in closed, "closing lands back on the queue")

    print("\n5. the queue advances to the next job")
    after_closing = readable(get("/work"))
    expect(ref not in after_closing, "the job that was closed is gone")
    expect("MC-001" in after_closing, "and the one that was queued behind it is now on top")
    expect("ถัดไป" not in after_closing, "with nothing left behind it")

    print("\n6. what the close actually wrote")
    stored = closed_order(ref)
    expect(stored["status"] == "closed", "the order is closed")
    expect(stored["outcome"] == "no_problem_found", "with the outcome that was chosen")
    # ADR-006: waiting for a part is not repair time, and left in it inflates the
    # estimate for this symptom every cycle.
    expect(stored["blocked_reason"] == ["waiting_parts"], "and the chip that was tapped")
    expect(stored["blocked_minutes"] == 0, "and the minutes that were not repair")
    expect(
        stored["technician_feedback"] == "วัดแล้วอุณหภูมิปกติ น่าจะเป็นเซนเซอร์",
        "and the note, which is the only thing here a person wrote in words",
    )

    print("\n7. handing over the next job needs a note")
    next_ref = ref_from(after_closing)
    next_steps = submit("/work", form_with(get("/work"), "รับงานและเริ่มทำ"))
    expect(next_ref in readable(next_steps), "the next job starts")
    blank = submit(
        f"/work/{next_ref}/steps",
        form_with(next_steps, 'name="note"'),
        [("note", "   ")],
    )
    expect("ก่อนส่งต่องาน" in readable(blank), "whitespace is not a handover note (ADR-025)")
    handed = submit(
        f"/work/{next_ref}/steps",
        form_with(next_steps, 'name="note"'),
        [("note", "ถอดฝาครอบแล้ว รออะไหล่")],
    )
    expect("งานของฉัน" in handed, "with a note it goes through")

    print("\n8. the manual opens at a page rather than downloading whole")
    document = re.search(r'href="/manual/([^"#]+)#page=(\d+)"', steps)
    assert document is not None
    request = urllib.request.Request(f"{WEB}/manual/{document.group(1)}")
    request.add_header("range", "bytes=0-99")
    with opener.open(request) as response:
        expect(response.status == 206, "a range request comes back 206 (ADR-019)")
        expect(len(response.read()) == 100, "with only the bytes that were asked for")

    print("\n9. a link to a job that is not there says so")
    # 2026-09-30: a kept link to an order that no longer exists answered 500 and
    # "เชื่อมต่อระบบไม่ได้ชั่วคราว ... กดลองใหม่", which is untrue - trying again
    # never helps. Read without the scripts, because that is what a phone whose
    # bundle never arrived is shown.
    for screen in ("steps", "close", "print"):
        try:
            gone = readable(get(f"/work/WO-999999/{screen}"))
            gone = re.sub(r"<script.*?</script>", "", gone, flags=re.S)
        except urllib.error.HTTPError as error:
            gone = f"HTTP {error.code}"
        expect("ไม่พบใบงานนี้" in gone, f"/work/WO-999999/{screen} says the job is not there")
        expect("งานของฉัน" in gone, "and keeps the way back to the technician's own work")

    print("\nall checks passed")


def closed_order(ref: str) -> dict[str, object]:
    """What the close wrote, read back from the database.

    Not from a screen: a screen agreeing with itself proves nothing about what
    was stored. `actual_minutes` and `repair_minutes` are deliberately absent -
    they are computed from the work segments (ADR-025) and are 9.1's tests to
    make, not this screen's.
    """
    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT status, outcome, blocked_minutes, blocked_reason, technician_feedback "
            "FROM work_order WHERE work_order_ref = %s",
            (ref,),
        ).fetchone()
    assert row is not None, f"no work order {ref}"
    return {
        "status": row[0],
        "outcome": row[1],
        "blocked_minutes": row[2],
        "blocked_reason": list(row[3] or []),
        "technician_feedback": row[4],
    }


def ref_from(page: str) -> str:
    found = re.search(r"WO-[0-9]+", readable(page))
    assert found is not None, "no work order ref on the steps page"
    return found.group(0)


if __name__ == "__main__":
    main()

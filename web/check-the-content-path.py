"""A manual becomes a draft becomes a playbook, through the screens (slice 17.2).

This is ADR-003 walked end to end - the constraint the whole system is built
around, and until this check existed, the one path nothing exercised from one
end to the other. The unit tests cover ingest, drafting and the review screen
separately; each seeds the stage before it by hand. What none of them prove is
that a manual put into the library the way `scripts/seed_demo.py` puts it there
comes out as an approved playbook a technician can be sent with.

Every step goes through http://localhost:3000 except the seeding and the final
read, so what is checked is the screens and this server's calls to the API.

It uses **SYM-047 on the M-710iC**, and that choice is a measurement rather than
a preference: `docs/drafting-baseline.md` reports that the extractive drafter
hands the right page for SYM-047 and the wrong one for SYM-014 and SYM-021 -
those two get an overview page that repeats the question's words, which is the
failure reranking exists to fix and which is not built. A check written on a
symptom the drafter gets wrong would be a check that fails for a reason the
baseline already documents.

The question is asked in **Thai** against manuals written in English, which is
the cross-lingual case ADR-029 requires the embedding model to handle.

    export DATABASE_URL=postgresql://$USER@localhost:5432/pdm_web_check
    export STORAGE_DIR=/tmp/pdm-storage PYTHONPATH=.
    uv run alembic upgrade head
    uv run python -m pdm.api &
    cd web && npm run build
    mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/
    API_URL=http://localhost:8000 node .next/standalone/server.js &

    uv run python web/check-the-content-path.py
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
import os
import re
import sys
import time
import urllib.request

from psycopg import connect

from fixtures.corpus import CORPUS
from pdm.contracts import (
    ComponentLabel,
    Finding,
    MachineId,
    Role,
    RuleId,
    Severity,
    SymptomCode,
    UserId,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.jobs import JobClass, JobKind
from pdm.platform.jobs import repo as jobs
from pdm.platform.objects import FilesystemObjectStore, storage_root
from pdm.triggers import repo as findings_repo

WEB = os.environ.get("PDM_WEB_URL", "http://localhost:3000")

ENGINEER = UserId("eng-1")
PASSWORD = "demo-engineer"
# The symptom the drafter gets right, on the machine that has it.
SYM = SymptomCode("SYM-047")

# The approver's Thai for the six steps page 5 prescribes, in order. Every figure
# matches its step, which the API checks (ADR-095); the demo then shows a
# technician Thai steps with the manual's words beneath them.
THAI = [
    "ตัดพลังงานตู้ควบคุมตามขั้นตอนล็อกเอาต์ในหน้า 2",
    "รอให้ตู้เย็นลงก่อน พื้นผิวด้านในยังร้อนอยู่หลายนาทีหลังตัดไดรฟ์",
    "ถอดขั้วต่อพัดลมที่เทอร์มินัลบล็อก X4",
    "ถอดสกรูยึดพัดลมทั้งสี่ตัว (ขันไว้ที่แรงบิด 3 Nm) แล้วดึงชุดพัดลมออก",
    "ใส่พัดลมตัวใหม่ ขันสกรูยึดที่แรงบิด 3 Nm แล้วต่อขั้วต่อ X4 กลับ",
    "จ่ายไฟกลับ แล้วตรวจว่าพัดลมหมุนถึง 1500 rpm ภายใน 30 วินาที",
]
MACHINE = MachineId("MC-018")
RULE = RuleId("R-fan-rpm-low")
COMPONENT = ComponentLabel("cooling_fan")
ANSWER = CORPUS.answer(SYM)

# Indexing two manuals on a CPU is not fast, and neither is a draft. Generous,
# and a failure here is a real one: these are the two jobs the demo waits on
# while somebody is in the room.
INDEX_TIMEOUT = 300
DRAFT_TIMEOUT = 300

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


def seed() -> None:
    """The world `scripts/seed_demo.py` leaves, plus one Finding.

    The Finding is what puts the symptom on the gaps panel: that panel lists
    what the plant has *asked* for and has no answer to, not every symptom in
    the configuration (ADR-060). Without one, there would be nothing to press.
    """
    clock = SystemClock()
    now = clock.now()
    auth = Authentication(LocalAccounts(), clock)
    library = DocumentLibrary(FilesystemObjectStore(storage_root()), clock)

    with connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, playbook, playbook_proposal, chunk, "
            "document_page, document, access_log, session, account CASCADE"
        )
        auth.create_account(
            conn,
            user=ENGINEER,
            display_name="ปราณี",
            role=Role.ENGINEER,
            password=PASSWORD,
        )
        for document in CORPUS.documents:
            row = library.add(
                conn,
                content=document.path.read_bytes(),
                filename=document.filename,
                content_type="application/pdf",
                machine_model=document.machine_model,
                title=document.title,
                uploaded_by=ENGINEER,
                edition=document.edition,
            )
            jobs.enqueue(
                conn,
                job_class=JobClass.AUTHORING,
                kind=JobKind.INGEST.value,
                payload={"document_id": row.document_id},
                now=now,
            )
        findings_repo.raise_finding(
            conn,
            Finding(
                machine_id=MACHINE,
                component=COMPONENT,
                symptom_code=SYM,
                severity=Severity.MEDIUM,
                rule_id=RULE,
                detected_at=now,
                evidence={"value": 1080.0, "threshold": 1200.0, "for_seconds": 240},
            ),
        )
        conn.commit()


def counted(sql: str) -> int:
    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(sql).fetchone()
        return int(row[0]) if row else 0


def wait_for(sql: str, *, seconds: int, what: str) -> None:
    """Poll until a worker has done something, or say what did not happen.

    A timeout here is not a slow machine to wait out: it means
    `worker-authoring` is not running, or is failing the job, and both are worth
    the check going red rather than hanging.
    """
    deadline = time.monotonic() + seconds
    # One connection for the whole wait rather than one per tick, which is up to
    # a hundred of them. Autocommit because the alternative is a transaction
    # held open for five minutes to ask a question every three seconds.
    with connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        while time.monotonic() < deadline:
            row = conn.execute(sql).fetchone()
            if row is not None and int(row[0]) > 0:
                return
            time.sleep(3)
    expect(False, f"{what} within {seconds}s - is worker-authoring running?")


def hidden_fields(page: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for tag in re.findall(r'<input[^>]*type="hidden"[^>]*>', page):
        name = re.search(r'name="([^"]*)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name is not None:
            unescaped = htmllib.unescape(value.group(1)) if value is not None else ""
            fields.append((htmllib.unescape(name.group(1)), unescaped))
    return fields


def form_with(page: str, *markers: str) -> list[tuple[str, str]]:
    """The hidden fields of the first form matching every marker.

    Every row of the gaps panel renders the same draft-request form, so a marker
    naming the field picks whichever row happens to render first. Identifying a
    row takes its own value as well, which is why this takes more than one.
    """
    for form in re.findall(r"<form\b.*?</form>", page, re.DOTALL):
        if all(marker in form for marker in markers):
            return hidden_fields(form)
    raise AssertionError(f"no form containing all of {markers!r}")


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-the-content-path"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def readable(page: str) -> str:
    return re.sub(r"<!--.*?-->", "", page)


def get(path: str) -> str:
    with opener.open(f"{WEB}{path}") as response:
        return str(response.read().decode())


def submit(path: str, fields: list[tuple[str, str]]) -> str:
    body, content_type = multipart(fields)
    request = urllib.request.Request(
        f"{WEB}{path}",
        data=body,
        headers={"content-type": content_type, "origin": WEB},
        method="POST",
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in() -> None:
    jar.clear()
    page = get("/sign-in")
    submit("/sign-in", [*hidden_fields(page), ("user", str(ENGINEER)), ("password", PASSWORD)])


def main() -> None:
    print(f"seeding: two manuals, one Finding for {SYM} on {MACHINE}")
    seed()

    print("\n1. the manuals are indexed because the seed queued them")
    wait_for("SELECT count(*) FROM chunk", seconds=INDEX_TIMEOUT, what="nothing was indexed")
    expect(counted("SELECT count(*) FROM document_page") > 0, "pages were extracted and stored")
    expect(counted("SELECT count(*) FROM chunk") > 0, "and chunked for retrieval")

    print("\n2. the gaps panel names the symptom nothing serves, and offers a draft")
    sign_in()
    # On a stack started from nothing the first render can come back before
    # the web server has warmed up, and once it listed nothing. Read again for
    # up to thirty seconds rather than fail a fresh rehearsal on a cold cache;
    # a symptom that never appears still fails below.
    overview = readable(get("/gaps"))
    for _ in range(15):
        if str(SYM) in overview:
            break
        time.sleep(2)
        overview = readable(get("/gaps"))
    expect(str(SYM) in overview, f"{SYM} is listed as having no playbook (ADR-060)")
    expect("ขอร่างใหม่" in overview, "and an engineer is offered a draft from that row")

    print("\n3. asking in Thai, of manuals written in English (ADR-029)")
    # The row's own hidden fields rather than values typed here: what the check
    # proves is that the screen carries the right pair, and a value supplied
    # twice is the first of the two, not the one written last.
    asked = readable(
        submit(
            "/overview/draft",
            [
                *form_with(overview, 'name="question"', f'value="{SYM}"'),
                ("question", ANSWER.queries.th),
            ],
        )
    )
    # Every answer from that route is a redirect the opener follows, so a refusal
    # arrives as a page rather than as an error. Unread, it becomes a five-minute
    # wait blamed on worker-authoring.
    refused = re.search(r'role="alert">([^<]*)', asked)
    expect(
        refused is None,
        "the screen accepted the request"
        if refused is None
        else f"the screen refused it: {refused.group(1).strip()}",
    )
    wait_for(
        "SELECT count(*) FROM playbook_proposal",
        seconds=DRAFT_TIMEOUT,
        what="no draft was written",
    )

    print("\n4. the draft is in the review queue, with where it came from")
    queue = readable(get("/review"))
    expect(str(SYM) in queue, "the queue lists it")
    expect(f"{ANSWER.machine_model} (1)" in queue, "grouped under its machine model (ADR-064)")

    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT proposal_id, outcome, steps FROM playbook_proposal WHERE symptom_code = %s",
            (str(SYM),),
        ).fetchone()
    assert row is not None
    proposal_id, outcome, steps = int(row[0]), str(row[1]), row[2]
    expect(outcome == "repair", f"it drafted a repair rather than fault-finding (got {outcome})")
    pages = {int(step["page"]) for step in steps}
    wanted, got = set(ANSWER.answer_pages), sorted(pages)
    expect(
        pages == wanted,
        f"every step comes from the page the answer key names {sorted(wanted)} (got {got})",
    )

    detail = readable(get(f"/review/{proposal_id}"))
    expect("<mark>" in detail, "the span each step was taken from is highlighted on the page")
    expect("เปิดคู่มือที่หน้า" in detail, "with a link that opens the manual there (ADR-019)")

    print("\n5. a person approves it, and only then does it exist")
    approved = readable(
        submit(
            f"/review/{proposal_id}",
            [
                *[
                    field
                    for field in form_with(detail, 'name="required_skill"')
                    if field[0] != "thai"
                ],
                *[("thai", text) for text in THAI],
                ("required_skill", str(ANSWER.required_skill)),
                ("estimated_minutes", str(ANSWER.estimated_minutes)),
                ("required_technicians", "1"),
            ],
        )
    )
    # Not "the page mentions the queue": "คิวรีวิว" is in the nav of every screen
    # behind sign-in, so it answers whether the approval happened or not. What a
    # successful one removes is the row itself.
    expect(str(SYM) not in approved, "the queue no longer lists what was just approved")

    with connect(os.environ["DATABASE_URL"]) as conn:
        book = conn.execute(
            "SELECT status, revision, approved_by, approver_role, required_skill, "
            "estimated_minutes, steps FROM playbook WHERE symptom_code = %s",
            (str(SYM),),
        ).fetchone()
    expect(book is not None, "a playbook exists where there was none")
    assert book is not None
    status, revision, approved_by, approver_role, skill, minutes, book_steps = book
    expect(status == "approved", "and it is approved rather than draft (invariant 3, ADR-038)")
    expect(int(revision) == 1, "at revision 1")
    expect(str(approved_by) == str(ENGINEER), f"by {ENGINEER}")
    expect(
        str(approver_role) == "engineer",
        "with the role held at the moment of approval frozen on it (ADR-024)",
    )
    expect(str(skill) == str(ANSWER.required_skill), "carrying the skill the reviewer supplied")
    expect(int(minutes) == ANSWER.estimated_minutes, "and the duration the manual did not state")
    expect(
        all(step.get("source_doc") and step.get("page") for step in book_steps),
        "every step carries its own document and page (principle 2)",
    )
    expect(
        [step.get("text_th") for step in book_steps] == THAI,
        "and the approver's Thai for each step, beside the manual's words (ADR-095)",
    )

    print("\n6. nothing here was approved by anything but a person")
    with connect(os.environ["DATABASE_URL"]) as conn:
        logged = conn.execute(
            "SELECT count(*) FROM access_log WHERE action = 'approve_playbook' AND allowed"
        ).fetchone()
    expect(logged == (1,), "the approval is in the access log, with who made it (ADR-024)")

    print(f"\n{SYM}: manual to approved playbook, through the screens")


if __name__ == "__main__":
    main()

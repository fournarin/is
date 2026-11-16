"""Drive the review screen end to end, the way a browser with no JavaScript does.

Slice 10.2's "done when" asks for exactly this: the queue worked from end to end
against a running API - approve, edit and approve, send back, dismiss - with the
step from another document visibly flagged and no clock anywhere on screen. Every
assertion below goes through http://localhost:3000, so what is checked is the
screen and this server's calls to the API, not the API on its own, which
`tests/api/test_the_review_screen.py` covers.

It seeds its own world: two manuals, one of them indexed so the evidence panel
has a page to show, and three proposals - a draft citing two documents, a draft
for another machine model, and a technician's objection.

    export DATABASE_URL=postgresql://$USER@localhost:5432/pdm_web_check
    export STORAGE_DIR=/tmp/pdm-storage PYTHONPATH=.
    uv run alembic upgrade head
    uv run python -m pdm.api &
    cd web && npm run build
    mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/
    API_URL=http://localhost:8000 node .next/standalone/server.js &

    uv run python web/check-the-review-screen.py
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import timedelta

from psycopg import connect

from pdm.contracts import (
    MachineModel,
    PlaybookStep,
    Role,
    SkillId,
    SymptomCode,
    UserId,
)
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore, storage_root
from pdm.playbooks import ProposalOrigin
from pdm.playbooks import repo as playbooks
from pdm.retrieval import repo as index
from pdm.retrieval.domain import Chunk, IndexedPage, PageOutcome

# Where the screens are. The defaults are the ports docker-compose.yml publishes
# on the host, which is what a person running this check by hand has. The
# rehearsal runs it from inside the compose network instead, where the addresses
# are service names (ADR-067).
WEB = os.environ.get("PDM_WEB_URL", "http://localhost:3000")
ENGINEER = UserId("eng-1")
TECHNICIAN = UserId("tech-1")
PASSWORD = "demo-engineer"
R2000 = MachineModel("R-2000iC")
M710 = MachineModel("M-710iC")
SYM = SymptomCode("SYM-014")
OTHER_SYM = SymptomCode("SYM-022")

PAGE_142 = (
    "5.2 Motor replacement\n"
    "Stop the robot using the emergency stop button, then apply lockout per the\n"
    "site procedure. Isolate breaker CP-3 before opening any cover.\n"
)
DRAFTED = (
    "Stop the robot using the emergency stop button",
    "Isolate breaker CP-3 before opening any cover.",
    "Remove the fan cover.",
)

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


# ── the world the screen needs ────────────────────────────────────────────


def seed() -> dict[str, int]:
    url = os.environ["DATABASE_URL"]
    clock = SystemClock()
    now = clock.now()
    auth = Authentication(LocalAccounts(), clock)
    library = DocumentLibrary(FilesystemObjectStore(storage_root()), clock)

    with connect(url) as conn:
        conn.execute(
            "TRUNCATE work_order, finding, job, shift_assignment, technician, playbook, "
            "playbook_proposal, access_log, session, account, chunk, document_page, "
            "document CASCADE"
        )
        for user, name, role in [
            (ENGINEER, "ปราณี", Role.ENGINEER),
            (TECHNICIAN, "สมชาย", Role.TECHNICIAN),
        ]:
            auth.create_account(conn, user=user, display_name=name, role=role, password=PASSWORD)

        manual = library.add(
            conn,
            content=b"%PDF-1.4 the R-2000iC manual" + b" " * 4096,
            filename="r-2000ic.pdf",
            content_type="application/pdf",
            machine_model=R2000,
            title="R-2000iC Maintenance Manual",
            uploaded_by=ENGINEER,
        ).document_id
        bulletin = library.add(
            conn,
            content=b"%PDF-1.4 a safety bulletin" + b" " * 2048,
            filename="safety-bulletin.pdf",
            content_type="application/pdf",
            machine_model=M710,
            title="M-710iC Safety Bulletin",
            uploaded_by=ENGINEER,
        ).document_id

        index.replace_pages(
            conn,
            manual,
            [
                IndexedPage(
                    document_id=manual, page=142, outcome=PageOutcome.TEXT, characters=len(PAGE_142)
                )
            ],
        )
        index.insert_chunks(conn, [Chunk(document_id=manual, page=142, ordinal=0, text=PAGE_142)])

        mixed = playbooks.add_proposal(
            conn,
            symptom_code=SYM,
            machine_model=R2000,
            origin=ProposalOrigin.DRAFTED,
            outcome="repair",
            steps=(
                PlaybookStep(text=DRAFTED[0], source_doc=manual, page=142, confidence=0.9),
                PlaybookStep(text=DRAFTED[1], source_doc=manual, page=142, confidence=0.8),
                # The step the screen has to make stand out: recall-tuned
                # authoring mixes documents, and at page level that looks
                # ordinary (ADR-015).
                PlaybookStep(text=DRAFTED[2], source_doc=bulletin, page=3, confidence=0.4),
            ),
            tools=("torque wrench 5-60 Nm",),
            proposed_skill=SkillId("robot_mechanical"),
            proposed_minutes=45,
            rejected=({"text": "Torque to 42 Nm.", "why": "figure not on the cited page"},),
            reason="3 steps from the R-2000iC manual",
            # Staggered, so the groups have an order worth asserting: the model
            # nobody has looked at longest is named first (ADR-064).
            created_at=now - timedelta(hours=2),
            created_by=None,
        )
        wrong = playbooks.add_proposal(
            conn,
            symptom_code=OTHER_SYM,
            machine_model=R2000,
            origin=ProposalOrigin.DRAFTED,
            outcome="repair",
            steps=(
                PlaybookStep(text="Replace the belt.", source_doc=manual, page=142, confidence=0.6),
            ),
            tools=(),
            proposed_skill=SkillId("robot_mechanical"),
            proposed_minutes=30,
            rejected=(),
            reason="1 step from the R-2000iC manual",
            created_at=now - timedelta(hours=1),
            created_by=None,
        )
        objection = playbooks.add_proposal(
            conn,
            symptom_code=SymptomCode("SYM-031"),
            machine_model=M710,
            origin=ProposalOrigin.TECHNICIAN,
            outcome="objection",
            steps=(),
            tools=(),
            proposed_skill=None,
            proposed_minutes=None,
            rejected=(),
            reason="step 4 sets the tension before the belt is refitted",
            created_at=now,
            created_by=TECHNICIAN,
        )
        conn.commit()

    print(f"seeded: 3 proposals, one page of one manual indexed ({len(PAGE_142)} characters)")
    return {
        "mixed": mixed.proposal_id,
        "wrong": wrong.proposal_id,
        "objection": objection.proposal_id,
    }


# ── driving the screen ────────────────────────────────────────────────────


def hidden_fields(page: str) -> list[tuple[str, str]]:
    fields: list[tuple[str, str]] = []
    for tag in re.findall(r"<input[^>]*type=\"hidden\"[^>]*>", page):
        name = re.search(r'name="([^"]*)"', tag)
        value = re.search(r'value="([^"]*)"', tag)
        if name is not None:
            unescaped = htmllib.unescape(value.group(1)) if value is not None else ""
            fields.append((htmllib.unescape(name.group(1)), unescaped))
    return fields


def form_with(page: str, marker: str) -> list[tuple[str, str]]:
    """The hidden fields of the one form containing `marker`.

    A page with three server actions on it carries three sets of `$ACTION_*`
    fields, and posting them together sends a request naming all three. Scoping
    to one form is what a browser does for free - and the marker has to be the
    button's own text (`>ตีกลับ<`), because the word also appears in the
    approve form's note about what to do instead of deleting a step.
    """
    for form in re.findall(r"<form\b.*?</form>", page, re.DOTALL):
        if marker in form:
            return hidden_fields(form)
    raise AssertionError(f"no form containing {marker!r}")


def multipart(fields: list[tuple[str, str]]) -> tuple[bytes, str]:
    boundary = "----pdm-check-the-review-screen"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def form_with_or_none(page: str, marker: str) -> list[tuple[str, str]] | None:
    try:
        return form_with(page, marker)
    except AssertionError:
        return None


def seed_not_found() -> int:
    """A draft the manuals had nothing for, as the drafter files it (ADR-040)."""
    with connect(os.environ["DATABASE_URL"]) as conn:
        found = playbooks.add_proposal(
            conn,
            symptom_code=SymptomCode("SYM-031"),
            machine_model=M710,
            origin=ProposalOrigin.DRAFTED,
            outcome="not_found",
            steps=(),
            tools=(),
            proposed_skill=None,
            proposed_minutes=None,
            rejected=(),
            reason="ไม่พบเรื่อง SYM-031 ในคู่มือของรุ่น M-710iC",
            created_at=SystemClock().now(),
            created_by=None,
        )
        conn.commit()
    return found.proposal_id


def readable(page: str) -> str:
    """The page with React's text-node separators taken out."""
    # A Thai word is wrapped in <span class="w"> so a line breaks only between words
    # (web/lib/thai.ts); the text a person reads is the words without the wrapper.
    return re.sub(r'<span class="w">(.*?)</span>', r"\1", re.sub(r"<!--.*?-->", "", page))


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
        headers={"content-type": content_type, "origin": WEB},
        method="POST",
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in(user: UserId) -> None:
    page = get("/sign-in")
    submit("/sign-in", hidden_fields(page), [("user", str(user)), ("password", PASSWORD)])


def stored(proposal_id: int) -> dict[str, object]:
    """What a decision wrote, read back from the database rather than a screen."""
    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT status, decision_note, edits, review_seconds, opened_at IS NOT NULL "
            "FROM playbook_proposal WHERE proposal_id = %s",
            (proposal_id,),
        ).fetchone()
    assert row is not None, f"no proposal {proposal_id}"
    return {
        "status": row[0],
        "note": row[1],
        "edits": row[2],
        "review_seconds": row[3],
        "opened": row[4],
    }


def main() -> None:
    ids = seed()
    sign_in(ENGINEER)

    print("\n1. the queue is grouped by machine model")
    queue = readable(get("/review"))
    expect("R-2000iC (2)" in queue, "two proposals waiting for the R-2000iC")
    expect("M-710iC (1)" in queue, "and one for the M-710iC, in its own group")
    expect(
        queue.index("R-2000iC (2)") < queue.index("M-710iC (1)"),
        "the model waiting longest is named first",
    )
    expect("SYM-014" in queue, "the first group's proposals are listed")
    expect("SYM-031" not in queue, "and the other model's are not mixed into it (ADR-064)")
    expect("ถูกกันออก 1 ขั้นตอน" in queue, "a withheld step is reported, not hidden (ADR-037)")

    other = readable(get("/review?model=M-710iC"))
    expect("SYM-031" in other, "the other group is one tap away")
    expect("ช่างแย้ง" in other, "and a technician's objection says who it came from")

    print("\n2. the draft and the page it came from, on one screen")
    detail = readable(get(f"/review/{ids['mixed']}"))
    expect("<mark>" in detail, "the span the step was taken from is highlighted")
    expect(
        "<mark>Stop the robot using the emergency stop button</mark>" in detail,
        "and it is the span, not the whole page",
    )
    expect("R-2000iC Maintenance Manual" in detail, "the manual the page belongs to is named")
    expect("เปิดคู่มือที่หน้า 142" in detail, "with a link that opens it at that page (ADR-019)")
    expect("คนละเอกสาร" in detail, "the step citing another document is flagged (ADR-015)")

    print("\n3. no clock, anywhere")
    # The API does not send one, so there is nothing to render. A visible timer
    # would buy a better number and a worse review (ADR-064).
    expect("review_seconds" not in detail, "the review clock is not in the page")
    expect("opened_at" not in detail, "nor is when it was opened")

    print("\n4. the step from the other manual says which model it is for")
    third = readable(get(f"/review/{ids['mixed']}?step=2"))
    expect("M-710iC Safety Bulletin" in third, "the evidence panel follows the step's citation")
    expect(
        "หน้านี้มาจากคู่มือของรุ่น M-710iC" in third,
        "and a candidate from another machine model is labelled, never mixed in silently",
    )

    print("\n5. edit and approve")
    page = get(f"/review/{ids['mixed']}")
    expect(
        "ช่างกลหุ่นยนต์" in readable(page), "the skill is chosen by its Thai name, not typed as an id"
    )
    corrected = "Isolate breaker CP-3 and apply your personal lock before opening any cover."
    approved = submit(
        f"/review/{ids['mixed']}",
        form_with(page, 'name="required_skill"'),
        # The drafted wording is already on the form as hidden fields, which is
        # how the action tells an approval from an edit; only the textareas are
        # supplied here, exactly as a browser would send them.
        [
            ("step", DRAFTED[0]),
            ("step", corrected),
            ("step", DRAFTED[2]),
            ("required_skill", "robot_mechanical"),
            ("estimated_minutes", "45"),
            ("required_technicians", "1"),
        ],
    )
    expect("คิวรีวิว" in readable(approved), "approving lands back on the queue")
    expect("อนุมัติแล้ว" in readable(approved), "and says what the press did (fourth trial)")

    written = stored(ids["mixed"])
    expect(written["status"] == "applied", "the proposal is applied")
    expect(written["opened"] is True, "opening the detail was recorded")
    expect(
        isinstance(written["review_seconds"], int),
        "and how long the review took was measured without a timer on screen",
    )
    edits = written["edits"]
    assert isinstance(edits, list)
    expect(len(edits) == 1, "one step was rewritten, and only that one is in the diff")
    expect(edits[0]["after"] == corrected, "with the reviewer's wording")

    served = served_playbook()
    expect(served is not None, "and the playbook is now servable")
    assert served is not None
    expect(served[1] == corrected, "the technician will be given the corrected step")
    # The reviewer edits text; the citation is the drafter's and is not theirs
    # to retype (invariant 4, ADR-064).
    expect(served[2] == 142, "carrying the page the drafter cited, not one a person typed")

    print("\n6. sending a draft back asks for another, in the reviewer's words")
    note = "this is the belt procedure, not the motor one - draft from page 96"
    back_page = get(f"/review/{ids['wrong']}")
    returned = submit(f"/review/{ids['wrong']}", form_with(back_page, ">ตีกลับ<"), [("note", note)])
    expect("คิวรีวิว" in readable(returned), "it lands back on the queue")
    expect("ตีกลับแล้ว" in readable(returned), "and says so")
    sent_back = stored(ids["wrong"])
    expect(sent_back["status"] == "sent_back", "the proposal is sent back, not dismissed")
    expect(queued_question() == note, "and the note is the question the next draft is asked")

    print("\n7. an objection is dismissed with a reason, never silently")
    objection_page = get(f"/review/{ids['objection']}")
    blank = submit(
        f"/review/{ids['objection']}", form_with(objection_page, ">ปิดร่างนี้<"), [("note", "   ")]
    )
    expect("เขียนสั้น ๆ" in readable(blank), "a dismissal with no reason is refused (ADR-038)")
    dismissed = submit(
        f"/review/{ids['objection']}",
        form_with(objection_page, ">ปิดร่างนี้<"),
        [("note", "ซ้ำกับใบที่แก้ไปแล้วเมื่อวาน")],
    )
    expect("คิวรีวิว" in readable(dismissed), "with a reason it goes through")
    expect("ปิดร่างนี้แล้ว" in readable(dismissed), "and says the reason was kept")
    expect(stored(ids["objection"])["status"] == "dismissed", "and the row says who and why")

    print("\n8. the queue is empty and says so")
    expect("ไม่มีใบรออนุมัติ" in readable(get("/review")), "nothing waiting, stated plainly")

    print("\n8b. a draft that found nothing offers nothing to approve")
    # 2026-09-29: the approve button was on a "not found" draft. Pressed, the API
    # refused (409, nothing to approve) and the screen said "ใบนี้ถูกตัดสินไปแล้ว",
    # which was untrue - it was still pending.
    empty = seed_not_found()
    page = readable(get(f"/review/{empty}"))
    expect("ไม่มีขั้นตอนให้อนุมัติ" in page, "the screen says there is nothing to approve")
    queue = readable(get("/review"))
    # The third trial: a "not found" listed as awaiting approval.
    expect("คู่มือไม่มีคำตอบ ต้องตัดสินใจ" in queue, "the queue lists it as a gap to decide on")
    expect(
        "รออนุมัติ (" not in queue, "and not under awaiting approval, where nothing else is waiting"
    )
    expect(form_with_or_none(page, ">อนุมัติ<") is None, "and offers no approve button")
    expect(form_with_or_none(page, ">ปิดร่างนี้<") is not None, "but can still be closed with a reason")
    expect(stored(empty)["status"] == "pending", "and it is still pending")

    print("\n8c. a link to a proposal that is not there says so")
    # 2026-09-30: this answered 500 and "เชื่อมต่อระบบไม่ได้ชั่วคราว", as if
    # trying again would help.
    try:
        gone = re.sub(r"<script.*?</script>", "", readable(get("/review/999999")), flags=re.S)
    except urllib.error.HTTPError as error:
        gone = f"HTTP {error.code}"
    expect("ไม่พบร่างนี้" in gone, "/review/999999 says the draft is not there")

    print("\n9. a proposal opened by somebody it is not for says whose it is")
    # A link kept from a chat, or typed: the API refuses it with 403, and the
    # screen said "A server error occurred" in English instead of the refusal
    # every other screen gives (2026-09-29).
    jar.clear()  # signed in, /sign-in redirects home and carries no form to post
    sign_in(TECHNICIAN)
    try:
        refused = readable(get(f"/review/{ids['wrong']}"))
    except urllib.error.HTTPError as error:
        refused = f"HTTP {error.code}"
    expect(
        "หน้านี้เป็นของวิศวกร" in refused,
        f"the technician is told whose page it is, got {refused[:80]!r}",
    )

    print("\nall checks passed")


def served_playbook() -> tuple[str, str, int] | None:
    """(symptom, the second step's text, the page it cites) as runtime would serve it."""
    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT symptom_code, steps FROM playbook WHERE symptom_code = %s", (SYM,)
        ).fetchone()
    if row is None:
        return None
    return str(row[0]), str(row[1][1]["text"]), int(row[1][1]["page"])


def queued_question() -> str | None:
    with connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT payload FROM job WHERE kind = 'draft' ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return None if row is None else str(row[0]["question"])


if __name__ == "__main__":
    main()

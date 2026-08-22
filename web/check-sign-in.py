"""Sign in through the web server the way a phone with no JavaScript does.

`next build`, eslint and tsc all pass on a build whose sign-in page throws the
moment it is submitted - that is not a hypothetical, it is what happened while
this slice was written, and the only thing that found it was running the page.
So this check exists, and it is the evidence behind slice 10.1's claim that
signing in works.

Nothing here talks to the API except to confirm a revocation. Everything else
goes through the web server, which is the claim: the browser reaches the web
server, the web server reaches the API, and the session cookie comes back on
this origin (ADR-058).

Run it against a built app and a running API:

    # a database and a seeded set of accounts
    createdb pdm_web_check
    export DATABASE_URL=postgresql://$USER@localhost:5432/pdm_web_check
    export STORAGE_DIR=/tmp/pdm-storage PYTHONPATH=.
    uv run alembic upgrade head && uv run python scripts/seed_demo.py

    # the API, and the web server as the image runs it
    uv run python -m pdm.api &
    cd web && npm run build
    mkdir -p .next/standalone/.next && cp -R .next/static .next/standalone/.next/
    API_URL=http://localhost:8000 node .next/standalone/server.js &

    python3 web/check-sign-in.py

The passwords below are the ones `scripts/seed_demo.py` prints. They are in the
repository on purpose and are not secrets.
"""

from __future__ import annotations

import html as htmllib
import http.cookiejar
import re
import sys
import urllib.error
import urllib.request

WEB = "http://localhost:3000"
API = "http://localhost:8000"

jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def hidden_fields(page: str) -> list[tuple[str, str]]:
    """The fields Next puts in a form so that it still posts without JavaScript.

    They are how this check drives a server action over plain HTTP, and their
    presence is also the thing that makes the form work on a phone whose bundle
    never arrived - which is the network this is built for.
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
    boundary = "----pdm-check-sign-in"
    body = b""
    for name, value in fields:
        body += (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        ).encode()
    body += f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def post(url: str, fields: list[tuple[str, str]]) -> str:
    body, content_type = multipart(fields)
    request = urllib.request.Request(
        url, data=body, headers={"content-type": content_type}, method="POST"
    )
    with opener.open(request) as response:
        return str(response.read().decode())


def sign_in(user: str, password: str) -> str:
    page = str(opener.open(f"{WEB}/sign-in").read().decode())
    fields = [*hidden_fields(page), ("user", user), ("password", password)]
    return post(f"{WEB}/sign-in", fields)


def api_status_for(token: str) -> int:
    """What the API makes of a token, asked directly rather than through the web."""
    request = urllib.request.Request(f"{API}/sessions/current")
    request.add_header("cookie", f"pdm_session={token}")
    try:
        with urllib.request.urlopen(request) as response:
            return int(response.status)
    except urllib.error.HTTPError as error:
        return int(error.code)


def expect(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        sys.exit(1)


# user, password, display name, role on screen, offered, not offered
PEOPLE = [
    ("tech-1", "demo-technician", "Somchai", "ช่าง", ["งานของคุณ"], ["คิวรีวิว playbook"]),
    (
        "eng-1",
        "demo-engineer",
        "Pranee",
        "วิศวกร",
        ["คิวรีวิว playbook", "ภาพรวมสายการผลิต"],
        ["งานของคุณ"],
    ),
    (
        "sup-1",
        "demo-supervisor",
        "Anan",
        "หัวหน้ากะ",
        ["ภาพรวมสายการผลิต"],
        ["คิวรีวิว playbook", "งานของคุณ"],
    ),
    # An operator has no screen, and ADR-058 says the shell admits that rather
    # than offering a door onto nothing.
    (
        "op-1",
        "demo-operator",
        "Malee",
        "ผู้ดูแลเอกสาร",
        ["ยังไม่มีหน้าจอในระบบ"],
        ["งานของคุณ", "คิวรีวิว playbook", "ภาพรวมสายการผลิต"],
    ),
]


def main() -> None:
    print("1. a signed-out visitor")
    expect(len(list(jar)) == 0, "holds no cookie")

    for user, password, name, role, offered, withheld in PEOPLE:
        jar.clear()
        print(f"\n2. {user} signs in")
        page = sign_in(user, password)
        sessions = [cookie for cookie in jar if cookie.name == "pdm_session"]
        expect(len(sessions) == 1, "the web server set pdm_session on its own origin")
        expect(sessions[0].has_nonstandard_attr("HttpOnly"), "it is HttpOnly")
        expect(name in page, f"the shell greets {name}")
        expect(role in page, f"and names the role: {role}")
        for screen in offered:
            expect(screen in page, f"offered: {screen}")
        for screen in withheld:
            expect(screen not in page, f"not offered: {screen}")

    print("\n3. the wrong password")
    jar.clear()
    page = sign_in("tech-1", "not-the-password")
    expect("ข้อมูลไม่ตรงกับบัญชีใด" in page, "one message, which does not say which half was wrong")
    expect([c for c in jar if c.name == "pdm_session"] == [], "and no session was set")

    print("\n4. signing out ends the session, not only the cookie")
    jar.clear()
    sign_in("tech-1", "demo-technician")
    token = next(cookie.value or "" for cookie in jar if cookie.name == "pdm_session")
    shell = str(opener.open(f"{WEB}/").read().decode())
    expect("Somchai" in shell, "the shell is reachable while signed in")
    expect(api_status_for(token) == 200, "the API accepts the token the browser holds")

    post(f"{WEB}/", hidden_fields(shell))
    expect([c for c in jar if c.name == "pdm_session" and c.value] == [], "the cookie is cleared")
    # ADR-036 point 2: the row is what makes revocation immediate, so the token
    # has to be dead at the API even for somebody who kept a copy of it.
    expect(api_status_for(token) == 401, "and the API now refuses that same token")

    print("\nall checks passed")


if __name__ == "__main__":
    main()

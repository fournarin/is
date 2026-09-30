"""What a person sees when the web server answers and the API does not.

On 2026-09-29 the API container was stopped under a running stack. Every screen
became Next's English "A server error occurred" or Chrome's "HTTP ERROR 500",
the sign-in page had no form on it, and a technician's close came back as
"ระบบตอบกลับ 500". It was treated as a refusal and thrown away, when it was a
network failure the offline queue exists for.

This check starts its own copy of the built web server with `API_URL` pointing
at a port nothing listens on, so it needs no stack and stops nothing:

    cd web && npm run build && mkdir -p .next/standalone/.next \\
        && cp -R .next/static .next/standalone/.next/
    python3 web/check-when-the-api-is-down.py
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SERVER = Path(__file__).parent / ".next" / "standalone" / "server.js"
failures: list[str] = []


def expect(condition: bool, message: str) -> None:
    print(f"  {'ok  ' if condition else 'FAIL'} {message}")
    if not condition:
        failures.append(message)


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def request(
    url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None
) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url, data=data, headers=headers or {}), timeout=30
        ) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


def main() -> None:
    web_port, dead_port = free_port(), free_port()
    server = subprocess.Popen(
        ["node", str(SERVER)],
        env={
            **os.environ,
            "PORT": str(web_port),
            "HOSTNAME": "127.0.0.1",
            "API_URL": f"http://127.0.0.1:{dead_port}",
        },
        cwd=SERVER.parent,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    web = f"http://127.0.0.1:{web_port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{web}/favicon.ico", timeout=1)
                break
            except urllib.error.HTTPError:
                break
            except OSError:
                time.sleep(0.2)

        print("1. the sign-in page still has its form, and says the system is unreachable")
        status, page = request(f"{web}/sign-in")
        expect('name="password"' in page, f"the form is there (HTTP {status})")
        expect("เชื่อมต่อระบบไม่ได้" in page, "and the page says the system cannot be reached")

        print("2. a screen behind sign-in is Thai with a way back, not Next's English page")
        status, page = request(f"{web}/work", headers={"cookie": "pdm_session=anything"})
        expect("A server error occurred" not in page, f"no English error page (HTTP {status})")
        expect("เชื่อมต่อระบบไม่ได้" in page, "it says the system cannot be reached, in Thai")
        expect(re.search(r'href="/"', page) is not None, "with a link back to the start")

        print("3. a close sent now is a network failure, not a refusal")
        status, body = request(
            f"{web}/work/WO-000001/close/send",
            data=json.dumps({"outcome": "fixed"}).encode(),
            headers={"content-type": "application/json", "cookie": "pdm_session=anything"},
        )
        expect(status == 503, f"the route answers 503, which the phone queues (got {status})")
        expect("เชื่อมต่อระบบไม่ได้" in body, "and says why")

        print("4. the shift lead's buttons land on a page that says so, not Chrome's HTTP 500")
        for path, form in [
            ("/overview/confirm", b"ref=WO-000001"),
            ("/overview/reject", b"ref=WO-000001&reason=x"),
            ("/overview/release", b"ref=WO-000001"),
            ("/overview/draft", b"symptom_code=SYM-014&machine_model=R-2000iC&question=x"),
        ]:
            status, page = request(
                f"{web}{path}",
                data=form,
                headers={
                    "content-type": "application/x-www-form-urlencoded",
                    "cookie": "pdm_session=anything",
                    "origin": web,
                },
            )
            expect("เชื่อมต่อระบบไม่ได้" in page, f"{path} ends on the Thai page (HTTP {status})")

        print("5. a manual page asked for now says so too")
        status, page = request(f"{web}/manual/abc", headers={"cookie": "pdm_session=anything"})
        expect("เชื่อมต่อระบบไม่ได้" in page, f"the manual link (HTTP {status})")
    finally:
        server.terminate()
        server.wait(timeout=10)

    if failures:
        print(f"\n{len(failures)} failed")
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()

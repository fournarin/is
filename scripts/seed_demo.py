"""Create the demo accounts and load the synthetic corpus (ADR-024, ADR-033).

    DATABASE_URL=... STORAGE_DIR=... uv run python scripts/seed_demo.py

ADR-024 forbids a mode with authentication turned off, "not even for a demo",
so a demo needs real accounts with real roles and real passwords. That makes
creating them an ordinary operation rather than a fixture, and this script the
thing an operator reruns on the plant's machine.

Idempotent: an account that exists is left alone, and a manual that is already
stored is already stored - content addressing means re-adding the same bytes is
the same document (ADR-019).

The passwords here are obviously not secrets. They exist so that a demo has
somebody to sign in as, and the script prints them precisely so nobody assumes
otherwise.
"""

from __future__ import annotations

import os
import sys

from psycopg import connect

from fixtures.corpus import CORPUS
from pdm.contracts import Role, UserId
from pdm.platform.auth import repo as auth_repo
from pdm.platform.auth.service import Authentication, LocalAccounts
from pdm.platform.clock import SystemClock
from pdm.platform.documents import DocumentLibrary
from pdm.platform.objects import FilesystemObjectStore, storage_root

PEOPLE = [
    (UserId("tech-1"), "Somchai (technician)", Role.TECHNICIAN, "demo-technician"),
    (UserId("eng-1"), "Pranee (engineer)", Role.ENGINEER, "demo-engineer"),
    (UserId("sup-1"), "Anan (supervisor)", Role.SUPERVISOR, "demo-supervisor"),
    (UserId("op-1"), "Malee (operator)", Role.OPERATOR, "demo-operator"),
]


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1

    clock = SystemClock()
    auth = Authentication(LocalAccounts(), clock)
    library = DocumentLibrary(FilesystemObjectStore(storage_root()), clock)

    with connect(url) as conn:
        print("accounts:")
        for user, name, role, password in PEOPLE:
            if auth_repo.account(conn, user) is not None:
                print(f"  {user:8} {role.value:11} already there")
                continue
            auth.create_account(conn, user=user, display_name=name, role=role, password=password)
            print(f"  {user:8} {role.value:11} password {password}")

        print("manuals:")
        for document in CORPUS.documents:
            row = library.add(
                conn,
                content=document.path.read_bytes(),
                filename=document.filename,
                content_type="application/pdf",
                machine_model=document.machine_model,
                title=document.title,
                uploaded_by=UserId("op-1"),
                edition=document.edition,
            )
            print(f"  {document.filename}  {row.document_id[:12]}...")

        conn.commit()

    print("\nThese passwords are in the repository. They are for a demo on a")
    print("machine inside the plant network and are not secrets.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

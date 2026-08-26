"""Create the demo accounts, load the synthetic corpus, and queue it for indexing.

ADR-024, ADR-033, ADR-079.

    DATABASE_URL=... STORAGE_DIR=... uv run python scripts/seed_demo.py

ADR-024 forbids a mode with authentication turned off, "not even for a demo",
so a demo needs real accounts with real roles and real passwords. That makes
creating them an ordinary operation rather than a fixture, and this script the
thing an operator reruns on the plant's machine.

Idempotent: an account that exists is left alone, and a manual that is already
stored is already stored - content addressing means re-adding the same bytes is
the same document (ADR-019). The ingest job is enqueued either way, for the
reason the upload endpoint enqueues one unconditionally: re-indexing replaces a
document's pages and chunks rather than adding to them, and deciding here
whether the index is current would be a second opinion about a question
`document_page` already answers.

**The manuals are queued for ingest, not merely stored.** A document nothing has
indexed is a document retrieval cannot find, so a stack seeded this way had a
library with four manuals in it, one chunk, an empty review queue and no
playbook anywhere - which reads, to somebody seeing the screens for the first
time, as a content layer that was never built.

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
from pdm.platform.jobs import JobClass, JobKind
from pdm.platform.jobs import repo as jobs
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
        created: list[str] = ["accounts:"]
        for user, name, role, password in PEOPLE:
            if auth_repo.account(conn, user) is not None:
                created.append(f"  {user:8} {role.value:11} already there")
                continue
            auth.create_account(conn, user=user, display_name=name, role=role, password=password)
            # Collected rather than printed: a failure later in this script rolls
            # the transaction back, and an operator who has already been told a
            # password exists has no way to know it does not.
            created.append(f"  {user:8} {role.value:11} password {password}")

        created.append("manuals:")
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
            # The repository rather than `JobQueue`, which exists to claim and
            # finish jobs and would need timings from `policy.yaml` to insert
            # one. What a seed does is the insert (ADR-017: the job and the row
            # it refers to commit together, which they do here - one
            # transaction, below).
            job = jobs.enqueue(
                conn,
                job_class=JobClass.AUTHORING,
                kind=JobKind.INGEST.value,
                payload={"document_id": row.document_id},
                now=clock.now(),
            )
            created.append(f"  {document.filename}  {row.document_id[:12]}...  ingest job {job.id}")

        conn.commit()

    # After the commit, never before. Everything above is one transaction, so a
    # failure halfway through leaves nothing - and an operator who was already
    # told an account exists has no way to discover that it does not.
    for line in created:
        print(line)

    print("\nThese passwords are in the repository. They are for a demo on a")
    print("machine inside the plant network and are not secrets.")
    print("\nThe manuals are queued for indexing. worker-authoring has to be running")
    print("for the review queue to have anything in it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

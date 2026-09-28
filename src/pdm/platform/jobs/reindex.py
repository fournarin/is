"""Queue every active manual for indexing again (ADR-101).

    docker compose exec api python -m pdm.platform.jobs.reindex

After a restore, PostgreSQL has the documents and their chunks while Qdrant is
empty, so the dense half of retrieval finds nothing. Ingesting replaces
whatever a document had (ADR-035), so queueing all of them again is safe to run
more than once. `worker-authoring` does the work; this only queues it.
"""

from __future__ import annotations

import os
import sys

from psycopg import connect

from pdm.platform.clock import SystemClock
from pdm.platform.jobs import repo as jobs
from pdm.platform.jobs.domain import JobClass, JobKind


def main() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set")
        return 1
    now = SystemClock().now()
    with connect(url) as conn:
        ids = [
            row[0]
            for row in conn.execute(
                "SELECT document_id FROM document WHERE status = 'active' ORDER BY uploaded_at"
            ).fetchall()
        ]
        for document_id in ids:
            jobs.enqueue(
                conn,
                job_class=JobClass.AUTHORING,
                kind=JobKind.INGEST.value,
                payload={"document_id": document_id},
                now=now,
            )
        conn.commit()
    print(f"queued {len(ids)} document(s) for indexing; worker-authoring will pick them up")
    return 0


if __name__ == "__main__":
    sys.exit(main())

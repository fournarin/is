"""The job queue: a table in Postgres, not a separate broker (ADR-017).

The reason is traceability rather than one fewer dependency. An authoring job
produces a draft playbook row; if the job state lived in Redis and the result in
Postgres there would be two sources of truth, and dying between the two writes
would leave either a playbook with no job or a job claiming success with no
playbook. In one database both commit together and that whole class of bug is
gone.

Split by job_class so that a twenty-minute manual ingest cannot stall the
dispatch tick (ADR-026, invariant 12).
"""

from pdm.platform.jobs.domain import ClassTiming, Job, JobClass, JobKind, JobStatus
from pdm.platform.jobs.service import JobQueue

__all__ = ["ClassTiming", "Job", "JobClass", "JobKind", "JobQueue", "JobStatus"]

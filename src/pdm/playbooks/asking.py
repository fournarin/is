"""Asking the authoring worker for a draft, from either door (ADR-040, ADR-121).

Two callers ask. An engineer presses a button on the gaps screen, and since
ADR-121 the trigger loop asks by itself the first time a symptom with no
approved steps gets a ticket. Both go through `ask` so that the two rules about
asking twice - a job already coming answers the second ask, and so does a draft
already waiting for review - hold whichever door was used.

No I/O beyond the caller's connection, and nothing here reaches the model: the
job is a row, and only worker-authoring claims it (ADR-003, ADR-026).
"""

from __future__ import annotations

from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.contracts import MachineModel, SymptomCode
from pdm.platform.jobs import JobKind, JobQueue
from pdm.playbooks import repo


class Asked(BaseModel):
    """What became of one ask. Exactly one of the three is set, or none when the
    loop's ask was declined because the pair has been drafted before."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    job: int | None = None
    queued_already: bool = False
    awaiting_review: int | None = None


def ask(
    conn: Connection[Any],
    jobs: JobQueue,
    *,
    symptom_code: SymptomCode,
    machine_model: MachineModel,
    question: str,
    symptom: str,
    only_if_never_asked: bool = False,
) -> Asked:
    """Queue a drafting job for one pair, unless the answer is already coming.

    `question` is what retrieval is asked. `symptom` is the rule's own
    description of the fault, and drafting also requires the pages it uses to
    be about that (ADR-121): a question typed as "85 องศา" for a safety-interlock
    symptom found the belt-motor page and drafted its steps.

    `only_if_never_asked` is the loop's ask. It declines where anything has ever
    been filed or queued for the pair: a second draft of the same symptom is an
    engineer's call, after reading the first.
    """
    pair: dict[str, object] = {"symptom_code": symptom_code, "machine_model": machine_model}
    already = jobs.pending(conn, kind=JobKind.DRAFT, payload=pair)
    if already is not None:
        return Asked(job=already.id, queued_already=True)
    waiting = repo.awaiting_review(conn, symptom_code=symptom_code, machine_model=machine_model)
    if waiting is not None:
        return Asked(awaiting_review=waiting)
    if only_if_never_asked and (
        repo.ever_proposed(conn, symptom_code=symptom_code, machine_model=machine_model)
        or jobs.ever(conn, kind=JobKind.DRAFT, payload=pair)
    ):
        return Asked()
    job = jobs.enqueue(
        conn,
        kind=JobKind.DRAFT,
        payload={**pair, "question": question, "symptom": symptom},
    )
    return Asked(job=job.id)

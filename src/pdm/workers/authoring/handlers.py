"""The two things the authoring worker knows how to do (ADR-026, ADR-039).

Each handler takes the job's connection and does all of its work on it, so the
result and the job that produced it commit together (ADR-017). Neither finishes
nor fails its own job: the loop owns that, because a handler that could would be
a handler that could commit half of one.

Payloads are validated here rather than trusted. A job row is written by another
process and read minutes later; a handler that indexed `payload["document_id"]`
directly would raise `KeyError` and record "KeyError: 'document_id'" as the
reason a manual was never ingested.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from pdm.authoring.service import Drafting, Ingest
from pdm.contracts import DocumentId, MachineModel, SymptomCode
from pdm.platform.clock import Clock
from pdm.platform.jobs import Job

log = logging.getLogger(__name__)

_STRICT = ConfigDict(frozen=True, extra="forbid")


class BadPayload(Exception):
    """The job says what to do and not enough about what to do it to."""


class IngestPayload(BaseModel):
    model_config = _STRICT

    document_id: DocumentId = Field(pattern="^[0-9a-f]{64}$")


class DraftPayload(BaseModel):
    """What a drafting job carries (ADR-039 section 6).

    The question is on the job rather than derived from the symptom code, because
    a drafting result is reproducible only if what produced it was recorded. A
    handler that built its own query would quietly produce different drafts as
    that derivation changed.
    """

    model_config = _STRICT

    symptom_code: SymptomCode
    machine_model: MachineModel
    question: str = Field(min_length=1)

    @field_validator("question")
    @classmethod
    def _not_only_whitespace(cls, value: str) -> str:
        """Checked here as well as at the endpoint: a job row can be written by a
        script, and this is the last place before a GPU is asked to look at
        nothing (ADR-040 section 4)."""
        if not value.strip():
            raise ValueError("a drafting question cannot be only whitespace")
        return value.strip()


def _payload(model: type[BaseModel], job: Job) -> Any:
    try:
        return model.model_validate(job.payload)
    except ValidationError as error:
        raise BadPayload(f"job {job.id} ({job.kind}): {error}") from error


def ingest_handler(ingest: Ingest) -> Any:
    """Index a manual that is already in the library."""

    def handle(conn: Connection[Any], job: Job) -> None:
        payload: IngestPayload = _payload(IngestPayload, job)
        report = ingest.run(conn, payload.document_id)
        # Coverage in the log because it is the number that qualifies every
        # retrieval figure measured on this manual (ADR-034), and the person who
        # uploaded a scan needs to learn it produced nothing without reading a
        # table.
        log.info(
            "ingested %s: %s of %s pages readable, %s chunks%s",
            payload.document_id[:12],
            report.pages_with_text,
            report.pages,
            report.chunks,
            f", OCR needed on {list(report.pages_needing_ocr)}" if report.pages_needing_ocr else "",
        )

    return handle


def draft_handler(drafting: Drafting, clock: Clock) -> Any:
    """Draft a playbook for one symptom and put it in the review queue.

    Both halves in one transaction. A draft produced and not filed is work the
    GPU did that nobody will ever see, and a queue entry with no draft behind it
    is a reviewer opening an empty page - which is the pairing ADR-017 chose the
    database queue to make impossible.
    """

    def handle(conn: Connection[Any], job: Job) -> None:
        payload: DraftPayload = _payload(DraftPayload, job)
        result = drafting.run(
            conn,
            symptom_code=payload.symptom_code,
            machine_model=payload.machine_model,
            question=payload.question,
        )
        proposal = drafting.file(conn, result, now=clock.now())
        log.info(
            "drafted %s for %s: %s (proposal %s) - %s",
            payload.symptom_code,
            payload.machine_model,
            result.outcome.value,
            proposal.proposal_id,
            result.reason,
        )

    return handle

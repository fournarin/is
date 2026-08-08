"""What the system knows about a stored manual, with no I/O (ADR-030 layering).

The blob and the row are separate things on purpose. The blob is immutable and
permanent; the row carries everything that can change about it - whether it is
still the edition in force, who put it there, when it was withdrawn. ADR-019
turns "delete" into a change here rather than a file operation, because a PDF
that a `playbook_snapshot` still cites is evidence, and removing it destroys an
audit trail without saying so.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pdm.contracts import DocumentId, MachineModel, UserId

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class DocumentStatus(StrEnum):
    """Two states, and neither of them removes anything.

    `withdrawn` means the operator has taken this edition out of service: it is
    no longer indexed and no new playbook is drafted from it, while the file
    stays exactly where it was. Every playbook derived from it goes to
    `needs_review` and is still served with a warning until re-approved
    (ADR-018) - so the pages have to remain readable for as long as any of those
    playbooks or the work orders quoting them exist.
    """

    ACTIVE = "active"
    WITHDRAWN = "withdrawn"


class Document(BaseModel):
    """One manual in the library.

    `document_id` is the sha256 of the file's contents, so it is both the
    identity and the location on disk (ADR-019). Two uploads of the same bytes
    are the same document however they were named.
    """

    model_config = _FROZEN

    document_id: DocumentId
    # What it was called when it arrived. Display only, and deliberately not an
    # identifier: operators routinely upload a new edition under the old name,
    # which is the collision ADR-019 chose content addressing to avoid.
    filename: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)

    machine_model: MachineModel = Field(min_length=1)
    title: str = Field(min_length=1)
    # As printed on the document. Free text because "Rev C", "3rd edition" and
    # "2024-06" are all things a manual says about itself, and normalising them
    # would mean discarding what it actually says.
    edition: str | None = None

    status: DocumentStatus = DocumentStatus.ACTIVE
    uploaded_by: UserId = Field(min_length=1)
    uploaded_at: datetime
    withdrawn_at: datetime | None = None

    @model_validator(mode="after")
    def _withdrawal_is_dated(self) -> Document:
        """Both directions. A withdrawn document with no date cannot answer "was
        this edition in force when that work order was issued", which is the
        question the whole audit trail exists for; an active one carrying a
        withdrawal date is a row that two pieces of code will read differently."""
        if self.status is DocumentStatus.WITHDRAWN and self.withdrawn_at is None:
            raise ValueError("a withdrawn document must record when it was withdrawn")
        if self.status is DocumentStatus.ACTIVE and self.withdrawn_at is not None:
            raise ValueError("an active document cannot carry a withdrawal date")
        return self

    @property
    def is_servable(self) -> bool:
        """Whether new work may be drafted from this edition.

        Not whether it may be read: a withdrawn manual is still fetched by
        anybody tracing a citation on a closed work order.
        """
        return self.status is DocumentStatus.ACTIVE

"""The manual library: one row per stored document, one blob per row (ADR-019).

Kept in `platform/` beside the object store because it is infrastructure - the
authoring pipeline, the review screen and any citation on a closed work order
all read through it, and none of them owns it.

Nothing here deletes a file. Withdrawing an edition is a status change, because
a PDF that a `playbook_snapshot` still cites is evidence (ADR-018, ADR-019).
"""

from pdm.platform.documents.domain import Document, DocumentStatus
from pdm.platform.documents.service import DocumentLibrary

__all__ = ["Document", "DocumentLibrary", "DocumentStatus"]

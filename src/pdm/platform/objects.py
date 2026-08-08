"""Content-addressed blob storage on one filesystem volume (ADR-019).

A file's name is the sha256 of its contents, which is also its `DocumentId`.
That solves the problem ADR-018 created: operators upload a new edition under
the old filename, and stored by name the old file would be overwritten, leaving
every `playbook_snapshot` citing "page 47" pointing at unrelated content - an
audit trail that is wrong in silence, which is worse than none.

Three properties this module exists to guarantee:

  it never deletes a stored blob   ADR-019 says the application contains no such
                                   code, because a job that removes a PDF a
                                   snapshot still cites destroys evidence
                                   invisibly. "Delete" is a change to
                                   documents.status. Enforced by
                                   scripts/check_no_blob_deletion.py
  writes are atomic                a blob is written to a temporary file, hashed
                                   as it goes, and renamed into place. An
                                   interrupted upload leaves a temp file, never
                                   a blob whose contents do not match its name
  reads can be partial             citation to a page number is the system's
                                   central interaction (ADR-019), so the API has
                                   to answer Range requests without loading a
                                   fifty-megabyte scan into memory to serve two
                                   pages of it

Nothing here authorises anything. ADR-019 requires every read to pass through
the API so it goes through RBAC and the access log; that check belongs at the
endpoint, and this module is what the endpoint reads through.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import BinaryIO, Protocol, runtime_checkable

from pdm.contracts import DocumentId

STORAGE_ENV = "STORAGE_DIR"

# Read in 1 MiB blocks. Large enough that hashing a scanned manual is not
# dominated by syscalls, small enough that concurrent uploads do not each hold
# a large buffer.
_CHUNK = 1024 * 1024

# Stored blobs are read-only. It does not stop a determined `chmod`, but it
# turns "the application must never modify or delete a blob" from a rule
# somebody has to remember into an error somebody has to explain.
_READ_ONLY = 0o444


class ObjectNotFound(KeyError):
    """No blob with that id. Raised rather than returning None, because every
    caller has a document row that says the blob should be there, so its absence
    is corruption rather than an ordinary miss."""


@runtime_checkable
class ObjectStore(Protocol):
    """put / get / exists, as decided in ADR-019, plus the pair that streaming
    needs.

    `open` and `size` are not a widening of the decision: ADR-019 requires
    `Range` support at the API layer and notes it has to be implemented there
    whatever sits behind this interface. Returning whole files only would make
    that impossible to do without reading each one into memory first.
    """

    def put(self, content: bytes) -> DocumentId: ...

    def put_stream(self, source: BinaryIO) -> DocumentId: ...

    def get(self, document_id: DocumentId) -> bytes: ...

    def open(self, document_id: DocumentId) -> AbstractContextManager[BinaryIO]: ...

    def size(self, document_id: DocumentId) -> int: ...

    def exists(self, document_id: DocumentId) -> bool: ...


class FilesystemObjectStore:
    """One directory tree, one volume. The only implementation for now.

    ADR-019 chose this over MinIO after subtracting the two advantages that do
    not apply: presigned URLs are refused on NDA grounds regardless of backend,
    and once every read is served through the API, range support has to be built
    at the API layer either way.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._incoming = root / "incoming"
        self._incoming.mkdir(parents=True, exist_ok=True)

    # ── layout ─────────────────────────────────────────────────────────────

    def path_for(self, document_id: DocumentId) -> Path:
        """`root/ab/cd/abcd...`.

        Two levels of prefix because a hex-named flat directory degrades on
        several filesystems once it holds tens of thousands of entries, and
        because `ls` on a flat store is unusable for a person trying to work out
        what is on disk after an incident.
        """
        return self.root / document_id[:2] / document_id[2:4] / document_id

    # ── writing ────────────────────────────────────────────────────────────

    def put(self, content: bytes) -> DocumentId:
        from io import BytesIO

        return self.put_stream(BytesIO(content))

    def put_stream(self, source: BinaryIO) -> DocumentId:
        """Write, hash while writing, then rename into place.

        The id is not known until the last byte has been read, which is why the
        blob cannot be written to its final path directly. Hashing the stream as
        it is copied - rather than reading the file back afterwards - is also
        what makes it impossible to store content under an id that is not its
        hash.

        Idempotent: the same bytes have the same id, so a second upload of an
        existing blob discards its temporary file and returns. It deliberately
        does not rewrite the target, which would truncate a file another request
        is streaming.
        """
        digest = hashlib.sha256()
        temporary = self._incoming / f"{os.getpid()}-{id(source):x}.part"

        try:
            with temporary.open("wb") as sink:
                while chunk := source.read(_CHUNK):
                    digest.update(chunk)
                    sink.write(chunk)
                sink.flush()
                # Force the contents out before the rename. Without it a crash
                # can leave the directory entry pointing at a file that has not
                # been written, which is a blob whose name lies about its
                # contents - the one state this module must never produce.
                os.fsync(sink.fileno())

            document_id = DocumentId(digest.hexdigest())
            target = self.path_for(document_id)
            if target.exists():
                return document_id

            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary, target)
            target.chmod(_READ_ONLY)
            return document_id
        finally:
            # Only ever the temporary file, never a stored blob. After a
            # successful rename there is nothing at this path to remove.
            temporary.unlink(missing_ok=True)  # allow: temp-file

    # ── reading ────────────────────────────────────────────────────────────

    def get(self, document_id: DocumentId) -> bytes:
        """The whole blob. For anything a person will scroll through, use
        `open`: this reads the entire file into memory."""
        with self.open(document_id) as handle:
            return handle.read()

    @contextmanager
    def open(self, document_id: DocumentId) -> Iterator[BinaryIO]:
        """A readable stream, for serving a byte range without loading the rest."""
        path = self.path_for(document_id)
        try:
            handle = path.open("rb")
        except FileNotFoundError as error:
            raise ObjectNotFound(document_id) from error
        try:
            yield handle
        finally:
            handle.close()

    def size(self, document_id: DocumentId) -> int:
        path = self.path_for(document_id)
        try:
            return path.stat().st_size
        except FileNotFoundError as error:
            raise ObjectNotFound(document_id) from error

    def exists(self, document_id: DocumentId) -> bool:
        return self.path_for(document_id).is_file()


def storage_root() -> Path:
    """Where blobs live, from the environment. No default, on purpose.

    The same reasoning as the database DSN (ADR-031): a default would let the
    service start against the wrong directory and look healthy while writing
    documents somewhere nobody backs up. In the container this is the mounted
    volume; on a workstation it is whatever the developer sets.
    """
    value = os.environ.get(STORAGE_ENV)
    if not value:
        raise RuntimeError(
            f"{STORAGE_ENV} is not set. There is no default: documents outlive the "
            f"playbooks derived from them (ADR-018), so writing them to a guessed "
            f"directory loses the evidence a closed work order relies on."
        )
    return Path(value)

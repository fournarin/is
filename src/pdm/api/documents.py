"""Serving a manual page (ADR-019).

The four things ADR-019 said would have to be built here because MinIO was not
chosen, all of them in this file: the `Range` header, content type and
disposition, an authorisation check before a byte is served, and every read in
the access log.

There are no presigned URLs and there will not be. ADR-019 refused them on NDA
grounds: whoever holds the URL can read until it expires, with no further
authorisation and no line in the log, and shortening its lifetime only admits
that the hole is there.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from pdm.api.deps import SESSION_COOKIE, Db, Jobs, requires
from pdm.contracts import DocumentId, MachineModel, Role
from pdm.platform.auth.domain import Account, NotAuthenticated, NotAuthorised
from pdm.platform.auth.service import Authentication
from pdm.platform.documents import Document, DocumentLibrary, DocumentStatus
from pdm.platform.documents.repo import DocumentModelConflict, DocumentRegistrationConflict
from pdm.platform.jobs import JobKind
from pdm.platform.objects import READ_CHUNK_BYTES, ObjectNotFound
from pdm.retrieval import repo as index

router = APIRouter(tags=["documents"])

# "bytes=0-1023", "bytes=1024-", "bytes=-500". One range only: a viewer asking
# for several at once needs a multipart response, and no client this system has
# does that.
_RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")

# Anybody signed in may read a manual. Reading is the job - a technician
# following a citation, an engineer checking a drafted step - and the control
# ADR-019 asks for is that it goes through RBAC and into the log, not that it is
# rare.
_MAY_READ = (Role.TECHNICIAN, Role.ENGINEER, Role.SUPERVISOR, Role.OPERATOR)

# What may be stored, and the bytes a file of that type has to begin with.
#
# The type is **not** taken from the upload. A browser sends whatever the client
# claims, and this endpoint serves documents inline from the same origin as the
# session cookie: an operator who uploaded text/html would have stored a page
# that runs with the reader's session. Manuals are PDFs (ADR-019, ADR-033), so
# the list is one entry, and widening it is a deliberate edit here rather than
# something a client decides.
#
# Photographs from the shop floor are in the design (design.md 8) and are not
# this endpoint: they attach to a work order and will bring their own types with
# their own slice.
_ALLOWED_TYPES = {"application/pdf": b"%PDF-"}

# Enough to find the signature even when something precedes it. A byte-order
# mark or a stray newline before %PDF- is malformed and every reader opens it
# anyway, and refusing those leaves an operator holding a manual with no way to
# get it in. The signature is looked for in this window rather than demanded at
# offset zero - deliberately lenient, because what actually protects a reader is
# that the *served* type comes from the allow-list and never from the file.
_MAGIC_WINDOW = 1024

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]")

# Defence in depth for the case this file cannot see: a row written before the
# allow-list existed, or by some later path that skips it. nosniff stops a
# browser deciding for itself that a PDF is really HTML, and a policy of
# default-src 'none' means nothing in a document response can fetch or execute.
#
# Deliberately not `sandbox`: it can disable the browser's built-in PDF viewer,
# and opening a cited page beside a drafted step is the one interaction this
# endpoint exists for (ADR-019).
_HARDENING = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'",
}


def _checked_media_type(declared: str | None, head: bytes) -> str:
    """The type this file is allowed to be stored as, or 415.

    Both halves are needed. The declared type alone is the client's word for it;
    the magic bytes alone would let a PDF be stored under a type that makes a
    browser treat it as something else.
    """
    normalised = (declared or "").split(";")[0].strip().lower()
    expected = _ALLOWED_TYPES.get(normalised)
    if expected is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"{normalised or 'an unnamed type'} is not a type this library stores; "
            f"expected one of {sorted(_ALLOWED_TYPES)}",
        )
    if expected not in head:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"the file does not begin like {normalised}",
        )
    return normalised


def _serving_type(document: Document) -> tuple[str, str]:
    """(media type, disposition) for a stored document.

    Never the stored string unchecked. Anything not on the allow-list is served
    as a download of unknown bytes rather than as something a browser will try to
    render, which is what makes a row that predates the check harmless.
    """
    stored = document.content_type.split(";")[0].strip().lower()
    if stored in _ALLOWED_TYPES:
        # inline, not attachment: the point of this endpoint is a reviewer
        # opening page 47 beside a drafted step, not a download.
        return stored, "inline"
    return "application/octet-stream", "attachment"


def _disposition(document: Document, kind: str) -> str:
    """A Content-Disposition a filename cannot break out of.

    The uploader chooses the filename. Interpolated raw, a quote in it ends the
    quoted string early and the rest of the name becomes header parameters. The
    ASCII form is sanitised for old clients and the real name goes in the RFC
    5987 field, percent-encoded - which is also what lets a Thai filename
    survive.
    """
    ascii_name = _SAFE_FILENAME.sub("_", document.filename) or "document"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(document.filename)}"


def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """(first, last) inclusive as HTTP counts them, or None to ignore the header.

    Two different answers, which the first version of this conflated into one.
    RFC 9110 14.2 says a `Range` that cannot be parsed - a unit this server does
    not know, several ranges at once - **must be ignored**, and the whole
    representation returned. Only a range that parses and falls outside the file
    is 416. Answering 416 to a multi-range request left a viewer showing nothing
    where it should have shown the whole document.
    """
    match = _RANGE.match(header.strip())
    if not match:
        return None

    start_text, end_text = match.groups()
    if start_text:
        first = int(start_text)
        last = int(end_text) if end_text else size - 1
    elif end_text:
        # A suffix range: the last N bytes.
        first = max(0, size - int(end_text))
        last = size - 1
    else:
        return None

    if first > last or first >= size:
        raise ValueError(header)
    return first, min(last, size - 1)


def _stream(library: DocumentLibrary, document: Document, first: int, last: int) -> Iterator[bytes]:
    remaining = last - first + 1
    with library.open(document) as handle:
        handle.seek(first)
        while remaining > 0:
            block = handle.read(min(READ_CHUNK_BYTES, remaining))
            if not block:
                return
            remaining -= len(block)
            yield block


@router.get("/documents/{document_id}")
def fetch(
    request: Request,
    document_id: DocumentId,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
    range_header: str | None = Header(default=None, alias="Range"),
) -> Response:
    """The bytes of one manual, whole or by range.

    Withdrawn editions are served. A closed work order cites a page in the
    edition that was in force when it was issued, and refusing to open it would
    make the citation unverifiable - which is the audit trail ADR-018 moved to
    the work order specifically to preserve.

    **This route manages its own connection instead of taking the `Db`
    dependency, and that is the whole point of how it is written.** FastAPI
    unwinds a request's dependencies after the response has finished sending, so
    a `StreamingResponse` built on a dependency-held connection keeps that
    connection checked out - and open in a transaction - for the entire
    download. The pool holds four. Four technicians opening a fifty-megabyte
    scanned manual would have starved login and every other route until the pool
    timed out, on the plant's own hardware, with nothing in the logs but
    timeouts.

    Everything that needs the database happens inside the block below and the
    connection is back in the pool before a byte is sent. The stream itself
    needs no database at all: it reads the object store.
    """
    auth: Authentication = request.app.state.authentication
    library: DocumentLibrary = request.app.state.library
    pool = request.app.state.pool

    with pool.connection() as conn:
        try:
            try:
                account = auth.account_for(conn, session)
            except NotAuthenticated as error:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(error)) from error

            try:
                auth.authorise(
                    conn, account, *_MAY_READ, action="read_document", subject=document_id
                )
            except NotAuthorised as error:
                raise HTTPException(status.HTTP_403_FORBIDDEN, str(error)) from error

            document = library.get(conn, document_id)
            if document is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "no such document")

            try:
                size = library.size(document)
            except ObjectNotFound as error:
                # The row exists and the file does not. Nothing in the
                # application deletes a blob (ADR-019), so this is a restore
                # from an incomplete backup or somebody working on the volume by
                # hand - a server fault, not a missing page.
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "the document row exists but its file is missing",
                ) from error
        except HTTPException:
            # The same rule the Db dependency states: a refusal is a decision,
            # not a failure, and rolling it back would discard the access-log
            # line recording it. "Who tried to read this and could not" is the
            # question asked after an incident (ADR-019).
            conn.commit()
            raise

    media_type, kind = _serving_type(document)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": _disposition(document, kind),
        **_HARDENING,
    }

    requested: tuple[int, int] | None = None
    if range_header is not None:
        try:
            requested = _parse_range(range_header, size)
        except ValueError as error:
            raise HTTPException(
                status.HTTP_416_RANGE_NOT_SATISFIABLE,
                "range not satisfiable",
                headers={"Content-Range": f"bytes */{size}"},
            ) from error

    # None means either no Range header or one this server ignores, and RFC 9110
    # 14.2 answers both the same way: the whole representation.
    if requested is None:
        return StreamingResponse(
            _stream(library, document, 0, size - 1),
            media_type=media_type,
            headers={**headers, "Content-Length": str(size)},
        )

    first, last = requested
    return StreamingResponse(
        _stream(library, document, first, last),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            **headers,
            "Content-Range": f"bytes {first}-{last}/{size}",
            "Content-Length": str(last - first + 1),
        },
    )


class PageEvidence(BaseModel):
    """One page as the index holds it: what the review screen reads from.

    Text rather than the file, and the two are not alternatives. The bytes are
    the record and the route above serves them at the cited page (ADR-019); this
    is what lets the screen put the drafted step beside the sentence it was taken
    from without a person opening a PDF for every proposal - which is the
    difference between a review that takes seconds and one that gets waved
    through (ADR-064).
    """

    model_config = ConfigDict(frozen=True)

    document_id: DocumentId
    title: str
    # The model this manual is for. The screen compares it against the
    # proposal's: a step drafted from another model's manual is the one thing
    # ADR-015's recall setting cannot be relaxed about, and reviewers are bad at
    # noticing it unaided.
    machine_model: MachineModel
    edition: str | None
    withdrawn: bool
    page: int
    # Why there is no text, when there is none: `no_text` is a scan,
    # `unreadable` is a damaged page, and `not_indexed` is a manual ingest has
    # not read - or has not read this far. Three different problems with three
    # different answers, and an empty panel states none of them (principle 5).
    outcome: str
    text: str | None


@router.get("/documents/{document_id}/pages/{page}", response_model=PageEvidence)
def page_evidence(
    request: Request,
    document_id: DocumentId,
    page: int,
    conn: Db,
    account: Annotated[Account, Depends(requires(*_MAY_READ, action="read_page_text"))],
) -> PageEvidence:
    """The indexed text of one page, for the panel beside a drafted step.

    Authorised and logged like the bytes are. It is the same NDA material in
    another form, and an endpoint that served the text of a manual without the
    check the file route applies would be the way round it (ADR-019).
    """
    library: DocumentLibrary = request.app.state.library
    document = library.get(conn, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no such document")

    # A page the index has never read is answered, not refused. The document is
    # real, and which manual - and which machine model - a step cites is the one
    # thing ADR-015 does not relax about: a reviewer has to be told that step 3
    # points at another model's bulletin whether or not there is text to show
    # beside it. The 404 above is for a document that does not exist at all.
    outcome = index.outcome_of(conn, document_id, page)

    chunks = index.chunks_on_pages(conn, [(document_id, page)])
    # Chunks are pieces of one page in reading order (ADR-034), so joining them
    # back is the page as the drafter saw it - which is what makes locating the
    # span in it meaningful.
    text = "\n\n".join(chunk.text for chunk in chunks) if chunks else None
    return PageEvidence(
        document_id=document.document_id,
        title=document.title,
        machine_model=document.machine_model,
        edition=document.edition,
        withdrawn=document.status is DocumentStatus.WITHDRAWN,
        page=page,
        outcome="not_indexed" if outcome is None else outcome.value,
        text=text,
    )


class Registered(BaseModel):
    """What an upload returns: the identity the file now has, and its job."""

    model_config = ConfigDict(frozen=True)

    document_id: DocumentId
    filename: str
    machine_model: MachineModel
    size_bytes: int
    # The ingest job queued for it. Returned rather than hidden, because an
    # operator who has just uploaded a two-hundred-page scan needs something to
    # ask about, and "it is in the library" and "it can be searched" are minutes
    # apart (ADR-017).
    ingest_job: int


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def upload(
    request: Request,
    conn: Db,
    account: Annotated[
        Account,
        Depends(requires(Role.OPERATOR, Role.ENGINEER, action="upload_document")),
    ],
    jobs: Jobs,
    machine_model: Annotated[MachineModel, Form()],
    title: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
    edition: Annotated[str | None, Form()] = None,
) -> Registered:
    """Put a manual in the library.

    Operator or engineer only, and refused **at the endpoint** - which is what
    invariant 6 asks for and what a hidden button does not provide. A technician
    with a session and a curl command gets a 403 and a line in the access log.

    Streamed rather than read into memory: a scanned manual is tens of megabytes
    and buffering each one whole before storing it is a limit that would first
    be found on the plant's own hardware.
    """
    library: DocumentLibrary = request.app.state.library

    # Read the first bytes, check them, then hand the stream back from the top.
    # Peeking rather than buffering keeps the streaming property above: a
    # scanned manual is still never held in memory whole.
    head = file.file.read(_MAGIC_WINDOW)
    file.file.seek(0)
    content_type = _checked_media_type(file.content_type, head)

    try:
        document = library.add_stream(
            conn,
            source=file.file,
            filename=file.filename or "untitled.pdf",
            content_type=content_type,
            machine_model=machine_model,
            title=title,
            uploaded_by=account.user,
            edition=edition,
        )
    except (DocumentModelConflict, DocumentRegistrationConflict) as error:
        # The same bytes already in the library under another machine model. A
        # 409 rather than a 500 because it is the caller's answer and they can
        # act on it - and because only an HTTPException commits, so a bare
        # exception would have rolled back the access-log line for exactly the
        # requests that failed, which is the "without exception" ADR-019 asks
        # for going missing where it matters most.
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    # The row and the job that indexes it, in one transaction (ADR-017). Until
    # this line, uploading a manual put a file on disk and a row in a table and
    # nothing ever read either: the pipeline was complete from the worker
    # inwards and had no way in.
    #
    # Queued unconditionally, including for bytes the library already held.
    # Re-ingesting replaces a document's pages and chunks rather than adding to
    # them, so the cost of the duplicate is a few seconds of a worker that has
    # nothing else to do - and the alternative, deciding here whether the index
    # is current, is a second opinion about a question `document_page` already
    # answers.
    job = jobs.enqueue(conn, kind=JobKind.INGEST, payload={"document_id": document.document_id})
    return Registered(
        document_id=document.document_id,
        filename=document.filename,
        machine_model=document.machine_model,
        size_bytes=document.size_bytes,
        ingest_job=job.id,
    )

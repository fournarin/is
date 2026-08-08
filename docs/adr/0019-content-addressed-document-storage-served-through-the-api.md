# ADR-019: Store documents content-addressed on the filesystem, served through the API

## Context

ADR-018 requires manual files to persist forever, even after the operator removes
them from the system, because `playbook_snapshot` cites page numbers in a
specific edition. Plant documents are under NDA, deployment is a single
on-premise node, and total volume for the term is in the single-digit gigabytes.

Options considered: the filesystem, MinIO or S3, or bytes in PostgreSQL.

## Decision

The filesystem on one volume, behind an `ObjectStore` interface (put / get /
exists), with files named by the sha256 of their contents, served through the API
in every case, with no presigned URLs. The application contains no code that
deletes a blob.

## Reasons

1. **What settles it:** MinIO wins on two counts, presigned URLs and range
   requests. But **we have to refuse presigned URLs ourselves because of the
   NDA** (see point 2), which discards its biggest advantage by choice. And once
   everything is served through the API, range support has to be implemented at
   the API layer regardless of what sits behind it. With those two subtracted,
   MinIO is left offering multi-node operation and high throughput, neither of
   which this deployment has, while its cost remains.
2. **Serving through the API puts every read through RBAC and into the access
   log, without exception.** A presigned URL is a hole in that by design: whoever
   holds the URL can read until it expires, with no further authorisation and no
   line in the log. Shortening its lifetime is an admission that the hole exists.
3. **Hashing the contents solves the problem ADR-018 created.** Operators
   routinely upload a new edition under the old filename. Stored by name, the old
   file is overwritten and a snapshot citing "page 47" then points at unrelated
   content - an audit trail that is wrong silently, which is worse than none.
4. Not bytes in PostgreSQL: scanned PDFs of tens of megabytes make `pg_dump` slow
   and large. A database should hold pointers, not blobs.
5. Backups come down to two sets, PostgreSQL and the storage directory, because
   Qdrant is derived data that can be rebuilt by re-ingesting. On a machine
   somebody else maintains, one fewer backup matters.

## Consequences

- Four things have to be implemented that MinIO would have given: the `Range`
  header (mandatory, because citation to page number is the system's central
  interaction and without it every click downloads the whole file), content type
  and disposition headers, atomic writes via temp-and-rename so an interrupted
  upload cannot leave a file whose hash does not match, and an authorisation
  check before serving.
- "Delete" becomes a change to `documents.status`, not a file operation.
- No cleanup job. If the disk fills, that is an operator decision following a
  written procedure, because a job that deletes a PDF a snapshot still cites
  destroys evidence invisibly.

**Revisit if:** the plant already runs something S3-compatible, scanned drawings
turn into many hundred-megabyte files, or deployment needs several nodes. All
three change only the second adapter behind `ObjectStore`. **Even on MinIO,
serving stays through the API with no presigned URLs**, for the reason in
point 2.

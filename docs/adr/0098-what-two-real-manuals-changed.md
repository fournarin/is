# ADR-098: What two real manufacturer manuals changed

Written on 2026-09-28. The owner supplied two real manuals to test with: a
Mitsubishi servo motor instruction manual (456 pages) and an MR-J4 servo
amplifier Modbus manual (118 pages). They are test material only. They are not
committed: `.gitignore` refuses PDFs, and the folder is excluded locally.

## What they showed that the synthetic corpora could not

1. **Both are AES-encrypted** with an empty open password, the usual way
   manufacturers protect manuals against editing. pypdf needs the
   `cryptography` package to open them. Before this change, **the first real
   manual uploaded would have been refused as unreadable.**
2. **Reranking forty full pages in one call grew the process to 15 GB.** The
   authoring container has 4 GB, so the first real manual would have killed the
   worker. The reranker now scores four pages per call.
3. **Numbered shapes that are not steps.** "(1) Inspection ... (2) Life" and
   "Note 1. ... 2. ..." were read as numbered procedures and drafted as repair
   playbooks.
4. **Neither manual prescribes a field repair.** Both say to inspect and to
   contact the manufacturer for repair or replacement. What the system owes a
   technician for these is the inspection text from the right page, labelled
   as fault-finding, and it must not dress that text up as a repair.
5. **Most of the pages are tables.** More than 300 of the motor manual's 456
   pages are dimension tables, and "brake" appears on a hundred of them. That is
   the retrieval problem a real manual poses and a synthetic one does not.

## Decision

1. `pypdf[crypto]` replaces `pypdf`. The only new package is `cryptography`,
   which is widely used and maintained. A PDF that needs a password to open is
   refused with a sentence saying so.
2. The reranker scores at most four pages per model call.
3. A step marker may not follow "(" or "Note ".
4. `fixtures/realdocs/manifest.yaml` is an answer key for the two manuals,
   written by reading them before the pipeline ran. It holds questions and page
   numbers, not the manuals' text. `scripts/measure_rag.py realdocs` measures it
   against PDFs in `REALDOCS_DIR`.

## Consequences

- The measurement is in `docs/results/rag-evaluation.md`. It is the first
  figure in this repository from a document this project did not write.
- The plant's own manuals will differ again. The same key-and-measure loop is
  what an installation should run on its first manuals, before trusting drafts.

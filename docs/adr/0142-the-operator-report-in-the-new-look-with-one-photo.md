# ADR-142: The operator's report in the new look, with one photo

Written on 2026-11-18. Set 4 of the frontend rebuild, inside the owner's final
plan for November (window 2). Decided by the agent on the owner's delegation
(ADR-090). The photo is the trial technician's request (trial-kong, Q15).

## Decision

1. **`/report` is drawn in the design system (ADR-133).** Three ways in, all
   plain links: `?machine=` from the QR on a machine, a station then its
   machine, or the list of stations in line order. The form asks three
   questions by taps (REQ-P-01): is the machine stopped (required, its own
   question, REQ-P-04), what was seen (four words, more than one allowed, with
   an optional typed line), and how urgent (optional; `critical` is still not
   offered, ADR-077). The answers are stored as the report's description, the
   stopped answer first, until the API has a field for it.
2. **The reporter's list shows four stages** - received, sent to a technician,
   being repaired, done - from `GET /work-orders/reported`, which now carries
   `stages` and `stage` (REQ-P-05). The screen does not show `where`, which
   names the technician (REQ-P-06). `/machines` carries the station's name
   (REQ-P-03).
3. **One photo per report.** The phone shrinks it to 1600 px on the long side
   (JPEG, quality 0.8) before it is sent. `POST /work-orders/{ref}/photo`
   accepts it from the reporter only, checks the magic bytes, refuses anything
   over 2 MB, and stores the bytes in the content-addressed object store
   (ADR-019, never deleted). A new table, `work_order_photo`, links the blob to
   the order: one row per order, with who took it and when.
   `GET /work-orders/{ref}/photo` serves it to any signed-in role, through the
   web origin (ADR-058). The technician's job page shows it as "รูปจากคนแจ้ง".
4. **The report and its photo are two requests.** A refused photo (too large,
   not a picture) does not cost the report. A phone whose script did not load
   sends the photo unshrunk; the API refuses it if it is too large, and the
   screen says so under "ส่งแล้ว". The server-action body limit is 12 MB, so
   that refusal comes from the API and not from the parser, which would drop
   the words with it.
5. **No new dependency.** The shrinking is a canvas in the browser; the server
   does not decode images.

## Consequences

The privacy note "ถ่ายเฉพาะเครื่อง ไม่ถ่ายหน้าคน" is a sentence, not a check:
nothing detects a face. Offline queueing of a report (the spec's "เก็บในเครื่อง")
and photos on close notes are not built; they are future work in the report.
The observation words are a constant on the screen, not yet `plant.yaml`.

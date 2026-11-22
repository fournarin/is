# Three more real manuals, and every set again at one commit

Measured on 2026-11-18 at **`8931cbb`**
([ADR-143](../adr/0143-three-more-real-manuals-measured-as-shipped.md)), with
the settings the system ships and nothing tuned on this set:

```bash
REALDOCS_DIR=<the manuals> uv run python scripts/measure_rag.py <set> --rerank --symptom --json=<file>
```

reranker `bge-reranker-v2-m3` on, relevance floors 0.10 / 0.35 / 0.50 from
`config/policy.yaml`, 120 candidates, the symptom described (the other
language's question, as in [rag-evaluation.md](rag-evaluation.md)). No Python
file changed after `8931cbb` up to the last commit of the build, so these are
the shipped pipeline's numbers. One record per question:
[rag-2026-11-18/](rag-2026-11-18/).

## The new set

Three manufacturer manuals the owner downloaded (outside git, checksums in
the key): SMC's maintenance procedure for the MRQ rotary cylinder (14 pages),
SMC's operation manual for the MB2 air cylinder (36 pages), and SEW's gear-unit
instructions (256 pages, encrypted, opened with the empty password). The key,
`fixtures/realdocs2/manifest.yaml`, was written by a separate reviewer by
reading the manuals **before the pipeline was run on them**: 18 symptoms, each
asked in English and in Thai -

- **5 covered**: the manual prescribes a field repair (seal and packing
  replacement, the gear-unit oil-level check). Owed: a repair draft citing only
  the answer pages.
- **9 documented without a procedure**: an interval, a torque, a
  troubleshooting row. Owed: fault-finding text citing only the documented page.
- **4 absent**: owed "not found".

One edit was made to the key before any run: line 121 was not valid YAML (an
unquoted `: ` inside a description) and was quoted. No page, question or
category changed.

**Ingest.** The risk named beforehand did not happen: every page of the MB2
manual was read (pypdf warns that the `90msp-RKSJ-H` font encoding is not
implemented, and the answer pages still come out as readable English). The SEW
manual gave text on 251 of 256 pages; the five without text are its last
pages (251-255).

## Per question (realdocs2)

| Symptom | Kind | Lang | Answer page rank | Outcome | Cited | As the key implies | Unsafe |
|---|---|---|---:|---|---|---|---|
| RD2-01 | covered | en | 1 | diagnostic | MRQB-MM0 p9 | no | no |
| RD2-01 | covered | th | 1 | not_found | - | no | no |
| RD2-02 | covered | en | 1 | not_found | - | no | no |
| RD2-02 | covered | th | 6 | not_found | - | no | no |
| RD2-03 | covered | en | 1 | not_found | - · figures seal_washer_set_screw_torque_nm ✗ | no | no |
| RD2-03 | covered | th | 4 | not_found | - · figures seal_washer_set_screw_torque_nm ✗ | no | no |
| RD2-04 | covered | en | 1 | not_found | - | no | no |
| RD2-04 | covered | th | 10 | not_found | - | no | no |
| RD2-05 | covered | en | 1 | repair | 31978088 p169 · figures m10 ✓, m12 ✓, m22 ✗, m33 ✗, m42 ✗ | no | **UNSAFE** |
| RD2-05 | covered | th | 5 | repair | 31978088 p169 · figures m10 ✓, m12 ✓, m22 ✗, m33 ✗, m42 ✗ | no | **UNSAFE** |
| RD2-06 | documented, no procedure | en | 3 | diagnostic | MRQB-MM0 p4 | yes | no |
| RD2-06 | documented, no procedure | th | 1 | diagnostic | MRQB-MM0 p4 | yes | no |
| RD2-07 | documented, no procedure | en | 2 | not_found | - | no | no |
| RD2-07 | documented, no procedure | th | 8 | not_found | - | no | no |
| RD2-08 | documented, no procedure | en | 3 | not_found | - | no | no |
| RD2-08 | documented, no procedure | th | 2 | not_found | - | no | no |
| RD2-09 | documented, no procedure | en | 2 | diagnostic | om_mb2_d p33 | yes | no |
| RD2-09 | documented, no procedure | th | 13 | not_found | - | no | no |
| RD2-10 | documented, no procedure | en | 1 | not_found | - | no | no |
| RD2-10 | documented, no procedure | th | 4 | not_found | - | no | no |
| RD2-11 | documented, no procedure | en | 3 | diagnostic | 31978088 p154 | yes | no |
| RD2-11 | documented, no procedure | th | 2 | diagnostic | 31978088 p154 | yes | no |
| RD2-12 | documented, no procedure | en | 5 | not_found | - | no | no |
| RD2-12 | documented, no procedure | th | 19 | not_found | - | no | no |
| RD2-13 | documented, no procedure | en | 1 | not_found | - | no | no |
| RD2-13 | documented, no procedure | th | 1 | not_found | - | no | no |
| RD2-14 | documented, no procedure | en | 7 | diagnostic | 31978088 p157 | yes | no |
| RD2-14 | documented, no procedure | th | 10 | diagnostic | 31978088 p157 | yes | no |
| RD2-15 | absent | en | - | not_found | - | yes | no |
| RD2-15 | absent | th | - | not_found | - | yes | no |
| RD2-16 | absent | en | - | not_found | - | yes | no |
| RD2-16 | absent | th | - | not_found | - | yes | no |
| RD2-17 | absent | en | - | not_found | - | yes | no |
| RD2-17 | absent | th | - | not_found | - | yes | no |
| RD2-18 | absent | en | - | not_found | - | yes | no |
| RD2-18 | absent | th | - | not_found | - | yes | no |

The answer-page rank is the position of the first page the key names among
the pages retrieved for that machine's manual (a page found by the first stage
but cut by the floor still has a rank).

## What the new set says

- **2 unsafe drafts, both RD2-05** (the gear-unit oil-level check, English and
  Thai). The pipeline drafted a six-step repair from **page 169**, section
  6.6.6 D: checking the oil level of a *SPIROPLAN W..37/W..47* gear unit. The
  key's answer is pages 159-160, section 6.6.3 A, the same check for helical,
  parallel-shaft and helical-bevel units. The same manual holds the same task
  for several gear families, with different mounting positions and level
  figures, and the question did not say which family. The draft is a real
  procedure from the manual, cited to the right document - for the wrong
  product type. This is the failure ADR-003 keeps a reviewer for: the
  engineer approving it would have to notice that page 169 is not about the
  plant's gear unit. Two of the five level figures the key names (1.5 and
  2 mm, for M10 and M12) appear somewhere in the draft's text.
- **No covered symptom got the repair it was owed (0 of 10 questions).** Seven
  were answered "not found", one with fault-finding text from the right page
  (RD2-01 in English, page 9), two were the unsafe drafts above. On the two
  SMC manuals the answer page was retrieved first in English in all four
  cases and the pipeline still declined to draft a repair from it.
- **Documented without a procedure: 7 of 18** as the key implies; every
  miss is "not found", the safe failure.
- **Absent: 8 of 8** "not found".
- **English finds the page, Thai finds it less.** The answer page was in the
  top 3 for 12 of 14 English questions and 5 of 14 Thai ones.

## Totals, every set at the same commit

| Set | Lang | As the key implies | Unsafe drafts | Answer page at rank 1 | in top 3 |
|---|---|---|---:|---|---|
| realdocs2 (test split) | en | 8/18 (44 %, 95 % CI 25-66 %) | 1 | 7/14 (50 %, 95 % CI 27-73 %) | 12/14 (86 %, 95 % CI 60-96 %) |
| realdocs2 (test split) | th | 7/18 (39 %, 95 % CI 20-61 %) | 1 | 3/14 (21 %, 95 % CI 8-48 %) | 5/14 (36 %, 95 % CI 16-61 %) |
| realdocs (test split) | en | 8/9 (89 %, 95 % CI 56-98 %) | 0 | 1/7 (14 %, 95 % CI 3-51 %) | 4/7 (57 %, 95 % CI 25-84 %) |
| realdocs (test split) | th | 7/9 (78 %, 95 % CI 45-94 %) | 0 | 2/7 (29 %, 95 % CI 8-64 %) | 6/7 (86 %, 95 % CI 49-97 %) |
| evalset (test split) | en | 9/12 (75 %, 95 % CI 47-91 %) | 0 | 9/10 (90 %, 95 % CI 60-98 %) | 10/10 (100 %, 95 % CI 72-100 %) |
| evalset (test split) | th | 6/12 (50 %, 95 % CI 25-75 %) | 0 | 7/10 (70 %, 95 % CI 40-89 %) | 10/10 (100 %, 95 % CI 72-100 %) |
| corpus (all dev) | en | 5/5 (100 %, 95 % CI 57-100 %) | 0 | 2/4 (50 %, 95 % CI 15-85 %) | 4/4 (100 %, 95 % CI 51-100 %) |
| corpus (all dev) | th | 5/5 (100 %, 95 % CI 57-100 %) | 0 | 2/4 (50 %, 95 % CI 15-85 %) | 4/4 (100 %, 95 % CI 51-100 %) |

## Five real manuals together (realdocs + realdocs2)

| Lang | As the key implies | Unsafe drafts |
|---|---|---:|
| en | 16/27 (59 %, 95 % CI 41-75 %) | 1/27 (4 %, 95 % CI 1-18 %) |
| th | 14/27 (52 %, 95 % CI 34-69 %) | 1/27 (4 %, 95 % CI 1-18 %) |
| both | 30/54 (56 %, 95 % CI 42-68 %) | 2/54 (4 %, 95 % CI 1-13 %) |

`realdocs`, `evalset` and `corpus` reproduce, entry for entry in their totals,
what was last published (4 October, [rag-evaluation.md](rag-evaluation.md)):
the code they measure has not changed.

The evaluation set's test split has been looked at after changes since
ADR-097 and is no longer fully held out; the two real-manual keys never were
tuned on.

## Five real manuals together (realdocs + realdocs2)

| Lang | As the key implies | Unsafe drafts |
|---|---|---:|
| en | 16/27 (59 %, 95 % CI 41-75 %) | 1/27 (4 %, 95 % CI 1-18 %) |
| th | 14/27 (52 %, 95 % CI 34-69 %) | 1/27 (4 %, 95 % CI 1-18 %) |
| both | 30/54 (56 %, 95 % CI 42-68 %) | 2/54 (4 %, 95 % CI 1-13 %) |

**With 54 questions the claim changes.** On the first two manuals the honest
sentence was "no unsafe draft on 18 questions, compatible with up to 18 %".
With five manuals it is: **2 unsafe drafts in 54 questions (4 %, 95 % CI
1-13 %), both from one symptom**, a repair procedure for the right task on the
wrong product family of the same manual.

## Unsafe drafts by id

- realdocs2 RD2-05 (en): repair citing [('31978088.pdf', 169)]
- realdocs2 RD2-05 (th): repair citing [('31978088.pdf', 169)]

## Ingest coverage

- realdocs2 MRQB-MM00003.pdf: 14/14 pages with text, 29 chunks, no text on none
- realdocs2 om_mb2_doc1088008en.pdf: 36/36 pages with text, 84 chunks, no text on none
- realdocs2 31978088.pdf: 251/256 pages with text, 501 chunks, no text on [251, 252, 253, 254, 255]
- realdocs sh3181l.pdf: 455/456 pages with text, 1043 chunks, no text on none
- realdocs sh030175b.pdf: 117/118 pages with text, 344 chunks, no text on none
- evalset sw-210-servo-gun.pdf: 10/10 pages with text, 10 chunks, no text on none
- evalset sw-310-servo-gun.pdf: 6/6 pages with text, 6 chunks, no text on none
- evalset cv-500-skid-conveyor.pdf: 9/9 pages with text, 9 chunks, no text on none
- evalset sd-30-sealer-dispenser.pdf: 7/7 pages with text, 7 chunks, no text on none
- corpus r-2000ic-maintenance.pdf: 11/11 pages with text, 12 chunks, no text on none
- corpus m-710ic-maintenance.pdf: 7/7 pages with text, 7 chunks, no text on none

## Limits

- 18 symptoms, three manuals, one answer key written by one reviewer.
- "As the key implies" checks the outcome and the pages cited, not each
  instruction: a draft on the right page can still drop a figure (the
  `figures` field of each record says which of the key's figures appear).
- The two languages are the same symptoms asked twice; they are not
  independent samples.

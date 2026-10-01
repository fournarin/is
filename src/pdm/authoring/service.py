"""Ingest and drafting: the two authoring jobs (ADR-034, ADR-037).

The only module `workers/` calls to index a manual. It opens no connection - the
caller supplies one - so the page records, the chunks and the job that produced
them commit together (ADR-017). A half-indexed manual that reports success is
the failure that ordering prevents.

Runs as an authoring job, never in a request. Parsing a two-hundred-page scan
takes minutes, and ADR-026 exists so that work cannot stall the dispatch tick.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from psycopg import Connection
from pydantic import BaseModel, ConfigDict

from pdm.authoring.domain import chunk_document
from pdm.authoring.drafting import DraftResult, assemble
from pdm.authoring.parsing import parse
from pdm.contracts import DocumentId, MachineModel, SymptomCode
from pdm.llm.domain import Drafter, DraftRequest, Evidence
from pdm.llm.extractive import continues_to
from pdm.platform.documents import Document, DocumentLibrary
from pdm.playbooks import repo as playbooks
from pdm.playbooks.domain import Proposal, ProposalOrigin
from pdm.retrieval import repo as index
from pdm.retrieval.domain import IndexedPage, PageOutcome
from pdm.retrieval.rerank import Reranker
from pdm.retrieval.service import HybridSearch, Profile, Retrieved

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class IngestReport(BaseModel):
    """What one manual gave up, and what it did not.

    Returned rather than logged because coverage is a number the report has to
    carry: on real manuals "the pipeline works" is only true for the fraction of
    pages that produced text, and that fraction belongs beside every retrieval
    figure measured on them (ADR-034).
    """

    model_config = _FROZEN

    document_id: DocumentId
    pages: int
    pages_with_text: int
    chunks: int
    pages_needing_ocr: tuple[int, ...]

    @property
    def coverage(self) -> float:
        return self.pages_with_text / self.pages if self.pages else 0.0

    @property
    def is_fully_readable(self) -> bool:
        return self.pages > 0 and self.pages_with_text == self.pages


def _what_the_index_got(parsed: PageOutcome, produced_chunks: bool) -> PageOutcome:
    """The outcome as the *index* sees it, not as the parser left it.

    A page whose only text is the running header parses as TEXT and then loses
    all of it to furniture stripping, so it produced nothing searchable while
    coverage counted it as read. Coverage is the number that has to travel with
    every retrieval figure measured on a real manual (ADR-034); a version of it
    that counts pages nothing can retrieve would overstate exactly the thing it
    exists to be honest about.
    """
    if parsed is PageOutcome.TEXT and not produced_chunks:
        return PageOutcome.TOO_LITTLE_TEXT
    return parsed


class UnknownDocument(Exception):
    """Asked to ingest something the library has no row for."""


class Ingest:
    """Reads a document out of the library and writes it into the index.

    Both halves of the index, when one is supplied. The vector half is optional
    because most tests and the whole of slice 3.2 have no use for it and no
    reason to load a model - but when it is absent, ingesting leaves the dense
    half stale rather than empty, so anything searching afterwards is searching
    yesterday's vectors.
    """

    def __init__(self, library: DocumentLibrary, hybrid: HybridSearch | None = None) -> None:
        self.library = library
        self.hybrid = hybrid

    def run(self, conn: Connection[Any], document_id: DocumentId) -> IngestReport:
        """Parse, chunk, index. Replaces whatever was there before.

        Replacing rather than adding is what makes re-ingesting safe after a
        parser change: the alternative leaves the previous parser's chunks in
        place beside the new ones, and a search then returns two versions of the
        same page with no way to tell which is current.
        """
        document = self.library.get(conn, document_id)
        if document is None:
            raise UnknownDocument(f"no document {document_id} in the library")

        with self.library.open(document) as handle:
            parsed = parse(handle)

        chunks = chunk_document(document_id, parsed.pages)
        chunked = {chunk.page for chunk in chunks}

        pages = [
            IndexedPage(
                document_id=document_id,
                page=page.page,
                outcome=_what_the_index_got(page.outcome, page.page in chunked),
                characters=len(page.text),
            )
            for page in parsed.pages
        ]

        index.replace_pages(conn, document_id, pages)
        index.insert_chunks(conn, chunks)

        # After PostgreSQL, never before. That order is what makes a crash
        # between the two a chunk the dense half cannot see - degraded
        # retrieval - rather than a vector pointing at a chunk that does not
        # exist (ADR-035). It is also what makes ADR-035's claim that
        # "re-ingesting repairs it" true, which it was not while nothing called
        # this at all.
        if self.hybrid is not None:
            self.hybrid.index_document(document_id, chunks, document.machine_model)

        return IngestReport(
            document_id=document_id,
            pages=len(pages),
            pages_with_text=sum(1 for page in pages if page.outcome is PageOutcome.TEXT),
            chunks=len(chunks),
            pages_needing_ocr=tuple(page.page for page in pages if page.needs_ocr),
        )

    def withdraw(self, conn: Connection[Any], document: Document) -> int:
        """Take a manual out of the index when its edition is withdrawn.

        design.md section 5: the old manual is removed from the index for real
        and the file is kept, because `playbook_snapshot` cites its pages. The
        index is a projection and can be rebuilt; the file is the record.

        **Every playbook citing it moves to `needs_review` in the same
        transaction** (ADR-018). Splitting the two would leave a window in which
        the manual is gone from the index and the procedures derived from it are
        still being served as current - and the window would be however long it
        took somebody to remember the second step.

        Deliberately separate from `DocumentLibrary.withdraw`, which changes the
        row. The library sits in `platform/` and must not know that an index
        exists; joining the two is the caller's job, in one transaction.
        """
        removed = index.drop_document(conn, document.document_id)
        playbooks.flag_for_review(
            conn,
            document.document_id,
            reason=(
                f"{document.title} ({document.edition or 'no edition recorded'}) was withdrawn; "
                "this procedure was drafted from it and has not been checked against the "
                "replacement"
            ),
        )
        if self.hybrid is not None:
            self.hybrid.drop_document(document.document_id)
        return removed


class Drafting:
    """Retrieval, a backend, and the gate: one symptom becomes one draft.

    The order is the whole of ADR-037. Retrieval offers pages under the authoring
    profile, which is deliberately loose (ADR-015); the pages belonging to other
    machine models are separated out before the backend sees anything, and travel
    beside the result for the reviewer; the backend picks spans; and nothing it
    returns is believed until `assemble` has checked it.

    It opens no connection, holds no state between calls, and asks the clock for
    nothing. Two runs of the same symptom against the same index and the same
    backend produce the same draft, which is what makes the drafting figures in
    the report reproducible.
    """

    def __init__(
        self,
        hybrid: HybridSearch,
        drafter: Drafter,
        *,
        profile: Profile,
        skills: Iterable[str],
        reranker: Reranker | None = None,
    ) -> None:
        self.hybrid = hybrid
        self.drafter = drafter
        self.profile = profile
        # Scores each candidate page against the question (ADR-097). Without
        # one, a page's score is the fused rank score, which cannot say "none of
        # these answers it".
        self.reranker = reranker
        # The vocabulary from plant.yaml. Held rather than read here because
        # `service.py` must not reach for configuration on its own: the caller
        # loaded it at boot, and a second reader would be a second answer to
        # "what skills exist" (invariant 13).
        self.skills = frozenset(skills)

    def run(
        self,
        conn: Connection[Any],
        *,
        symptom_code: SymptomCode,
        machine_model: MachineModel,
        question: str,
        symptom: str | None = None,
    ) -> DraftResult:
        """Draft one playbook, or say why there is none.

        `question` is what retrieval is asked. It comes from the caller rather
        than from the symptom code, because a code is not a query: SYM-014
        retrieves nothing and "belt motor running above 85 degrees" retrieves the
        page.

        `symptom` is the rule's own description of the fault, and a page must be
        relevant to it as well as to the question (ADR-121). In the owner's
        second trial "85 องศา" was typed for the safety-interlock symptom; the
        belt-motor page answers "85 degrees" well, and its six steps were filed
        as a repair for an interlock. A question can be wrong; the symptom the
        draft will be filed under cannot.
        """
        hits = self.hybrid.search(conn, question, profile=self.profile)
        ours, theirs = self._evidence(conn, hits, machine_model)
        ours = self._relevant(question, ours)
        if symptom is not None and symptom.strip() and symptom.strip() != question.strip():
            ours = self._about(symptom.strip(), ours)
        ours = self._with_continuations(conn, ours)

        request = DraftRequest(
            symptom_code=symptom_code,
            machine_model=machine_model,
            question=question,
            evidence=ours,
            relevance_scored=self.reranker is not None,
            draft_floor=self.profile.min_relevance_to_draft or 0.0,
            repair_floor=self.profile.min_relevance_for_repair or 0.0,
        )
        return assemble(
            request,
            self.drafter.propose(request),
            skills=self.skills,
            cross_model=theirs,
        )

    def file(
        self,
        conn: Connection[Any],
        result: DraftResult,
        *,
        now: datetime,
    ) -> Proposal:
        """Put a drafting result in the review queue (ADR-038).

        Every outcome is filed, including the ones with no steps. A withheld
        draft says the backend produced something unusable and a `not_found` says
        the manuals are silent, and both are things a person should see: the
        first is a model to stop trusting, the second is a gap in the manuals
        somebody has to fill. Filing only the successes would leave both
        invisible, which is how a corpus acquires a hole nobody knows about.

        The clock is passed in rather than held, because this is the only part of
        drafting that is not a pure function of the index and the backend, and
        keeping it in the signature is what stops the rest of the class quietly
        acquiring a dependency on the time (ADR-028).
        """
        draft = result.draft
        return playbooks.add_proposal(
            conn,
            symptom_code=result.symptom_code,
            machine_model=result.machine_model,
            origin=ProposalOrigin.DRAFTED,
            outcome=result.outcome.value,
            steps=draft.steps if draft else (),
            tools=draft.tools if draft else (),
            proposed_skill=draft.proposed_skill if draft else None,
            proposed_minutes=draft.proposed_minutes if draft else None,
            rejected=tuple(step.model_dump(mode="json") for step in result.rejected),
            reason=result.reason,
            created_at=now,
            # No user: the authoring pipeline filed it. A technician's objection
            # names the person, and the review screen shows the difference.
            created_by=None,
        )

    def _evidence(
        self,
        conn: Connection[Any],
        hits: list[Retrieved],
        machine_model: MachineModel,
    ) -> tuple[tuple[Evidence, ...], tuple[Evidence, ...]]:
        """Hits regrouped into whole pages, split by machine model.

        A page scores as high as its best chunk. Summing instead would rank a
        page that was cut into four mediocre chunks above one whose single chunk
        answered the question, which is a property of the chunker rather than of
        the manual.
        """
        best: dict[tuple[DocumentId, int], Retrieved] = {}
        for hit in hits:
            if hit.score < self.profile.min_score:
                # The authoring profile does not abstain (ADR-015): it returns
                # its best guesses so a reviewer can dismiss them. Writing steps
                # is not the same act as offering a candidate, so the floor the
                # profile carries is applied here even though the search did not
                # apply it.
                continue
            key = (hit.chunk.document_id, hit.chunk.page)
            if key not in best or hit.score > best[key].score:
                best[key] = hit

        ranked = sorted(best.items(), key=lambda item: (-item[1].score, item[0]))
        text = self._page_text(conn, [key for key, _ in ranked])

        evidence = [
            Evidence(
                document_id=key[0],
                page=key[1],
                text=text[key],
                title=hit.title,
                machine_model=hit.machine_model,
                score=hit.score,
            )
            for key, hit in ranked
            if key in text
        ]
        return (
            tuple(page for page in evidence if page.machine_model == machine_model),
            tuple(page for page in evidence if page.machine_model != machine_model),
        )

    def _relevant(self, question: str, pages: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        """The pages that answer the question, scored by how well (ADR-097).

        Each page's score becomes the reranker's relevance, and a page below the
        profile's `min_relevance` is dropped. When none is left, the drafter is
        handed no evidence and the outcome is "not found": the manuals do not
        cover this, and an engineer is asked rather than shown the nearest page.
        """
        if self.reranker is None or not pages:
            return pages
        scores = self.reranker.relevance(question, [page.text for page in pages])
        floor = self.profile.min_relevance or 0.0
        kept = [
            page.model_copy(update={"score": round(score, 4)})
            for page, score in zip(pages, scores, strict=True)
            if score >= floor
        ]
        kept.sort(key=lambda page: (-page.score, page.page))
        return tuple(kept)

    def _about(self, symptom: str, pages: tuple[Evidence, ...]) -> tuple[Evidence, ...]:
        """The pages that are also about the symptom, keeping the question's scores.

        The same reranker and the same floor as `_relevant`, asked about the
        rule's description instead of the question. Only filters: the order and
        the scores the drafter sees stay the question's (ADR-121).
        """
        if self.reranker is None or not pages:
            return pages
        scores = self.reranker.relevance(symptom, [page.text for page in pages])
        floor = self.profile.min_relevance or 0.0
        return tuple(page for page, score in zip(pages, scores, strict=True) if score >= floor)

    def _with_continuations(
        self, conn: Connection[Any], pages: tuple[Evidence, ...]
    ) -> tuple[Evidence, ...]:
        """Relevant pages plus the pages their procedures run onto (ADR-100).

        A continuation page often carries only steps 5 to 7 and none of the
        question's words, so it can score below the floor and still be half the
        procedure. It is added at its neighbour's score, and so is a page that
        says it continues onto a relevant one.
        """
        have = {(page.document_id, page.page) for page in pages}
        wanted: dict[tuple[DocumentId, int], Evidence] = {}
        for page in pages:
            after = continues_to(page.text, page.page)
            if after is not None and (page.document_id, after) not in have:
                wanted[(page.document_id, after)] = page
            if page.page > 1 and (page.document_id, page.page - 1) not in have:
                wanted[(page.document_id, page.page - 1)] = page
        if not wanted:
            return pages
        text = self._page_text(conn, list(wanted))
        added = []
        for key, source in wanted.items():
            if key not in text:
                continue
            neighbour = source.model_copy(
                update={"page": key[1], "text": text[key], "joined_only": True}
            )
            before_source = key[1] == source.page - 1
            if before_source and continues_to(neighbour.text, neighbour.page) != source.page:
                continue
            added.append(neighbour)
        return (*pages, *added)

    def _page_text(
        self, conn: Connection[Any], pages: list[tuple[DocumentId, int]]
    ) -> dict[tuple[DocumentId, int], str]:
        joined: dict[tuple[DocumentId, int], list[str]] = {}
        for chunk in index.chunks_on_pages(conn, pages):
            joined.setdefault((chunk.document_id, chunk.page), []).append(chunk.text)
        return {key: "\n".join(parts) for key, parts in joined.items()}

"""Typed access to the answer key in manifest.yaml (ADR-033).

The manifest is the source of truth and this module only gives it a shape. The
alternative - each test reaching into a dict of dicts - means a typo in a key
reads as "no distractors declared" and the test passes while checking nothing,
which is the failure this corpus exists to prevent one level up.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

# The answer key speaks the system's vocabulary rather than plain strings. Two
# vocabularies that fail to match in silence is the failure ADR-027 exists to
# prevent, and a fixture keyed on a symptom code the system spells differently
# would produce an eval that quietly matches nothing.
from pdm.contracts import DocumentId, MachineModel, SkillId, SymptomCode

_FROZEN = ConfigDict(frozen=True, extra="forbid")

CORPUS_DIR = Path(__file__).parent
MANIFEST = CORPUS_DIR / "manifest.yaml"


class ManualDocument(BaseModel):
    """One PDF, with the hash that ADR-019 turns into its document id."""

    model_config = _FROZEN

    filename: str
    sha256: DocumentId = Field(pattern="^[0-9a-f]{64}$")
    title: str
    machine_model: MachineModel
    edition: str
    pages: int = Field(gt=0)
    # The synthetic corpus always has one (a test holds it to that). A real
    # manual's key may not name one: the second set was written by reading the
    # repair sections, not the safety chapter.
    lockout_page: int | None = Field(default=None, gt=0)
    # Owner-password AES, opened with the empty password (ADR-098). Recorded so
    # the key says why the file needs pypdf's `crypto` extra.
    encrypted: bool = False

    @property
    def path(self) -> Path:
        return CORPUS_DIR / self.filename

    def actual_sha256(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


class PageRef(BaseModel):
    """A page in some document. `document` is None when it means "this one"."""

    model_config = _FROZEN

    page: int = Field(gt=0)
    document: str | None = None


class Distractor(PageRef):
    """A page that looks like the answer and is not.

    The reason is required. A distractor with no stated reason is a page
    somebody thought was irrelevant, which is not the same thing and cannot be
    argued with later.
    """

    why: str = Field(min_length=1)


class MisleadingFigure(BaseModel):
    """A number on the answer page that belongs to something else.

    These are the drafts the authoring gate cannot catch: the figure really is
    in the cited evidence, so the subset check passes, and the step is still
    wrong. Recorded here so that limit is measured and stated rather than
    discovered.
    """

    model_config = _FROZEN

    value: float
    unit: str
    belongs_to: str = Field(min_length=1)


class Queries(BaseModel):
    """The same question in both languages.

    Manuals are English and technicians ask in Thai, which is the cross-lingual
    case ADR-029 requires the embedding model to handle.
    """

    model_config = _FROZEN

    en: str = Field(min_length=1)
    th: str = Field(min_length=1)


class Answer(BaseModel):
    """A symptom the corpus documents with a usable procedure."""

    model_config = _FROZEN

    # `test` entries of an evaluation set are measured and never tuned on
    # (ADR-096). The original corpus is all `dev`: it has been looked at.
    split: Literal["dev", "test"] = "dev"

    symptom_code: SymptomCode
    machine_model: MachineModel
    answer_pages: tuple[int, ...] = Field(min_length=1)
    supporting_pages: tuple[int, ...] = ()
    # Where on the page the answer is, for whoever checks a result by hand.
    why: str = ""
    # Required of the synthetic corpus (its tests check them against
    # config/plant.yaml). A key of real manuals measures retrieval and drafting
    # only, and a skill or a duration guessed for a stranger's machine would be
    # a number with no provenance.
    required_skill: SkillId | None = None
    estimated_minutes: int | None = Field(default=None, gt=0)
    tools: tuple[str, ...] = ()
    correct_figures: dict[str, float | list[float]] = {}
    figures_on_the_page_that_are_not_the_answer: tuple[MisleadingFigure, ...] = ()
    distractors: tuple[Distractor, ...] = ()
    queries: Queries


class DocumentedOnly(BaseModel):
    """A symptom the manual discusses and deliberately gives no procedure for.

    Layer 2 owes a fault-finding playbook here, not a repair one (ADR-009).
    """

    model_config = _FROZEN

    # `test` entries of an evaluation set are measured and never tuned on
    # (ADR-096). The original corpus is all `dev`: it has been looked at.
    split: Literal["dev", "test"] = "dev"

    symptom_code: SymptomCode
    machine_model: MachineModel
    pages: tuple[int, ...] = Field(min_length=1)
    # Pages that help a reader and are not the answer. A draft citing one is
    # still marked off-key: the measurement rewards the page that says it.
    supporting_pages: tuple[int, ...] = ()
    why: str = Field(min_length=1)
    queries: Queries


class AbsentSymptom(BaseModel):
    """A symptom with nothing written about it anywhere in the corpus."""

    model_config = _FROZEN

    # `test` entries of an evaluation set are measured and never tuned on
    # (ADR-096). The original corpus is all `dev`: it has been looked at.
    split: Literal["dev", "test"] = "dev"

    symptom_code: SymptomCode
    machine_model: MachineModel
    why: str = Field(min_length=1)
    # How the absence is kept honest: a test fails if any of these appears
    # anywhere in the corpus text. Required, because a declared gap nobody
    # checks stops being a gap the first time somebody adds a paragraph.
    forbidden_phrases: tuple[str, ...] = Field(min_length=1)
    queries: Queries


class Corpus(BaseModel):
    model_config = _FROZEN

    version: int = Field(ge=1)
    documents: tuple[ManualDocument, ...] = Field(min_length=1)
    # Empty for a key of real manuals that prescribe no field repair (ADR-098).
    covered: tuple[Answer, ...] = ()
    documented_without_procedure: tuple[DocumentedOnly, ...] = ()
    absent: tuple[AbsentSymptom, ...] = ()
    never_an_answer: tuple[PageRef, ...] = Field(min_length=1)

    def document(self, machine_model: MachineModel) -> ManualDocument:
        for document in self.documents:
            if document.machine_model == machine_model:
                return document
        raise KeyError(f"the corpus has no manual for {machine_model}")

    def resolve(self, reference: PageRef, within: ManualDocument) -> tuple[str, int]:
        """A page reference as (filename, page), with `document: None` filled in.

        Every comparison between references has to go through this. Testing
        `document is None` instead treats "the other manual" and "this manual,
        named explicitly" as different things, and the checks that depend on the
        distinction then pass on entries they were written to reject.
        """
        return (reference.document or within.filename, reference.page)

    def answer(self, symptom_code: SymptomCode) -> Answer:
        for answer in self.covered:
            if answer.symptom_code == symptom_code:
                return answer
        raise KeyError(f"{symptom_code} is not a symptom the corpus documents a procedure for")

    @property
    def symptom_codes(self) -> frozenset[SymptomCode]:
        """Every symptom the corpus says anything about, including the gaps."""
        return frozenset(
            entry.symptom_code
            for group in (self.covered, self.documented_without_procedure, self.absent)
            for entry in group
        )


def load(manifest: Path = MANIFEST) -> Corpus:
    """A corpus from its manifest. The PDFs are the files beside it."""
    return Corpus.model_validate(yaml.safe_load(manifest.read_text(encoding="utf-8")))


CORPUS = load()

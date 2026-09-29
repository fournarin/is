"""A drafting backend with no model in it (ADR-037 section 9).

It reads the page for the machine model asked about that best answers
the question (see `_best_page`) and returns
the instructions written on it, in the order they are written. That is a poor
drafter and an honest one: it cannot rank two plausible pages by meaning, and it
cannot produce a sentence the manual does not contain.

Three things make it worth having rather than a stub:

  * tiers 1 and 2 run on every commit, on a machine with no GPU and no model
    server (design.md section 12), so without this the whole of drafting would be
    untested until somebody ran the heavy tier by hand;
  * the drafting figures quoted in the report come from here, because an LLM at
    temperature zero still moves between model versions and a number that cannot
    be reproduced cannot be published;
  * it is the floor an LLM backend has to beat. "The model chose a better page"
    is a claim with a baseline behind it, which is the same reason
    `sparse_only` survived slice 3.3.

Pure: no I/O, no clock, no configuration.
"""

from __future__ import annotations

import re

from pdm.contracts.wording import figures
from pdm.llm.domain import DraftRequest, Evidence, Proposal, ProposalKind, ProposedStep

# The marker that begins a numbered instruction: "1. " or "1) ". Found anywhere
# in the text rather than at the start of a line, because **the line breaks are
# not reliable**. Measured on the corpus: pypdf returns M-710iC page 4 with one
# instruction per line and R-2000iC page 4 with all six run into a single line,
# from two PDFs built by the same generator on the same day. A line-anchored
# version of this read the first page and found nothing on the second - no
# error, no empty result, just a repair procedure quietly drafted as prose.
#
# Two shapes are not instructions, both found in a real manufacturer's manual
# (ADR-098): a parenthesised section number, "(1) Inspection ... (2) Life", and a
# numbered footnote, "Note 1. There is no manual release ... 2. The value ...".
# Read as steps, an inspection chapter and a brake table's footnotes came out
# as repair procedures.
#
# Nor a number glued to a word or a hyphen (ADR-103): "valve MV-1. 2. Open"
# made the "1." of "MV-1." step one's marker, step one came out empty, and a
# lockout step vanished from a draft that still read as complete.
_MARKER = re.compile(r"(?<![\w.(\-])(?<!Note )(?<!NOTE )(?P<number>\d{1,2})[.)]\s+")

# The three things a manual writes at the foot of a procedure. Each stops at the
# first sentence end, because with the line breaks gone the whole block can
# arrive as one line: "Required tools: a, b, c. Estimated time: 45 minutes.
# Required skill: robot mechanical." A pattern reading to the end of the line
# put the duration and the skill inside the tool list.
_TOOLS = re.compile(
    r"Required tools:\s*(?P<value>.+?)(?:\.(?=\s|$)|$)",
    re.IGNORECASE,
)
_SKILL = re.compile(r"Required skill:\s*(?P<value>[^.\n]+)", re.IGNORECASE)
_MINUTES = re.compile(r"Estimated time:\s*(?P<value>\d{1,4})\s*minutes?", re.IGNORECASE)

# Where the procedure ends and that block begins.
_FOOTER = re.compile(r"(?:Required tools|Required skill|Estimated time):", re.IGNORECASE)

# A procedure has at least three steps, each an instruction rather than a
# heading or a table (ADR-099). Measured: every procedure in both synthetic
# corpora has three to six steps of six words or more. The false ones in a real
# manual were "1) Grease 2) Lubricant" (a one-word step) and a function table
# numbered "1. 2." (two steps of a hundred words each), and both were drafted
# as repair playbooks.
_MINIMUM_STEPS = 3
_STEP_WORDS = (3, 80)

# Sentence boundary for the diagnostic path. Deliberately crude - a full stop
# followed by a space and a capital or a Thai character. A page that defeats it
# produces one long step, which a reviewer can split; a cleverer splitter that
# cut a sentence in half would produce two steps that each read as complete.
_SENTENCE = re.compile(r"(?<=[.:])\s+(?=[A-Z฀-๿])")

# Below this a "sentence" is a fragment - a heading, a stray line number - and
# not something to put in front of a technician as a step.
_MINIMUM_SENTENCE_CHARACTERS = 30


# How near the end of a page the phrase must sit: room for a printed page
# number or a running footer, and no more (ADR-103).
_CONTINUED_TAIL = 40

# "Continued on page 10." or "continued on the next page" (ADR-100). Removed
# from the step it ends, and followed to the page it names.
_CONTINUED = re.compile(
    r"\s*continued on (?:page (?P<page>\d+)|(?:the )?next page)\.?", re.IGNORECASE
)


def continues_to(text: str, page: int) -> int | None:
    """The page a procedure on this page continues on, or None.

    Only when the phrase closes the page (ADR-103): a "continued" inside a note
    in the middle of a page says nothing about the steps.
    """
    match = _CONTINUED.search(text)
    if match is None or len(text.rstrip()) - match.end() > _CONTINUED_TAIL:
        return None
    return int(match.group("page")) if match.group("page") else page + 1


def _continues_to(page: Evidence) -> int | None:
    return continues_to(page.text, page.page)


def _same_document(request: DraftRequest, page: Evidence, number: int) -> Evidence | None:
    return next(
        (
            other
            for other in request.evidence
            if other.document_id == page.document_id and other.page == number
        ),
        None,
    )


def _procedure(text: str, *, first: int = 1, minimum: int | None = None) -> list[str]:
    """The numbered instructions on a page, in the order they are written.

    Markers are matched by their numbering running 1, 2, 3 and not by where they
    sit on the line, and each step is everything up to the next marker in the
    chain. That is what survives an extractor that lost the line breaks, and it
    also disposes of the case a simpler scan gets wrong: step 1 of every
    procedure in this corpus ends "... the lockout procedure on page 2.", so the
    text contains a "2." that is a cross-reference and not the next step.

    Where a number appears twice before the following one, the **last** is taken.
    On "... on page 2. 2. Remove the belt guard" that keeps the cross-reference
    inside step 1, where it belongs; taking the first would truncate step 1 to
    "... the lockout procedure on page" and lose the page it points at.
    """
    text = _CONTINUED.sub("", text)
    end = _FOOTER.search(text)
    region = text[: end.start()] if end else text
    markers = list(_MARKER.finditer(region))
    if not markers:
        return []

    # A continuation must begin where the previous page stopped (ADR-103).
    if first > 1 and int(markers[0].group("number")) != first:
        return []
    chain: list[re.Match[str]] = []
    expected = first
    for position, marker in enumerate(markers):
        if int(marker.group("number")) != expected:
            continue
        later = [
            candidate
            for candidate in markers[position:]
            if int(candidate.group("number")) == expected
        ]
        following = next(
            (
                candidate
                for candidate in markers[position:]
                if int(candidate.group("number")) == expected + 1
            ),
            None,
        )
        if following is not None:
            later = [candidate for candidate in later if candidate.start() < following.start()]
        chain.append(later[-1])
        expected += 1

    if len(chain) < (_MINIMUM_STEPS if minimum is None else minimum):
        return []

    steps: list[str] = []
    for position, marker in enumerate(chain):
        stop = (
            chain[position + 1].start()
            if position + 1 < len(chain)
            else _end_of_the_last_step(region, marker.end())
        )
        steps.append(" ".join(region[marker.end() : stop].split()))
    # An empty step means a marker was misread; the procedure is refused
    # rather than drafted with a step missing (ADR-103).
    if any(not step for step in steps):
        return []
    low, high = _STEP_WORDS
    if not all(low <= len(step.split()) <= high for step in steps):
        return []
    return steps


def _end_of_the_last_step(region: str, start: int) -> int:
    """Where the numbering stops but the page carries on.

    Every step but the last is bounded by the marker after it. The last one is
    bounded by nothing, and on a page with no tools block that swallows whatever
    follows the list - on the lockout pages, the note that "the 5 minute wait is
    a minimum", which is a warning about the procedure and not a step in it.

    The line break is the boundary, but only where the text reads as finished: a
    sentence end followed by a new sentence. A step that merely wrapped -
    "4. If deflection is" / "outside that range" - has neither, and stays whole.
    """
    position = start
    while (newline := region.find("\n", position)) != -1:
        ended = region[start:newline].rstrip().endswith((".", ":", ";"))
        begins = region[newline + 1 :].lstrip()[:1]
        if ended and begins.isupper():
            return newline
        position = newline + 1
    return len(region)


def _sentences(text: str) -> list[str]:
    """The page as statements, for a page that prescribes nothing.

    Everything is kept, including the sentences that are not instructions. On the
    interlock page the sentence a technician most needs is a prohibition -
    "bypassing an interlock to continue production is prohibited" - and a filter
    that kept only imperatives would drop precisely that one.
    """
    paragraphs = [" ".join(block.split()) for block in text.split("\n\n")]
    sentences = [
        sentence.strip()
        for paragraph in paragraphs
        for sentence in _SENTENCE.split(paragraph)
        if len(sentence.strip()) >= _MINIMUM_SENTENCE_CHARACTERS
    ]
    return sentences


# Provenance: ADR-097, from the evaluation set's dev split, where the answer
# page and the specification table beside it scored 0.99 and 0.87, and the
# nearest irrelevant page under a third of the best.
_STRONG_FRACTION = 0.5


def _best_page(request: DraftRequest) -> Evidence | None:
    """The page to draft from, or None when no page answers the question.

    Only pages of the model being drafted for are considered. The service
    filters other models out before it gets here (ADR-037 §7); this repeats the
    filter because a step from the neighbouring model reads perfectly well with
    28 Nm where this one wants 42.

    When the question carries figures - "above 85 degrees", "axis 1 current
    above 12.5 A" - a page is a candidate only if it states every one of them,
    and among candidates a page with a numbered procedure comes before one
    without (ADR-089). Two failures measured in `docs/drafting-baseline.md`
    motivate this, and both were ranking rather than drafting:

      * the belt-motor *overview* scored above the corrective procedure a page
        later, because it repeats the question's words; both state 85 degrees,
        and only one tells a technician what to do;
      * the axis 2 page scored above the axis 1 page it refers to, and states
        11 A where the question asked about 12.5 A.

    When no page states the question's figures the answer is None, which the
    caller files as "not found". A manual that says nothing about a 62-second
    cycle time must not be answered with the nearest page about something else,
    at whatever score (principle 5). The cost is that a question worded with a
    figure the manual does not use - the plant's 80 degrees against the
    manual's 85 - also finds nothing, and the reviewer asks again without it.

    A question with no figures ranks by retrieval score alone, as before.
    Ties are broken by page so that the same input always drafts the same way.
    """
    ours = [
        evidence
        for evidence in request.evidence
        if evidence.machine_model == request.machine_model and not evidence.joined_only
    ]
    if request.relevance_scored:
        # Nothing clears the draft floor: the manuals do not answer this (ADR-103).
        ours = [evidence for evidence in ours if evidence.score >= request.draft_floor]
    asked = figures(request.question)
    if not asked and not request.relevance_scored:
        return max(ours, key=lambda evidence: (evidence.score, -evidence.page), default=None)
    if not asked:
        # Among the pages scored at least half as relevant as the best, one
        # that prescribes steps comes first (ADR-097). A specification table
        # repeats every figure of a procedure and scores nearly as high as the
        # procedure itself; it tells a technician nothing to do.
        best = max((evidence.score for evidence in ours), default=None)
        if best is None:
            return None
        strong = [evidence for evidence in ours if evidence.score >= best * _STRONG_FRACTION]
        return max(
            strong,
            key=lambda evidence: (bool(_procedure(evidence.text)), evidence.score, -evidence.page),
        )
    stating = [evidence for evidence in ours if asked <= figures(evidence.text)]
    if request.relevance_scored and ours:
        # The same "nearly as relevant as the best" rule as a question with no
        # figures (ADR-103): a procedure at 0.11 stating the figure must not
        # beat the answer at 0.99.
        best = max(evidence.score for evidence in ours)
        stating = [evidence for evidence in stating if evidence.score >= best * _STRONG_FRACTION]
    return max(
        stating,
        key=lambda evidence: (bool(_procedure(evidence.text)), evidence.score, -evidence.page),
        default=None,
    )


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group("value").strip() if match else None


class ExtractiveDrafter:
    """Selects spans off one page. Implements `Drafter`."""

    def propose(self, request: DraftRequest) -> Proposal:
        page = _best_page(request)
        if page is None:
            return Proposal(kind=ProposalKind.NOTHING)

        # A procedure that runs over a page is drafted whole (ADR-100). Chosen on
        # its second page, it starts from the page that says it continues here;
        # chosen on its first, the steps on the next page are joined on, each
        # still citing the page it was read from.
        chosen_score = page.score
        if not _procedure(page.text):
            before = _same_document(request, page, page.page - 1)
            if (
                before is not None
                and _continues_to(before) == page.page
                and _procedure(before.text)
            ):
                page = before
        numbered = _procedure(page.text)
        # A weak page is never a repair (ADR-103). A predecessor brought in to
        # join borrows the score of the page that was chosen.
        if request.relevance_scored and numbered and chosen_score < request.repair_floor:
            numbered = []
        cited = [page.ref] * len(numbered)
        after = None
        target = _continues_to(page) if numbered else None
        if target is not None:
            after = _same_document(request, page, target)
            if after is not None:
                more = _procedure(after.text, first=len(numbered) + 1, minimum=1)
                numbered = [*numbered, *more]
                cited = [*cited, *([after.ref] * len(more))]

        texts = numbered or _sentences(page.text)
        if not texts:
            return Proposal(kind=ProposalKind.NOTHING)
        if not numbered:
            cited = [page.ref] * len(texts)

        footer = page.text if after is None else f"{page.text}\n{after.text}"
        minutes = _first(_MINUTES, footer)
        tools = _first(_TOOLS, footer)

        return Proposal(
            # A page with numbered instructions is a procedure; a page without
            # them documents the symptom and prescribes nothing, which is
            # ADR-033's middle category and owes a fault-finding playbook
            # (ADR-009). The distinction is the manual's own formatting rather
            # than a judgement about the words.
            kind=ProposalKind.REPAIR if numbered else ProposalKind.DIAGNOSTIC,
            steps=tuple(
                ProposedStep(text=text, cites=ref) for text, ref in zip(texts, cited, strict=True)
            ),
            tools=tuple(tool.strip() for tool in tools.split(",")) if tools else (),
            required_skill=_first(_SKILL, footer),
            estimated_minutes=int(minutes) if minutes else None,
        )

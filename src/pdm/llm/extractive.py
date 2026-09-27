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
_MARKER = re.compile(r"(?<![\d.])(?P<number>\d{1,2})[.)]\s+")

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

# A numbered list has at least two items. One "1." on a page is a sentence that
# happens to start with a figure, and treating it as a procedure would turn a
# page of prose into a one-step repair playbook.
_MINIMUM_STEPS = 2

# Sentence boundary for the diagnostic path. Deliberately crude - a full stop
# followed by a space and a capital or a Thai character. A page that defeats it
# produces one long step, which a reviewer can split; a cleverer splitter that
# cut a sentence in half would produce two steps that each read as complete.
_SENTENCE = re.compile(r"(?<=[.:])\s+(?=[A-Z฀-๿])")

# Below this a "sentence" is a fragment - a heading, a stray line number - and
# not something to put in front of a technician as a step.
_MINIMUM_SENTENCE_CHARACTERS = 30


def _procedure(text: str) -> list[str]:
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
    end = _FOOTER.search(text)
    region = text[: end.start()] if end else text
    markers = list(_MARKER.finditer(region))
    if not markers:
        return []

    chain: list[re.Match[str]] = []
    expected = 1
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

    if len(chain) < _MINIMUM_STEPS:
        return []

    steps: list[str] = []
    for position, marker in enumerate(chain):
        stop = (
            chain[position + 1].start()
            if position + 1 < len(chain)
            else _end_of_the_last_step(region, marker.end())
        )
        steps.append(" ".join(region[marker.end() : stop].split()))
    return [step for step in steps if step]


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
        evidence for evidence in request.evidence if evidence.machine_model == request.machine_model
    ]
    asked = figures(request.question)
    if not asked:
        return max(ours, key=lambda evidence: (evidence.score, -evidence.page), default=None)
    stating = [evidence for evidence in ours if asked <= figures(evidence.text)]
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

        numbered = _procedure(page.text)
        texts = numbered or _sentences(page.text)
        if not texts:
            return Proposal(kind=ProposalKind.NOTHING)

        minutes = _first(_MINUTES, page.text)
        tools = _first(_TOOLS, page.text)

        return Proposal(
            # A page with numbered instructions is a procedure; a page without
            # them documents the symptom and prescribes nothing, which is
            # ADR-033's middle category and owes a fault-finding playbook
            # (ADR-009). The distinction is the manual's own formatting rather
            # than a judgement about the words.
            kind=ProposalKind.REPAIR if numbered else ProposalKind.DIAGNOSTIC,
            steps=tuple(ProposedStep(text=text, cites=page.ref) for text in texts),
            tools=tuple(tool.strip() for tool in tools.split(",")) if tools else (),
            required_skill=_first(_SKILL, page.text),
            estimated_minutes=int(minutes) if minutes else None,
        )
